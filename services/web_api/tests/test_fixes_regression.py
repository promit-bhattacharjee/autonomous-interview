import json
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from src.api.db.models import Base, CredentialVault, FollowupRecord, QuestionBank, QuestionRecord, TopicRecord, User, UserRole
from src.api.security.vault import encrypt_api_key, mask_api_key
from src.api.services import question_service, vault_service
from services.langgraph_agent.src.agent.guard import abort_and_discard_session
from services.langgraph_agent.src.agent.prompts.rubrics import evaluate_response_keywords


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()


class TestFixesRegression:
    def test_rubrics_word_boundary_regex(self):
        """Validates that short words like 'in' or 'art' do not match inside larger words."""
        # Candidate says 'training start', but expected keywords are 'in' and 'art'
        score, hits, missed = evaluate_response_keywords("training start", ["in", "art"])
        assert hits == []
        assert set(missed) == {"in", "art"}
        assert score == 0.0

        # Exact match should succeed
        score, hits, missed = evaluate_response_keywords("I enrolled in state of the art facilities", ["in", "art"])
        assert set(hits) == {"in", "art"}
        assert missed == []
        assert score == 100.0

    def test_question_service_handles_none_keywords(self, db_session):
        """Validates that question_service does not raise TypeError when keywords JSON is None."""
        bank = QuestionBank(title="Test Bank")
        db_session.add(bank)
        db_session.commit()

        topic = TopicRecord(bank_id=bank.id, name="Topic 1")
        db_session.add(topic)
        db_session.commit()

        q = QuestionRecord(
            topic_id=topic.id,
            question_text="Sample Q",
            expected_answer_keywords_json=None,
        )
        db_session.add(q)
        db_session.commit()

        f = FollowupRecord(
            question_id=q.id,
            followup_text="Sample F",
            expected_answer_keywords_json=None,
        )
        db_session.add(f)
        db_session.commit()

        questions = question_service.get_questions_for_topic(db_session, topic.id)
        assert len(questions) == 1
        assert questions[0]["expected_answer_keywords"] == []

        followups = question_service.get_followups_for_question(db_session, q.id)
        assert len(followups) == 1
        assert followups[0]["expected_answer_keywords"] == []

    def test_vault_service_preserves_existing_key_on_masked_preview(self, db_session):
        """Validates that submitting masked key preview sk-...xxxx does not overwrite the secret."""
        real_key = "sk-live-super-secret-key-12345"
        vault_service.save_model_credential(
            db=db_session,
            category="thinking",
            provider="openrouter",
            api_key=real_key,
            model_name="deepseek/deepseek-v4",
            is_admin=True,
        )

        entry = db_session.query(CredentialVault).filter(CredentialVault.category == "thinking").first()
        initial_encrypted = entry.encrypted_api_key
        assert entry.key_preview == mask_api_key(real_key)

        # Update model name while passing masked preview in form
        vault_service.save_model_credential(
            db=db_session,
            category="thinking",
            provider="openrouter",
            api_key=entry.key_preview,  # e.g. sk-...2345
            model_name="deepseek/deepseek-v4-updated",
            is_admin=True,
        )

        db_session.refresh(entry)
        assert entry.model_name == "deepseek/deepseek-v4-updated"
        # Secret key should NOT have been overwritten
        assert entry.encrypted_api_key == initial_encrypted

    def test_discard_guard_safe_json_with_quotes(self, db_session):
        """Validates that reason with quotes does not break JSON serialization."""
        from src.api.db.models import InterviewSessionRecord
        bank = QuestionBank(title="Bank")
        db_session.add(bank)
        db_session.commit()

        profile_user = User(
            username="stud1",
            email="s1@test.com",
            hashed_password="pw",
            role=UserRole.STUDENT,
        )
        db_session.add(profile_user)
        db_session.commit()

        from src.api.db.models import StudentProfile
        sp = StudentProfile(user_id=profile_user.id, full_name="Student 1")
        db_session.add(sp)
        db_session.commit()

        session = InterviewSessionRecord(
            student_id=sp.id,
            bank_id=bank.id,
            room_name="room-stud1",
            status="in_progress",
        )
        db_session.add(session)
        db_session.commit()

        tricky_reason = 'Candidate said: "I want to abort now!" and newline\n'
        abort_and_discard_session(db=db_session, session_id="room-stud1", reason=tricky_reason)

        db_session.refresh(session)
        assert session.status == "discarded"
        parsed = json.loads(session.report_json)
        assert parsed["discard_reason"] == tricky_reason
