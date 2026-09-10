import asyncio
import json
import logging
import os
from typing import Any
from livekit import rtc
from livekit.agents import AutoSubscribe, JobContext, JobProcess, WorkerOptions, cli
from src.agent.graphs.interview_exec import (
    ask_question_node,
    evaluate_answer_node,
    generate_final_evaluation_node,
    process_answer_node,
)
from src.agent.guard import abort_and_discard_session
from src.agent.state import InterviewExecutionState
from src.agent.tools.relational_fetchers import (
    _get_db_session_if_available,
    fetch_followups,
    fetch_questions,
    fetch_topics,
    get_user_assigned_questions,
)

logger = logging.getLogger("livekit_worker")
logging.basicConfig(level=logging.INFO)


async def broadcast_datachannel_message(room: rtc.Room, payload: dict[str, Any]) -> None:
    """Broadcasts a JSON packet over the native WebRTC DataChannel to connected candidates."""
    try:
        data_bytes = json.dumps(payload).encode("utf-8")
        await room.local_participant.publish_data(data_bytes, reliable=True)
    except Exception as exc:
        logger.error("Failed to broadcast DataChannel message: %s", exc)


def hydrate_bank_topics(assigned_bank: dict[str, Any]) -> list[dict[str, Any]]:
    """Hydrates all nested topics, questions, and follow-ups for the assigned bank."""
    bank_id = assigned_bank.get("bank_id", "")
    topics = fetch_topics.invoke({"bank_id": bank_id})
    hydrated = []
    for t in topics:
        q_list = fetch_questions.invoke({"topic_id": t["topic_id"]})
        hydrated_questions = []
        for q in q_list:
            f_list = fetch_followups.invoke({"question_id": q["question_id"]})
            q_copy = dict(q)
            q_copy["followups"] = f_list
            hydrated_questions.append(q_copy)
        t_copy = dict(t)
        t_copy["questions"] = hydrated_questions
        hydrated.append(t_copy)
    return hydrated


def process_candidate_turn(
    state: InterviewExecutionState,
    candidate_transcript: str,
) -> tuple[InterviewExecutionState, dict[str, Any]]:
    """
    Executes a single turn of candidate answer evaluation and updates state:
    1. Evaluates candidate answer keywords against rubric.
    2. Advances question / followup or triggers reask if score < 70%.
    3. Prepares next prompt or triggers conclusion.
    """
    state_copy = dict(state)
    state_copy["latest_transcript"] = candidate_transcript

    # 1. Evaluate
    eval_updates = evaluate_answer_node(state_copy)
    state_copy.update(eval_updates)

    last_turn = state_copy["turns"][-1]
    turn_packet = {
        "accuracy_score": last_turn["score"],
        "is_passed": last_turn["score"] >= 70.0,
        "is_reask": last_turn["turn_type"] == "reask",
        "matched_keywords": last_turn["rubric_hits"],
        "missed_keywords": last_turn["missed_keywords"],
        "feedback": f"Recorded score: {last_turn['score']:.1f}%",
    }

    # 2. Progress
    progression = process_answer_node(state_copy)
    state_copy.update(progression)

    # 3. Next prompt or final evaluation
    if state_copy.get("is_interview_concluded"):
        final_eval = generate_final_evaluation_node(state_copy)
        state_copy.update(final_eval)
    else:
        prompt_update = ask_question_node(state_copy)
        state_copy.update(prompt_update)

    return state_copy, turn_packet


async def entrypoint(ctx: JobContext):
    """Entrypoint invoked by LiveKit Server when candidate connects to a room."""
    logger.info("Connecting to LiveKit room: %s", ctx.room.name)
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)

    # Participant state
    session_id = ctx.room.name.replace("room-", "")
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

    # Hydrate full question tree
    hydrated_topics = hydrate_bank_topics(assigned)
    if not hydrated_topics:
        hydrated_topics = assigned.get("topics", [])

    logger.info("Candidate authorized with Bank: %s (%s)", assigned.get("title"), assigned.get("difficulty"))
    await broadcast_datachannel_message(
        ctx.room,
        {
            "type": "session_ready",
            "bank_title": assigned.get("title"),
            "difficulty": assigned.get("difficulty"),
            "topics_count": len(hydrated_topics),
        },
    )

    # Initialize execution state
    interview_state: InterviewExecutionState = {
        "topics": hydrated_topics,
        "current_topic_index": 0,
        "current_question_index": 0,
        "current_followup_index": 0,
        "attempt_count": 1,
        "is_reask_active": False,
        "is_interview_concluded": False,
        "current_prompt": "",
        "expected_keywords": [],
        "expected_time_to_ans": 45,
        "latest_transcript": "",
        "latest_score": 0.0,
        "turns": [],
        "overall_score": 0.0,
        "ukvi_recommendation": "",
        "final_report_json": "{}",
    }

    # Ask the first question
    prompt_updates = ask_question_node(interview_state)
    interview_state.update(prompt_updates)

    await broadcast_datachannel_message(
        ctx.room,
        {
            "type": "question",
            "prompt": interview_state["current_prompt"],
            "topic_name": hydrated_topics[0].get("name", "Topic 1") if hydrated_topics else "Topic 1",
            "expected_time_to_ans": interview_state["expected_time_to_ans"],
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
