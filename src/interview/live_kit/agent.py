import asyncio
import json
import logging
import os
import sys

# Ensure Windows terminal outputs UTF-8 cleanly
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from dotenv import load_dotenv
from pathlib import Path

# Ensure src path is always accessible when run directly
src_path = str(Path(__file__).resolve().parent.parent.parent)
if src_path not in sys.path:
    sys.path.insert(0, src_path)
from livekit import rtc
from livekit.agents import (
    AutoSubscribe,
    JobContext,
    WorkerOptions,
    cli,
    llm,
    tts,
)
from livekit.agents.voice import Agent, AgentSession
from livekit.plugins import silero
from livekit.plugins.google.beta import GeminiSTT, GeminiTTS

from interview.service import InterviewSession
from interview.tools import print_interview_state_debug

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("livekit-audio-communicator")


class InterviewAgent(Agent):
    """
    Subclasses LiveKit Voice Agent to integrate LangGraph turn-by-turn brain
    into the native LiveKit turn completion lifecycle.
    Prevents intermediate STT chunk races and guarantees single-turn sequencing.
    """

    def __init__(
        self,
        interview_session: InterviewSession,
        voice_session: AgentSession,
        room: rtc.Room,
        instructions: str = "You are an autonomous UK university credibility and academic interviewer.",
        **kwargs,
    ):
        super().__init__(instructions=instructions, **kwargs)
        self.interview_session = interview_session
        self.voice_session = voice_session
        self.room = room
        self.turn_lock = asyncio.Lock()
        self.is_interview_concluded = False

    async def on_user_turn_completed(
        self, turn_ctx: llm.ChatContext, new_message: llm.ChatMessage
    ) -> None:
        """
        Invoked exclusively when VAD and TurnDetector confirm the candidate
        has finished their complete turn. Replaces low-level chunk listening.
        """
        if self.is_interview_concluded:
            return

        candidate_text = (new_message.text_content or "").strip() if new_message else ""
        if not candidate_text:
            return

        async with self.turn_lock:
            if self.is_interview_concluded:
                return

            logger.info(f"\n[Candidate Voice Transcribed]: {candidate_text}")

            # Run synchronous LangGraph brain execution in thread pool to prevent blocking WebRTC loop
            next_text, is_done, eval_data = await asyncio.to_thread(
                self.interview_session.submit_candidate_answer, candidate_text
            )

            # Broadcast live evaluation metrics over WebRTC Data Channel for frontend UI scorecards
            if eval_data:
                logger.info(
                    f"[Evaluation] Score: {eval_data.get('accuracy_score', 0):.1f}% | "
                    f"Passed: {eval_data.get('is_passed', False)} | "
                    f"Re-ask: {eval_data.get('is_reask', False)}"
                )
                try:
                    await self.room.local_participant.publish_data(
                        json.dumps(eval_data).encode("utf-8")
                    )
                except Exception as e:
                    logger.debug(f"Data channel publish skipped: {e}")

            if next_text:
                logger.info(f"[Interviewer Response]: {next_text}\n")
                speech_handle = self.voice_session.say(next_text)
                if speech_handle is not None and (asyncio.iscoroutine(speech_handle) or hasattr(speech_handle, "__await__")):
                    await speech_handle

            if is_done:
                self.is_interview_concluded = True
                logger.info("Interview concluded. Generating final evaluation report...")
                final_eval = self.interview_session.get_final_evaluation()
                if final_eval:
                    # Broadcast final scorecard to frontend via WebRTC DataChannel
                    try:
                        final_data_channel_payload = {
                            "type": "final_evaluation",
                            "final_evaluation": final_eval,
                        }
                        await self.room.local_participant.publish_data(
                            json.dumps(final_data_channel_payload).encode("utf-8")
                        )
                    except Exception as dc_err:
                        logger.debug(f"Failed to emit final eval over data channel: {dc_err}")

                    try:
                        from main import print_final_evaluation_report
                        print_final_evaluation_report(final_eval)
                    except Exception as eval_err:
                        logger.debug(f"Failed to print final report: {eval_err}")
                await asyncio.sleep(1.0)
                try:
                    await self.room.disconnect()
                except Exception as e:
                    logger.debug(f"Room disconnect error: {e}")


async def entrypoint(ctx: JobContext):
    """
    LiveKit Pure Audio Communicator Entrypoint:
    - Ear: Silero VAD + Gemini STT converts candidate voice to text.
    - Brain: InterviewSession (LangGraph) evaluates and formulates the next question.
    - Mouth: StreamAdapter + Gemini TTS converts question text into audio over WebRTC.
    """
    # 1. Connect to LiveKit Room (Audio Only)
    logger.info(f"Connecting audio communicator to room: {ctx.room.name}")
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)

    # 2. Wait for candidate to connect their microphone (skip in simulated console mode)
    is_console = getattr(ctx.job, "fake_job", False)
    if not is_console:
        logger.info("Waiting for candidate participant to join...")
        participant = await ctx.wait_for_participant()
        logger.info(f"Candidate connected: {participant.identity} ({participant.name})")
    else:
        logger.info("Console audio mode active - listening to local microphone and speaker.")

    # 3. Initialize the isolated InterviewSession (The Brain)
    # Check if this room has an existing session created via FastAPI
    try:
        from interview.api.session_store import default_session_store
        session_entry = default_session_store.get_session_by_room(ctx.room.name)
        if session_entry and session_entry.interview_session:
            interview_session = session_entry.interview_session
        else:
            interview_session = InterviewSession(session_id=ctx.room.name)
    except Exception:
        interview_session = InterviewSession(session_id=ctx.room.name)

    # 4. Configure Audio Communicator (Ear = Gemini STT, Mouth = Gemini TTS via StreamAdapter)
    gemini_tts = GeminiTTS(
        voice_name="Aoede",
        instructions="Speak clearly, warmly, and at a measured pace like a professional UK university interviewer.",
    )
    streaming_tts = tts.StreamAdapter(tts=gemini_tts)
    voice_session = AgentSession()

    agent = InterviewAgent(
        interview_session=interview_session,
        voice_session=voice_session,
        room=ctx.room,
        instructions="You are an autonomous UK university credibility and academic interviewer. Ask questions clearly and concisely.",
        vad=silero.VAD.load(),
        stt=GeminiSTT(language="en-US"),
        tts=streaming_tts,
    )

    # 5. Generate Question 1 & Start Voice Session
    logger.info("Generating Question 1 from student profile & rubric...")
    first_question = await asyncio.to_thread(interview_session.start)

    # Output detailed debug state breakdown to terminal for inspection
    print_interview_state_debug(interview_session.latest_state)

    # Debug Breakpoint (Disabled by default for full live voice interview)
    # Set BREAKPOINT_AFTER_QUESTION_GEN=true in .env to disconnect after initial question inspection
    breakpoint_enabled = os.getenv("BREAKPOINT_AFTER_QUESTION_GEN", "false").lower() in ("true", "1", "yes")
    if breakpoint_enabled:
        print("\n" + "=" * 80)
        print("🛑 [TESTING BREAKPOINT HIT]")
        print("   Question generation, rubrics, and state have been output above.")
        print("   Disconnecting the live voice interview session as requested for debugging.")
        print("=" * 80 + "\n")
        try:
            await ctx.room.disconnect()
        except Exception:
            pass
        return

    await voice_session.start(agent, room=ctx.room)
    logger.info(f"Interviewer asks Question 1: {first_question}")
    speech_handle = voice_session.say(first_question)
    await speech_handle


if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))
