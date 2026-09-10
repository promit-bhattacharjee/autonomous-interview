from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class CreateSessionRequest(BaseModel):
    """Request payload to initialize an autonomous interview session."""
    student_id: str = Field(default="UK-CAS-2026-9041", description="Student CAS or profile ID")
    university_id: str = Field(default="UK-HERTS-01", description="Target UK university ID")
    candidate_name: Optional[str] = Field(default=None, description="Optional custom candidate name")
    difficulty: str = Field(default="Medium", description="Interview rubric difficulty: Easy, Medium, or Hard")


class SessionResponse(BaseModel):
    """Metadata response for an initialized interview session."""
    session_id: str
    room_name: str
    status: str
    student_id: str
    university_id: str
    student_name: str
    university_name: str
    course_name: str


class TokenRequest(BaseModel):
    """Optional parameters when requesting an audio access token for a candidate."""
    candidate_id: Optional[str] = Field(default=None, description="Custom candidate identity")
    candidate_name: Optional[str] = Field(default=None, description="Custom candidate display name")


class TokenResponse(BaseModel):
    """Response containing LiveKit direct WebRTC JWT and connection URL."""
    session_id: str
    room_name: str
    token: str
    livekit_url: str
    participant_identity: str
    participant_name: str


class EvaluationRecordSchema(BaseModel):
    """Turn evaluation record schema for client inspection."""
    topic_id: str
    question_id: str
    attempt_number: int
    accuracy_score: float
    is_passed: bool
    is_reask: bool
    matched_keywords: List[str] = []
    unmatched_keywords: List[str] = []
    feedback: str = ""


class SessionStatusResponse(BaseModel):
    """Live state of an interview session."""
    session_id: str
    room_name: str
    interview_status: str
    current_topic_idx: int = 0
    current_question_idx: int = 0
    current_followup_idx: int = -1
    topics_count: int = 0
    evaluations_count: int = 0
    latest_evaluation: Optional[Dict[str, Any]] = None
    final_evaluation: Optional[Dict[str, Any]] = None


class LiveKitWebhookPayload(BaseModel):
    """Standard payload structure for LiveKit Server webhooks."""
    event: str
    room: Optional[Dict[str, Any]] = None
    participant: Optional[Dict[str, Any]] = None
    created_at: Optional[int] = None
