import os
import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.api.db.models import (
    AIProvider,
    Base,
    CredentialVault,
    StudentProfile,
    University,
    User,
    UserRole,
)
from src.api.security.auth import (
    create_access_token,
    decode_access_token,
    get_current_user,
    hash_password,
    verify_password,
)
from src.api.security.vault import decrypt_api_key, encrypt_api_key, mask_api_key
from src.api.services import question_service


@pytest.fixture
def test_db():
    """In-memory SQLite database for isolated unit testing."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


class TestSecurityVault:
    def test_fernet_encryption_roundtrip(self):
        plain = "sk-openrouter-secret-key-12345678"
        ciphertext = encrypt_api_key(plain)
        assert ciphertext != plain
        decrypted = decrypt_api_key(ciphertext)
        assert decrypted == plain

    def test_key_masking(self):
        key = "sk-or-v1-abcdef1234567890"
        masked = mask_api_key(key)
        assert masked == "sk-...7890"
        assert mask_api_key("") == "sk-...xxxx"


class TestAuthenticationAndDeviceLockdown:
    def test_password_hashing(self):
        password = "SecurePassword123!"
        hashed = hash_password(password)
        assert hashed != password
        assert verify_password(password, hashed) is True
        assert verify_password("WrongPassword!", hashed) is False

    def test_single_device_lockdown_success(self, test_db):
        user = User(
            username="student1",
            email="student1@example.com",
            hashed_password=hash_password("Pass123!"),
            role=UserRole.STUDENT,
            active_device_id="device-laptop-abc",
        )
        test_db.add(user)
        test_db.commit()

        token = create_access_token(user_id=user.id, role="student", device_id="device-laptop-abc")
        verified_user = get_current_user(access_token=token, authorization=None, db=test_db)
        assert verified_user.id == user.id

    def test_single_device_lockdown_rejection_on_device_switch(self, test_db):
        user = User(
            username="student2",
            email="student2@example.com",
            hashed_password=hash_password("Pass123!"),
            role=UserRole.STUDENT,
            active_device_id="device-phone-xyz",  # Logged in later on phone
        )
        test_db.add(user)
        test_db.commit()

        # Token issued for old laptop
        old_token = create_access_token(user_id=user.id, role="student", device_id="device-laptop-abc")

        # Access on laptop must be terminated
        with pytest.raises(HTTPException) as exc:
            get_current_user(access_token=old_token, authorization=None, db=test_db)
        assert exc.value.status_code == 401
        assert "another device" in exc.value.detail


class TestQuestionServiceAndAssignmentGate:
    def test_create_and_fetch_question_bank(self, test_db):
        payload = [
            {
                "name": "Academic Preparedness",
                "description": "Evaluates candidate understanding of UK modules",
                "questions": [
                    {
                        "question_text": "Why did you choose this university?",
                        "expected_time_to_ans": 45,
                        "expected_answer_keywords": ["curriculum", "professors", "ranking"],
                        "followups": [
                            {
                                "followup_text": "Which specific module excites you the most?",
                                "expected_time_to_ans": 30,
                                "expected_answer_keywords": ["machine learning", "data science"],
                            }
                        ],
                    }
                ],
            }
        ]

        bank = question_service.create_question_bank_from_payload(
            db=test_db,
            title="Standard UKVI Intake 2026",
            difficulty="Medium",
            university_id=None,
            topics_payload=payload,
        )
        assert bank.id is not None
        assert bank.title == "Standard UKVI Intake 2026"

        topics = question_service.get_topics_for_bank(test_db, bank.id)
        assert len(topics) == 1
        assert topics[0]["name"] == "Academic Preparedness"

        questions = question_service.get_questions_for_topic(test_db, topics[0]["topic_id"])
        assert len(questions) == 1
        assert "choose this university" in questions[0]["question_text"]
        assert "curriculum" in questions[0]["expected_answer_keywords"]

        followups = question_service.get_followups_for_question(test_db, questions[0]["question_id"])
        assert len(followups) == 1
        assert "specific module" in followups[0]["followup_text"]

    def test_auto_deactivation_invariant_and_assignment_gate(self, test_db):
        # Create student user and profile
        user = User(
            username="candidate_ukvi",
            email="candidate@ukvi.com",
            hashed_password=hash_password("Pass123!"),
            role=UserRole.STUDENT,
        )
        test_db.add(user)
        test_db.flush()

        student = StudentProfile(
            user_id=user.id,
            full_name="John Doe",
            academic_background="BSc Computer Science",
        )
        test_db.add(student)
        test_db.commit()

        # Gate Check 1: No bank assigned -> returns None
        assert question_service.get_assigned_bank_for_user(test_db, user.id) is None

        # Create two question banks
        bank1 = question_service.create_question_bank_from_payload(
            db=test_db, title="Bank Easy", difficulty="Easy", university_id=None, topics_payload=[]
        )
        bank2 = question_service.create_question_bank_from_payload(
            db=test_db, title="Bank Hard", difficulty="Hard", university_id=None, topics_payload=[]
        )

        # Assign Bank 1
        question_service.assign_bank_to_student(test_db, bank1.id, student_id=student.id)
        active_bank = question_service.get_assigned_bank_for_user(test_db, user.id)
        assert active_bank is not None
        assert active_bank["bank_id"] == bank1.id

        # Assign Bank 2 -> Auto-deactivates Bank 1 (Guaranteeing strictly at most 1 active bank)
        question_service.assign_bank_to_student(test_db, bank2.id, student_id=student.id)
        active_bank = question_service.get_assigned_bank_for_user(test_db, user.id)
        assert active_bank is not None
        assert active_bank["bank_id"] == bank2.id


class TestInstitutionalKeyGovernance:
    def test_student_key_capture_strictly_disabled(self, test_db):
        from src.api.services import vault_service

        user = User(
            username="student_lock_test",
            email="lock@test.com",
            hashed_password=hash_password("Pass123!"),
            role=UserRole.STUDENT,
        )
        test_db.add(user)
        test_db.commit()

        # Candidate attempting to save any key must raise 403 Forbidden
        with pytest.raises(HTTPException) as exc_info:
            vault_service.save_model_credential(
                db=test_db,
                category="thinking",
                provider="openrouter",
                api_key="sk-or-v1-student-attempt-key",
                user_id=user.id,
                is_admin=False,
            )
        assert exc_info.value.status_code == 403
        assert "Candidate API key capture is disabled" in exc_info.value.detail

    def test_admin_clean_student_credentials(self, test_db):
        from src.api.services import vault_service

        user = User(
            username="student_clean_target",
            email="target@test.com",
            hashed_password=hash_password("Pass123!"),
            role=UserRole.STUDENT,
        )
        test_db.add(user)
        test_db.commit()

        # Insert a legacy student credential directly
        legacy_key = CredentialVault(
            user_id=user.id,
            category="stt",
            provider="google",
            encrypted_api_key=encrypt_api_key("AIzaSyLegacyKey"),
            key_preview="AIza...yKey",
            is_admin_key=False,
        )
        test_db.add(legacy_key)
        test_db.commit()

        # Admin cleans/purges student credentials
        deleted = vault_service.clean_student_credentials(test_db, student_id=user.id)
        assert deleted == 1

        remaining = test_db.query(CredentialVault).filter(CredentialVault.user_id == user.id).first()
        assert remaining is None

    def test_student_matrix_locks_and_protects_admin_secret(self, test_db):
        from src.api.services import vault_service

        # Admin saves thinking key
        vault_service.save_model_credential(
            db=test_db,
            category="thinking",
            provider="openrouter",
            api_key="sk-or-v1-super-secret-institution-token",
            model_name="deepseek/deepseek-v4-flash-0731",
            is_admin=True,
        )

        user = User(
            username="student_secret_test",
            email="secret@test.com",
            hashed_password=hash_password("Pass123!"),
            role=UserRole.STUDENT,
        )
        test_db.add(user)
        test_db.commit()

        matrix = vault_service.get_student_model_matrix(test_db, user.id)
        assert matrix["thinking"]["admin_locked"] is True
        # Admin secret is masked and never revealed to student
        assert "super-secret" not in matrix["thinking"]["active_preview"]
        assert matrix["thinking"]["active_preview"] == "Institution Enforced (Protected)"

