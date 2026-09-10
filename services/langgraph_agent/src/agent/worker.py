import asyncio
import json
import logging
import os
from typing import Any
from livekit import rtc
from livekit.agents import AutoSubscribe, JobContext, JobProcess, WorkerOptions, cli
from src.agent.guard import abort_and_discard_session
from src.agent.tools.relational_fetchers import get_user_assigned_questions

logger = logging.getLogger("livekit_worker")
logging.basicConfig(level=logging.INFO)


async def broadcast_datachannel_message(room: rtc.Room, payload: dict[str, Any]) -> None:
    """Broadcasts a JSON packet over the native WebRTC DataChannel to connected candidates."""
    try:
        data_bytes = json.dumps(payload).encode("utf-8")
        await room.local_participant.publish_data(data_bytes, reliable=True)
    except Exception as exc:
        logger.error("Failed to broadcast DataChannel message: %s", exc)


async def entrypoint(ctx: JobContext):
    """Entrypoint invoked by LiveKit Server when candidate connects to a room."""
    logger.info("Connecting to LiveKit room: %s", ctx.room.name)
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)

    # Participant state
    session_id = f"sess-{ctx.room.name}"
    is_completed_normally = False

    @ctx.room.on("participant_disconnected")
    def on_participant_disconnected(participant: rtc.RemoteParticipant):
        nonlocal is_completed_normally
        if not is_completed_normally:
            logger.warning("Participant %s disconnected unexpectedly. Triggering discard guard.", participant.identity)
            # Invoke discard guard
            abort_and_discard_session(db=None, session_id=session_id, reason=f"Participant {participant.identity} disconnected mid-session")

    # Wait for candidate
    participant = await ctx.wait_for_participant()
    logger.info("Candidate joined: %s (identity: %s)", participant.name, participant.identity)

    # Pre-Assignment Gate check
    assigned = get_user_assigned_questions.invoke({"user_id": participant.identity})
    if not assigned or not assigned.get("topics"):
        logger.error("Pre-Assignment Gate violation: Candidate %s has no active question bank.", participant.identity)
        await broadcast_datachannel_message(
            ctx.room,
            {
                "type": "error",
                "message": "Awaiting Admin Question Bank Assignment. Interview cannot start.",
            },
        )
        return

    logger.info("Candidate authorized with Bank: %s (%s)", assigned.get("title"), assigned.get("difficulty"))
    await broadcast_datachannel_message(
        ctx.room,
        {
            "type": "session_ready",
            "bank_title": assigned.get("title"),
            "difficulty": assigned.get("difficulty"),
            "topics_count": len(assigned.get("topics", [])),
        },
    )


def start_worker():
    """Starts the LiveKit Agent Worker process."""
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
        )
    )


if __name__ == "__main__":
    start_worker()
