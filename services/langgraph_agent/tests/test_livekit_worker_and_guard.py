import json
from unittest.mock import AsyncMock, MagicMock
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from src.agent.guard import abort_and_discard_session
from src.agent.worker import broadcast_datachannel_message
from src.api.db.models import (
    Base,
    InterviewSessionRecord,
    QuestionBank,
    StudentProfile,
    TurnEvaluationRecord,
    User,
    UserRole,
)


@pytest.fixture
def test_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()


class TestLiveKitWorkerAndDiscardGuard:
    def test_broadcast_datachannel_message_encodes_json(self):
        async def _run():
            room = MagicMock()
            room.local_participant = MagicMock()
            room.local_participant.publish_data = AsyncMock()

            payload = {"type": "scorecard", "score": 85.0}
            await broadcast_datachannel_message(room, payload)

            room.local_participant.publish_data.assert_called_once()
            call_args = room.local_participant.publish_data.call_args
            data_bytes = call_args[0][0]
            assert json.loads(data_bytes.decode("utf-8")) == payload
            assert call_args[1]["reliable"] is True

        import asyncio
        asyncio.run(_run())

    def test_abort_and_discard_session_purges_partial_turns(self, test_db):
        # Create student, bank, and in_progress session with partial turns
        user = User(username="stud_disc", email="disc@ukvi.com", hashed_password="pw", role=UserRole.STUDENT)
        test_db.add(user)
        test_db.flush()

        student = StudentProfile(user_id=user.id, full_name="Disconnect Student")
        test_db.add(student)
        test_db.flush()

        bank = QuestionBank(title="Test Bank", university_id=None)
        test_db.add(bank)
        test_db.flush()

        session = InterviewSessionRecord(
            student_id=student.id,
            bank_id=bank.id,
            room_name="room-disc-test-123",
            status="in_progress",
        )
        test_db.add(session)
        test_db.flush()

        # Add 2 partial turns
        t1 = TurnEvaluationRecord(session_id=session.id, turn_type="question", reference_id="q1", spoken_prompt="Q1", score=80.0)
        t2 = TurnEvaluationRecord(session_id=session.id, turn_type="reask", reference_id="q1", spoken_prompt="R1", score=60.0)
        test_db.add_all([t1, t2])
        test_db.commit()

        assert test_db.query(TurnEvaluationRecord).filter(TurnEvaluationRecord.session_id == session.id).count() == 2

        # Trigger Discard Guard
        result = abort_and_discard_session(db=test_db, session_id=session.id, reason="Network timeout mid-turn")
        assert result["status"] == "discarded"

        # Verify: Partial turns purged!
        remaining_turns = test_db.query(TurnEvaluationRecord).filter(TurnEvaluationRecord.session_id == session.id).count()
        assert remaining_turns == 0

        # Verify: Session marked 'discarded'
        updated_session = test_db.query(InterviewSessionRecord).filter(InterviewSessionRecord.id == session.id).first()
        assert updated_session.status == "discarded"
        assert "Network timeout mid-turn" in updated_session.report_json
