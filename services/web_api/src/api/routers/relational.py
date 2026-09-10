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
