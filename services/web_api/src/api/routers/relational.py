import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from src.api.db.session import get_db
from src.api.services import question_service

router = APIRouter(prefix="/api", tags=["Relational Bank Navigation"])


@router.get("/banks/{bank_id}/topics")
def api_get_topics(bank_id: str, db: Session = Depends(get_db)):
    """Fetches all topics belonging to a question bank in sequence."""
    return question_service.get_topics_for_bank(db, bank_id)


@router.get("/topics/{topic_id}/questions")
def api_get_questions(topic_id: str, db: Session = Depends(get_db)):
    """Fetches all questions belonging to a specific topic in sequence."""
    return question_service.get_questions_for_topic(db, topic_id)


@router.get("/questions/{question_id}/followups")
def api_get_followups(question_id: str, db: Session = Depends(get_db)):
    """Fetches all follow-up probes for a question."""
    return question_service.get_followups_for_question(db, question_id)


@router.get("/students/{user_id}/assigned-questions")
def api_get_assigned_questions(user_id: str, db: Session = Depends(get_db)):
    """
    Pre-Assignment Gate Resolution:
    Returns the single active assigned QuestionBank, or 404 if unassigned.
    """
    bank = question_service.get_assigned_bank_for_user(db, user_id)
    if not bank:
        raise HTTPException(
            status_code=404,
            detail="No active question bank assigned to this student.",
        )
    return bank


@router.get("/students/{user_id}/model-config")
def api_get_resolved_model_config(user_id: str, db: Session = Depends(get_db)):
    """
    Resolves active dynamic 3-model configuration (Thinking, STT, TTS) for a candidate:
    Tier 1 (Student BYOK) -> Tier 2 (Admin Default) -> Tier 3 (.env Fallback).
    Decrypted credentials provided for agent worker execution.
    """
    from src.api.services import vault_service

    return {
        "thinking": vault_service.resolve_model_config(db, "thinking", student_user_id=user_id),
        "stt": vault_service.resolve_model_config(db, "stt", student_user_id=user_id),
        "tts": vault_service.resolve_model_config(db, "tts", student_user_id=user_id),
    }


@router.post("/sessions/{session_identifier}/complete")
def api_complete_session(
    session_identifier: str,
    payload: dict,
    db: Session = Depends(get_db),
):
    """
    Persists final interview conclusion metrics, overall score, and generated CAS report.
    Accepts either session UUID or room_name (e.g. room-<student_id>).
    """
    from src.api.db.models import InterviewSessionRecord
    session_record = (
        db.query(InterviewSessionRecord)
        .filter(
            (InterviewSessionRecord.id == session_identifier)
            | (InterviewSessionRecord.room_name == session_identifier)
            | (InterviewSessionRecord.room_name == f"room-{session_identifier}")
        )
        .order_by(
            InterviewSessionRecord.status.in_(["in_progress", "created"]).desc(),
            InterviewSessionRecord.created_at.desc(),
        )
        .first()
    )
    if not session_record:
        raise HTTPException(status_code=404, detail="Interview session not found.")

    overall_score = float(payload.get("overall_score", 0.0))
    ukvi_rec = str(payload.get("ukvi_recommendation", "Genuine"))
    report_data = payload.get("report_data", {})
    turns_data = payload.get("turns_data", [])

    completed = question_service.record_completed_session(
        db=db,
        session_id=session_record.id,
        overall_score=overall_score,
        ukvi_recommendation=ukvi_rec,
        report_data=report_data,
        turns_data=turns_data,
    )
    return {"status": "completed", "session_id": completed.id if completed else session_record.id}


@router.post("/sessions/{session_identifier}/discard")
def api_discard_session(
    session_identifier: str,
    payload: dict,
    db: Session = Depends(get_db),
):
    """
    Constitutional Invariant (SPEC-005 Art. I §10):
    Purges partial turn records and marks session discarded if candidate aborts.
    """
    from src.api.db.models import InterviewSessionRecord, TurnEvaluationRecord

    session_record = (
        db.query(InterviewSessionRecord)
        .filter(
            (InterviewSessionRecord.id == session_identifier)
            | (InterviewSessionRecord.room_name == session_identifier)
            | (InterviewSessionRecord.room_name == f"room-{session_identifier}")
        )
        .order_by(
            InterviewSessionRecord.status.in_(["in_progress", "created"]).desc(),
            InterviewSessionRecord.created_at.desc(),
        )
        .first()
    )
    if not session_record:
        return {"status": "not_found", "session_id": session_identifier}

    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    elapsed_seconds = 0.0
    if session_record.created_at:
        try:
            created_tz = session_record.created_at if session_record.created_at.tzinfo else session_record.created_at.replace(tzinfo=timezone.utc)
            elapsed_seconds = (now - created_tz).total_seconds()
        except Exception:
            pass

    reason = payload.get("reason", "Candidate disconnected mid-session")
    turns_count = db.query(TurnEvaluationRecord).filter(TurnEvaluationRecord.session_id == session_record.id).count()

    db.query(TurnEvaluationRecord).filter(TurnEvaluationRecord.session_id == session_record.id).delete()
    session_record.status = "discarded"
    session_record.concluded_at = now
    session_record.report_json = json.dumps({
        "status": "discarded",
        "reason": reason,
        "elapsed_seconds": round(elapsed_seconds, 1),
        "turns_used": turns_count,
        "discarded_at": now.isoformat(),
    })
    db.commit()
    return {
        "status": "discarded",
        "session_id": session_record.id,
        "elapsed_seconds": round(elapsed_seconds, 1),
        "turns_used": turns_count,
        "reason": reason,
    }


