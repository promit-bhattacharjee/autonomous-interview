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
