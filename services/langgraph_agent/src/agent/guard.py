import logging
from typing import Optional
from sqlalchemy.orm import Session

logger = logging.getLogger("livekit_discard_guard")


def abort_and_discard_session(
    db: Optional[Session],
    session_id: str,
    reason: str = "Client disconnected mid-interview",
) -> dict[str, str]:
    """
    Constitutional Invariant (SPEC-005 Art. I §10):
    If a candidate loses connection or token budget runs out mid-session,
    the session MUST be marked 'discarded' and partial turn records purged.
    """
    logger.warning("Aborting session %s: %s", session_id, reason)

    if db:
        try:
            from src.api.db.models import InterviewSessionRecord, TurnEvaluationRecord

            # Locate session record by ID or room_name
            session = (
                db.query(InterviewSessionRecord)
                .filter(
                    (InterviewSessionRecord.id == session_id)
                    | (InterviewSessionRecord.room_name == session_id)
                    | (InterviewSessionRecord.room_name == f"room-{session_id}")
                )
                .order_by(
                    InterviewSessionRecord.status.in_(["in_progress", "created"]).desc(),
                    InterviewSessionRecord.created_at.desc(),
                )
                .first()
            )
            if session:
                # Purge partial turn evaluation records
                db.query(TurnEvaluationRecord).filter(TurnEvaluationRecord.session_id == session.id).delete()
                session.status = "discarded"
                session.report_json = f'{{"discard_reason": "{reason}"}}'
                db.commit()
                return {"status": "discarded", "session_id": session.id, "reason": reason}
        except Exception as exc:
            logger.error("Failed to discard session in database: %s", exc)

    # Fallback to API service endpoint
    import os
    import httpx
    api_url = os.getenv("API_SERVICE_URL", "http://localhost:8000")
    try:
        with httpx.Client(base_url=api_url, timeout=5.0) as client:
            client.post(f"/api/sessions/{session_id}/discard", json={"reason": reason})
    except Exception as http_exc:
        logger.warning("Failed to notify API service of discarded session: %s", http_exc)

    return {"status": "discarded", "session_id": session_id, "reason": reason}

