import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from mock_api import fetch_student_api, fetch_university_api
from interview.service import InterviewSession
from interview.state import StudentData, UniversityData


@dataclass
class SessionEntry:
    session_id: str
    room_name: str
    student_id: str
    university_id: str
    student_data: StudentData
    university_data: UniversityData
    candidate_name: str
    difficulty: str
    status: str = "created"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    interview_session: Optional[InterviewSession] = None


class SessionStore:
    """
    Thread-safe registry of active and historical interview sessions.
    Decoupled from LiveKit media transport; holds metadata and Brain state.
    """

    def __init__(self):
        self._sessions: Dict[str, SessionEntry] = {}
        self._room_to_session: Dict[str, str] = {}
        self._lock = threading.Lock()

    def create_session(
        self,
        student_id: str,
        university_id: str,
        candidate_name: Optional[str] = None,
        difficulty: str = "Medium",
    ) -> SessionEntry:
        # Validate existence of student and university records
        raw_student = fetch_student_api(student_id)
        if not raw_student:
            raise ValueError(f"Student record '{student_id}' not found.")

        raw_uni = fetch_university_api(university_id)
        if not raw_uni:
            raise ValueError(f"University record '{university_id}' not found.")

        student_data = StudentData(**raw_student)
        university_data = UniversityData(**raw_uni)
        resolved_name = candidate_name or student_data.full_name or "Candidate"

        session_id = f"session-{uuid.uuid4().hex[:8]}"
        room_name = f"interview-{session_id}"

        # Initialize the LangGraph Brain wrapper
        session_instance = InterviewSession(
            session_id=session_id,
            student_data=student_data,
            university_data=university_data,
            difficulty=difficulty,
        )

        entry = SessionEntry(
            session_id=session_id,
            room_name=room_name,
            student_id=student_id,
            university_id=university_id,
            student_data=student_data,
            university_data=university_data,
            candidate_name=resolved_name,
            difficulty=difficulty,
            status="created",
            interview_session=session_instance,
        )

        with self._lock:
            self._sessions[session_id] = entry
            self._room_to_session[room_name] = session_id

        return entry

    def get_session(self, session_id: str) -> Optional[SessionEntry]:
        with self._lock:
            return self._sessions.get(session_id)

    def get_session_by_room(self, room_name: str) -> Optional[SessionEntry]:
        with self._lock:
            session_id = self._room_to_session.get(room_name)
            return self._sessions.get(session_id) if session_id else None

    def update_status(self, session_id: str, status: str) -> bool:
        with self._lock:
            entry = self._sessions.get(session_id)
            if entry:
                entry.status = status
                return True
            return False

    def clear(self) -> None:
        """Empties the store (primarily used in test teardowns)."""
        with self._lock:
            self._sessions.clear()
            self._room_to_session.clear()


# Global default store instance
default_session_store = SessionStore()
