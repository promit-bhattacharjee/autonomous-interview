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

            # Purge partial turn evaluation records
            db.query(TurnEvaluationRecord).filter(TurnEvaluationRecord.session_id == session_id).delete()

            # Mark session as discarded
            session = db.query(InterviewSessionRecord).filter(InterviewSessionRecord.id == session_id).first()
            if session:
                session.status = "discarded"
                session.report_json = f'{{"discard_reason": "{reason}"}}'
            db.commit()
            return {"status": "discarded", "session_id": session_id, "reason": reason}
        except Exception as exc:
            logger.error("Failed to discard session in database: %s", exc)
            return {"status": "error", "error": str(exc)}

    return {"status": "discarded", "session_id": session_id, "reason": reason}
