import logging
import os
from typing import Any, Dict, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware

from interview.api.schemas import (
    CreateSessionRequest,
    LiveKitWebhookPayload,
    SessionResponse,
    SessionStatusResponse,
    TokenRequest,
    TokenResponse,
)
from interview.api.session_store import default_session_store
from interview.live_kit.token_service import create_candidate_token

load_dotenv()

logger = logging.getLogger("interview-api-server")

app = FastAPI(
    title="UK Credibility & Academic AI Interviewer API",
    description="Control plane for candidate validation, LiveKit WebRTC AccessToken issuance, and session state tracking.",
    version="1.0.0",
)

# Enable CORS for browser clients (e.g. Next.js / React / Vue)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", tags=["Health"])
async def root() -> Dict[str, str]:
    """Health check endpoint."""
    return {
        "service": "UK Credibility Voice Interview API",
        "status": "online",
        "version": "1.0.0",
    }


@app.post(
    "/api/sessions",
    response_model=SessionResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Sessions"],
)
async def create_session(request: CreateSessionRequest) -> SessionResponse:
    """
    Creates an interview session.
    Validates candidate CAS profile and UK university parameters against mock API.
    """
    try:
        entry = default_session_store.create_session(
            student_id=request.student_id,
            university_id=request.university_id,
            candidate_name=request.candidate_name,
            difficulty=request.difficulty,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )

    return SessionResponse(
        session_id=entry.session_id,
        room_name=entry.room_name,
        status=entry.status,
        student_id=entry.student_id,
        university_id=entry.university_id,
        student_name=entry.student_data.full_name or entry.candidate_name,
        university_name=entry.university_data.official_name,
        course_name=entry.university_data.target_course,
    )


@app.post(
    "/api/sessions/{session_id}/token",
    response_model=TokenResponse,
    tags=["LiveKit WebRTC"],
)
async def issue_candidate_token(
    session_id: str,
    request: Optional[TokenRequest] = None,
) -> TokenResponse:
    """
    Generates a cryptographically signed LiveKit JWT AccessToken.
    Grants audio-only WebRTC publishing (microphone) and data channel permissions.
    The client connects DIRECTLY to LiveKit Server with this token.
    """
    entry = default_session_store.get_session(session_id)
    if not entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Interview session '{session_id}' does not exist.",
        )

    candidate_id = (request and request.candidate_id) or entry.student_id
    candidate_name = (request and request.candidate_name) or entry.candidate_name

    # Generate token using LiveKit API
    token = create_candidate_token(
        room_name=entry.room_name,
        candidate_id=candidate_id,
        candidate_name=candidate_name,
    )

    if entry.status == "created":
        default_session_store.update_status(session_id, "in_progress")

    livekit_url = os.getenv("LIVEKIT_URL", "ws://127.0.0.1:7880")

    return TokenResponse(
        session_id=entry.session_id,
        room_name=entry.room_name,
        token=token,
        livekit_url=livekit_url,
        participant_identity=candidate_id,
        participant_name=candidate_name,
    )


@app.get(
    "/api/sessions/{session_id}",
    response_model=SessionResponse,
    tags=["Sessions"],
)
async def get_session(session_id: str) -> SessionResponse:
    """Retrieves session metadata."""
    entry = default_session_store.get_session(session_id)
    if not entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session '{session_id}' not found.",
        )

    return SessionResponse(
        session_id=entry.session_id,
        room_name=entry.room_name,
        status=entry.status,
        student_id=entry.student_id,
        university_id=entry.university_id,
        student_name=entry.student_data.full_name or entry.candidate_name,
        university_name=entry.university_data.official_name,
        course_name=entry.university_data.target_course,
    )


@app.get(
    "/api/sessions/{session_id}/status",
    response_model=SessionStatusResponse,
    tags=["Sessions"],
)
async def get_session_status(session_id: str) -> SessionStatusResponse:
    """Returns real-time LangGraph state, topic progression, and evaluations."""
    entry = default_session_store.get_session(session_id)
    if not entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session '{session_id}' not found.",
        )

    session_inst = entry.interview_session
    latest_state = session_inst.latest_state if session_inst else {}

    topics = latest_state.get("topics", [])
    evaluations = latest_state.get("evaluations", [])
    latest_eval = evaluations[-1].model_dump() if evaluations and hasattr(evaluations[-1], "model_dump") else (evaluations[-1] if evaluations else None)
    final_eval = latest_state.get("final_evaluation")
    if final_eval and hasattr(final_eval, "model_dump"):
        final_eval = final_eval.model_dump()

    return SessionStatusResponse(
        session_id=entry.session_id,
        room_name=entry.room_name,
        interview_status=latest_state.get("interview_status", entry.status),
        current_topic_idx=latest_state.get("current_topic_idx", 0),
        current_question_idx=latest_state.get("current_question_idx", 0),
        current_followup_idx=latest_state.get("current_followup_idx", -1),
        topics_count=len(topics),
        evaluations_count=len(evaluations),
        latest_evaluation=latest_eval,
        final_evaluation=final_eval,
    )


@app.get(
    "/api/sessions/{session_id}/evaluation",
    tags=["Evaluation"],
)
async def get_session_evaluation(session_id: str) -> Dict[str, Any]:
    """Returns the official UKVI credibility and academic evaluation report."""
    entry = default_session_store.get_session(session_id)
    if not entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session '{session_id}' not found.",
        )

    session_inst = entry.interview_session
    final_eval = session_inst.get_final_evaluation() if session_inst else None
    if not final_eval:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Final evaluation report has not been generated yet. The interview must be completed first.",
        )

    return final_eval


@app.post(
    "/api/livekit/webhook",
    tags=["Webhooks"],
)
async def handle_livekit_webhook(payload: LiveKitWebhookPayload) -> Dict[str, Any]:
    """
    Receives lifecycle webhooks dispatched by the LiveKit Server.
    Updates session state when participants leave or rooms close.
    """
    event = payload.event
    logger.info(f"Received LiveKit webhook event: {event}")

    room_info = payload.room or {}
    room_name = room_info.get("name")

    if room_name:
        entry = default_session_store.get_session_by_room(room_name)
        if entry:
            if event in ("room_finished", "participant_left"):
                default_session_store.update_status(entry.session_id, "completed")
                logger.info(f"Session {entry.session_id} marked as completed via webhook.")

    return {"status": "ok", "event": event}
