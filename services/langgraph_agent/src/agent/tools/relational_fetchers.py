import json
import os
from typing import Any, Optional
import httpx
from langchain_core.tools import tool

API_SERVICE_URL = os.getenv("API_SERVICE_URL", "http://localhost:8000")
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./interview.db")


def _get_db_session_if_available():
    """Attempts to create a local database session for direct ORM access."""
    try:
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
        engine = create_engine(DATABASE_URL, connect_args=connect_args, echo=False)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        return SessionLocal()
    except Exception:
        return None


@tool
def fetch_topics(bank_id: str) -> list[dict[str, Any]]:
    """Fetches all topics belonging to a question bank in sequence."""
    db = _get_db_session_if_available()
    if db:
        try:
            from src.api.services.question_service import get_topics_for_bank
            return get_topics_for_bank(db, bank_id)
        except Exception:
            pass
        finally:
            db.close()

    # Fallback to HTTP REST endpoint
    with httpx.Client(base_url=API_SERVICE_URL, timeout=10.0) as client:
        res = client.get(f"/api/banks/{bank_id}/topics")
        return res.json() if res.status_code == 200 else []


@tool
def fetch_questions(topic_id: str) -> list[dict[str, Any]]:
    """Fetches all questions belonging to a specific topic in sequence."""
    db = _get_db_session_if_available()
    if db:
        try:
            from src.api.services.question_service import get_questions_for_topic
            return get_questions_for_topic(db, topic_id)
        except Exception:
            pass
        finally:
            db.close()

    with httpx.Client(base_url=API_SERVICE_URL, timeout=10.0) as client:
        res = client.get(f"/api/topics/{topic_id}/questions")
        return res.json() if res.status_code == 200 else []


@tool
def fetch_followups(question_id: str) -> list[dict[str, Any]]:
    """Fetches all follow-up probes for a question."""
    db = _get_db_session_if_available()
    if db:
        try:
            from src.api.services.question_service import get_followups_for_question
            return get_followups_for_question(db, question_id)
        except Exception:
            pass
        finally:
            db.close()

    with httpx.Client(base_url=API_SERVICE_URL, timeout=10.0) as client:
        res = client.get(f"/api/questions/{question_id}/followups")
        return res.json() if res.status_code == 200 else []


@tool
def get_user_assigned_questions(user_id: str) -> Optional[dict[str, Any]]:
    """
    Pre-Assignment Gate check: Resolves the single active QuestionBank assigned to a candidate.
    Returns None if no question set is assigned.
    """
    db = _get_db_session_if_available()
    if db:
        try:
            from src.api.services.question_service import get_assigned_bank_for_user
            return get_assigned_bank_for_user(db, user_id)
        except Exception:
            pass
        finally:
            db.close()

    with httpx.Client(base_url=API_SERVICE_URL, timeout=10.0) as client:
        res = client.get(f"/api/students/{user_id}/assigned-questions")
        return res.json() if res.status_code == 200 else None
