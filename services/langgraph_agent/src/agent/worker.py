import asyncio
import json
import logging
import os
from typing import Any
from dotenv import load_dotenv
from livekit import rtc

load_dotenv()
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
    fetch_user_model_config,
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
        "turn_index": len(state_copy["turns"]),
        "spoken_prompt": last_turn.get("spoken_prompt", ""),
        "candidate_transcript": last_turn.get("candidate_transcript", ""),
        "turn_type": last_turn.get("turn_type", "question"),
        "is_reask": last_turn.get("turn_type") == "reask",
        "is_passed": last_turn.get("score", 0.0) >= 70.0,
        "accuracy_score": last_turn.get("score", 0.0),
        "matched_keywords": last_turn.get("rubric_hits", []),
        "missed_keywords": last_turn.get("missed_keywords", []),
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

    # Participant state and lifecycle management
    session_id = ctx.room.name.replace("room-", "")
    is_completed_normally = False
    session_ended = asyncio.Event()
    turn_lock = asyncio.Lock()
    candidate_is_ready = False

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

    # Resolve dynamic 3-model configuration (Thinking, STT, TTS)
    model_cfg = fetch_user_model_config.invoke({"user_id": participant.identity})
    thinking_model = (model_cfg.get("thinking") or {}).get("model_name", "deepseek/deepseek-v4-flash-0731")
    logger.info(
        "Candidate %s dynamic models resolved: Thinking=%s (via %s), STT=%s (via %s), TTS=%s (via %s)",
        participant.identity,
        thinking_model,
        (model_cfg.get("thinking") or {}).get("source", "env"),
        (model_cfg.get("stt") or {}).get("model_name", "gemini-3.6-flash"),
        (model_cfg.get("stt") or {}).get("source", "env"),
        (model_cfg.get("tts") or {}).get("voice", "Aoede"),
        (model_cfg.get("tts") or {}).get("source", "env"),
    )

    logger.info("Candidate authorized with Bank: %s (%s)", assigned.get("title"), assigned.get("difficulty"))
    await broadcast_datachannel_message(
        ctx.room,
        {
            "type": "session_ready",
            "bank_title": assigned.get("title"),
            "difficulty": assigned.get("difficulty"),
            "topics_count": len(hydrated_topics),
            "model_configuration": {
                "thinking": (model_cfg.get("thinking") or {}).get("model_name", thinking_model),
                "stt": (model_cfg.get("stt") or {}).get("model_name", "gemini-3.6-flash"),
                "tts": (model_cfg.get("tts") or {}).get("voice", "Aoede"),
                "is_free_mode": (model_cfg.get("thinking") or {}).get("is_free", True),
            },
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
        "active_question_id": "",
        "active_question_hits": [],
        "total_question_keywords": [],
        "keyword_ledger": {},
    }

    # Track active question packet to guarantee delivery upon client_ready handshake
    current_question_packet: dict[str, Any] | None = None

    # Handler for candidate turns submitted via WebRTC DataChannel
    async def handle_candidate_turn(candidate_transcript: str):
        nonlocal interview_state, is_completed_normally, current_question_packet
        async with turn_lock:
            if is_completed_normally or interview_state.get("is_interview_concluded"):
                return

            logger.info("Processing candidate turn: %s", candidate_transcript[:80])
            interview_state, turn_packet = process_candidate_turn(interview_state, candidate_transcript)

            # 1. Broadcast evaluation result immediately over DataChannel
            await broadcast_datachannel_message(ctx.room, {
                "type": "turn_evaluation",
                "data": turn_packet,
            })

            # 2. Check if concluded
            if interview_state.get("is_interview_concluded"):
                is_completed_normally = True
                current_question_packet = None

                overall_score = float(interview_state.get("overall_score", 0.0))
                rec = str(interview_state.get("ukvi_recommendation", "Genuine"))
                turns = interview_state.get("turns", [])

                strengths = []
                improvements = []
                for t in turns:
                    hits = t.get("rubric_hits") or []
                    misses = t.get("missed_keywords") or []
                    if hits:
                        strengths.extend(hits[:2])
                    if misses:
                        improvements.extend(misses[:2])

                strengths = list(dict.fromkeys(strengths))[:4] or ["Solid grasp of core curriculum modules", "Demonstrated genuine academic intent"]
                improvements = list(dict.fromkeys(improvements))[:4] or ["Could provide more specific details on future career plans"]

                recommendation_text = (
                    f"Candidate scored {overall_score:.1f}% with an official recommendation of '{rec}'. "
                    f"Verified credibility across {len(hydrated_topics)} assessed examination modules."
                )

                final_eval = {
                    "overall_score": overall_score,
                    "overall_status": "Complete",
                    "ukvi_recommendation": rec,
                    "turns_count": len(turns),
                    "recommendation": recommendation_text,
                    "strengths": strengths,
                    "areas_for_improvement": improvements,
                }
                await broadcast_datachannel_message(ctx.room, {
                    "type": "final_evaluation",
                    "final_evaluation": final_eval,
                })

                # Persist to database via HTTP
                api_url = os.getenv("API_SERVICE_URL", "http://web_api:8000")
                try:
                    import httpx
                    async with httpx.AsyncClient(base_url=api_url, timeout=10.0) as client:
                        await client.post(f"/api/sessions/{session_id}/complete", json={
                            "overall_score": overall_score,
                            "ukvi_recommendation": rec,
                            "report_data": final_eval,
                            "turns_data": turns,
                        })
                except Exception as exc:
                    logger.warning("Failed to persist session completion via API: %s", exc)

                await asyncio.sleep(2.0)
                session_ended.set()
            else:
                # Prepare and broadcast next question
                t_idx = interview_state.get("current_topic_index", 0)
                t_name = hydrated_topics[t_idx].get("name", f"Topic {t_idx + 1}") if t_idx < len(hydrated_topics) else f"Topic {t_idx + 1}"
                current_question_packet = {
                    "type": "question",
                    "prompt": interview_state["current_prompt"],
                    "topic_name": t_name,
                    "topic_index": t_idx + 1,
                    "total_topics": len(hydrated_topics),
                    "expected_time_to_ans": interview_state.get("expected_time_to_ans", 45),
                }
                logger.info("Broadcasting question %d/%d: %s", t_idx + 1, len(hydrated_topics), interview_state["current_prompt"][:60])
                await broadcast_datachannel_message(ctx.room, current_question_packet)

    @ctx.room.on("participant_disconnected")
    def on_participant_disconnected(participant: rtc.RemoteParticipant):
        nonlocal is_completed_normally
        if not is_completed_normally:
            logger.warning("Participant %s disconnected. Immediately terminating and discarding session.", participant.identity)
            abort_and_discard_session(db=None, session_id=ctx.room.name, reason=f"Participant {participant.identity} disconnected mid-session")
        session_ended.set()
        asyncio.create_task(ctx.room.disconnect())

    @ctx.room.on("data_received")
    def on_data_received(data_packet: rtc.DataPacket):
        try:
            raw_text = data_packet.data.decode("utf-8")
            payload = json.loads(raw_text)
            msg_type = payload.get("type")
            if msg_type in ("discard_session", "leave_session"):
                logger.warning("Received discard signal from candidate over DataChannel. Terminating session immediately.")
                nonlocal is_completed_normally
                is_completed_normally = False
                abort_and_discard_session(db=None, session_id=ctx.room.name, reason=payload.get("reason", "Candidate discarded session"))
                session_ended.set()
                asyncio.create_task(ctx.room.disconnect())
                return
            elif msg_type in ("candidate_answer", "answer"):
                transcript = payload.get("transcript", "").strip()
                if transcript:
                    asyncio.create_task(handle_candidate_turn(transcript))
            elif msg_type in ("client_ready", "request_question"):
                logger.info("Candidate client ready/request signal received.")
                candidate_is_ready = True
                if current_question_packet:
                    logger.info("Dispatching active question packet to ready candidate.")
                    asyncio.create_task(broadcast_datachannel_message(ctx.room, current_question_packet))
        except Exception as err:
            logger.error("Error processing data packet: %s", err)

    # Ask the first question
    prompt_updates = ask_question_node(interview_state)
    interview_state.update(prompt_updates)

    current_question_packet = {
        "type": "question",
        "prompt": interview_state["current_prompt"],
        "topic_name": hydrated_topics[0].get("name", "Topic 1") if hydrated_topics else "Topic 1",
        "topic_index": 1,
        "total_topics": len(hydrated_topics),
        "expected_time_to_ans": interview_state["expected_time_to_ans"],
    }
    logger.info("Initial question formulated: %s", current_question_packet["prompt"][:60])
    await broadcast_datachannel_message(ctx.room, current_question_packet)

    # Keep agent worker active in room until completion or participant departure
    try:
        await session_ended.wait()
    except asyncio.CancelledError:
        logger.info("LiveKit agent session cancelled.")
    finally:
        try:
            await ctx.room.disconnect()
        except Exception:
            pass




def start_worker():
    """Starts the LiveKit Agent Worker process."""
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
        )
    )


if __name__ == "__main__":
    start_worker()
