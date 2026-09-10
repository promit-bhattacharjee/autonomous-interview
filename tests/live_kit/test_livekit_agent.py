import asyncio
import json
import sys
from pathlib import Path
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

src_path = str(Path(__file__).resolve().parent.parent.parent / "src")
if src_path not in sys.path:
    sys.path.insert(0, src_path)

from langchain_core.messages import AIMessage
from livekit.agents import llm
from interview.live_kit.agent import InterviewAgent
from interview.live_kit.token_service import create_candidate_token
from interview.service import InterviewSession
from interview.state import FollowupItem, QuestionItem, TopicItem


class TestTokenService(unittest.TestCase):
    """Tests JWT access token generation and WebRTC video grant configurations."""

    def test_create_candidate_token_defaults(self):
        """Generates audio-only token for candidate with default devkey/secret."""
        token_str = create_candidate_token(
            room_name="test-room-101",
            candidate_id="cand-001",
            candidate_name="Alex Turner",
        )
        self.assertTrue(isinstance(token_str, str))
        self.assertTrue(len(token_str) > 20)

        # Verify JWT header and payload formatting
        import jwt
        decoded = jwt.decode(token_str, options={"verify_signature": False})
        self.assertEqual(decoded.get("sub"), "cand-001")
        self.assertEqual(decoded.get("name"), "Alex Turner")
        video_grants = decoded.get("video", {})
        self.assertTrue(video_grants.get("roomJoin"))
        self.assertEqual(video_grants.get("room"), "test-room-101")
        self.assertTrue(video_grants.get("canPublish"))
        self.assertTrue(video_grants.get("canSubscribe"))
        self.assertEqual(video_grants.get("canPublishSources"), ["microphone"])


class TestInterviewAgentLifecycle(unittest.IsolatedAsyncioTestCase):
    """Asynchronous unit tests for InterviewAgent turn handling and WebRTC data broadcast."""

    async def asyncSetUp(self):
        self.mock_session = MagicMock(spec=InterviewSession)
        self.mock_voice_session = MagicMock()
        
        async def _mock_speech():
            return None
        self.mock_voice_session.say.side_effect = lambda *a, **kw: _mock_speech()

        self.mock_room = MagicMock()
        self.mock_local_participant = MagicMock()
        self.mock_local_participant.publish_data = AsyncMock()
        self.mock_room.local_participant = self.mock_local_participant
        self.mock_room.disconnect = AsyncMock()

        self.agent = InterviewAgent(
            interview_session=self.mock_session,
            voice_session=self.mock_voice_session,
            room=self.mock_room,
        )

    async def test_agent_initialization(self):
        """Agent initializes with required state machine, voice session, and locks."""
        self.assertIs(self.agent.interview_session, self.mock_session)
        self.assertIs(self.agent.voice_session, self.mock_voice_session)
        self.assertIs(self.agent.room, self.mock_room)
        self.assertFalse(self.agent.is_interview_concluded)
        self.assertTrue(isinstance(self.agent.turn_lock, asyncio.Lock))

    async def test_user_turn_completed_passing_answer(self):
        """Processes passing turn, broadcasts evaluation over data channel, and speaks next question."""
        eval_payload = {
            "accuracy_score": 88.0,
            "is_passed": True,
            "is_reask": False,
            "matched_keywords": ["PyTorch", "AI"],
            "feedback": "Strong technical answer",
        }
        self.mock_session.submit_candidate_answer.return_value = (
            "Great answer. Moving on to question 2.",
            False,
            eval_payload,
        )

        turn_ctx = MagicMock(spec=llm.ChatContext)
        user_msg = llm.ChatMessage(role="user", content=["I have extensive experience with PyTorch and AI."])

        await self.agent.on_user_turn_completed(turn_ctx, user_msg)

        # 1. Brain called with candidate transcript
        self.mock_session.submit_candidate_answer.assert_called_once_with(
            "I have extensive experience with PyTorch and AI."
        )

        # 2. Data channel published with evaluation JSON
        self.mock_local_participant.publish_data.assert_called_once()
        published_bytes = self.mock_local_participant.publish_data.call_args[0][0]
        published_data = json.loads(published_bytes.decode("utf-8"))
        self.assertEqual(published_data["accuracy_score"], 88.0)
        self.assertTrue(published_data["is_passed"])

        # 3. Voice synthesizer called
        self.mock_voice_session.say.assert_called_once_with("Great answer. Moving on to question 2.")
        self.assertFalse(self.agent.is_interview_concluded)
        self.mock_room.disconnect.assert_not_called()

    async def test_user_turn_completed_reask_failing_answer(self):
        """Processes weak answer on attempt 1, publishing is_reask=True and speaking re-ask prompt."""
        eval_payload = {
            "accuracy_score": 35.0,
            "is_passed": False,
            "is_reask": True,
            "matched_keywords": [],
            "unmatched_keywords": ["Tuition", "28-day rule"],
            "feedback": "Missed tuition and 28-day rule explanation.",
        }
        self.mock_session.submit_candidate_answer.return_value = (
            "Could you elaborate on the exact tuition and the 28-day rule?",
            False,
            eval_payload,
        )

        turn_ctx = MagicMock(spec=llm.ChatContext)
        user_msg = llm.ChatMessage(role="user", content=["I will pay my fees."])

        await self.agent.on_user_turn_completed(turn_ctx, user_msg)

        self.mock_local_participant.publish_data.assert_called_once()
        published_data = json.loads(self.mock_local_participant.publish_data.call_args[0][0].decode("utf-8"))
        self.assertTrue(published_data["is_reask"])
        self.assertFalse(published_data["is_passed"])
        self.mock_voice_session.say.assert_called_once_with(
            "Could you elaborate on the exact tuition and the 28-day rule?"
        )
        self.assertFalse(self.agent.is_interview_concluded)

    async def test_user_turn_completed_conclusion_and_disconnect(self):
        """When interview concludes, speaks closing remarks, flags concluded, and disconnects room."""
        eval_payload = {
            "accuracy_score": 92.0,
            "is_passed": True,
            "is_reask": False,
        }
        self.mock_session.submit_candidate_answer.return_value = (
            "Thank you. This concludes your UKVI credibility interview.",
            True,
            eval_payload,
        )

        turn_ctx = MagicMock(spec=llm.ChatContext)
        user_msg = llm.ChatMessage(role="user", content=["I plan to return to India after my graduation."])

        with patch("asyncio.sleep", new_callable=AsyncMock):
            await self.agent.on_user_turn_completed(turn_ctx, user_msg)

        self.assertTrue(self.agent.is_interview_concluded)
        self.mock_voice_session.say.assert_called_once_with(
            "Thank you. This concludes your UKVI credibility interview."
        )
        self.mock_room.disconnect.assert_called_once()

    async def test_user_turn_completed_empty_speech_ignored(self):
        """Ignores empty or whitespace-only transcriptions without invoking session or publishing data."""
        turn_ctx = MagicMock(spec=llm.ChatContext)
        user_msg = llm.ChatMessage(role="user", content=["   "])

        await self.agent.on_user_turn_completed(turn_ctx, user_msg)

        self.mock_session.submit_candidate_answer.assert_not_called()
        self.mock_local_participant.publish_data.assert_not_called()
        self.mock_voice_session.say.assert_not_called()

    async def test_user_turn_completed_after_concluded_ignored(self):
        """Drops audio turns once the interview has concluded."""
        self.agent.is_interview_concluded = True
        turn_ctx = MagicMock(spec=llm.ChatContext)
        user_msg = llm.ChatMessage(role="user", content=["Hello? Anyone there?"])

        await self.agent.on_user_turn_completed(turn_ctx, user_msg)

        self.mock_session.submit_candidate_answer.assert_not_called()
        self.mock_local_participant.publish_data.assert_not_called()
        self.mock_voice_session.say.assert_not_called()

    async def test_data_channel_publish_exception_handled_gracefully(self):
        """Catches and handles WebRTC data channel errors without interrupting conversation."""
        self.mock_local_participant.publish_data.side_effect = RuntimeError("Data channel closed")
        self.mock_session.submit_candidate_answer.return_value = (
            "Next question please.",
            False,
            {"accuracy_score": 80.0, "is_passed": True},
        )

        turn_ctx = MagicMock(spec=llm.ChatContext)
        user_msg = llm.ChatMessage(role="user", content=["Answer text."])

        # Must not raise RuntimeError
        await self.agent.on_user_turn_completed(turn_ctx, user_msg)

        self.mock_voice_session.say.assert_called_once_with("Next question please.")


class TestNestedTreeLiveKitMultiTurnScenarios(unittest.IsolatedAsyncioTestCase):
    """
    Comprehensive multi-scenario simulation testing candidate journeys
    through the LiveKit agent turn handler using the Nested Tree Architecture.
    """

    async def asyncSetUp(self):
        self.mock_voice_session = MagicMock()
        async def _mock_speech():
            return None
        self.mock_voice_session.say.side_effect = lambda *a, **kw: _mock_speech()

        self.mock_room = MagicMock()
        self.mock_local_participant = MagicMock()
        self.mock_local_participant.publish_data = AsyncMock()
        self.mock_room.local_participant = self.mock_local_participant
        self.mock_room.disconnect = AsyncMock()

    @patch("interview.service.interview_graph")
    async def test_scenario_top_student_smooth_progression(self, mock_graph):
        """
        Scenario 1: High-performing student answers primary question and follow-up cleanly.
        Verifies 2 consecutive turns via InterviewSession through LiveKit agent.
        """
        topics = [
            TopicItem(
                id=1,
                name="Academic Fit",
                expected_time_to_ans=45,
                questions=[
                    QuestionItem(
                        question="Why MSc AI?",
                        expected_answer_keywords=["Machine Learning"],
                        followups=[
                            FollowupItem(
                                followup_order=1,
                                followup="What are your career ambitions with AI?",
                                expected_answer_keywords=["Robotics"],
                            )
                        ],
                    )
                ],
            )
        ]

        # Mock graph multi-turn responses
        # Turn 1 response (Answer to Q1 -> asks Follow-up)
        turn_1_state = {
            "interview_status": "in_progress",
            "evaluations": [
                MagicMock(accuracy_score=90.0, is_passed=True, matched_keywords=["Machine Learning"], unmatched_keywords=[])
            ],
            "messages": [AIMessage(content="What are your career ambitions with AI?")],
        }
        # Turn 2 response (Answer to Follow-up -> concludes)
        turn_2_state = {
            "interview_status": "completed",
            "evaluations": [
                MagicMock(accuracy_score=90.0, is_passed=True, matched_keywords=["Machine Learning"], unmatched_keywords=[]),
                MagicMock(accuracy_score=95.0, is_passed=True, matched_keywords=["Robotics"], unmatched_keywords=[]),
            ],
            "messages": [AIMessage(content="Thank you for your time today.")],
        }

        mock_graph.invoke.side_effect = [turn_1_state, turn_2_state]

        session = InterviewSession(topics=topics)
        session.latest_state = {
            "topics": topics,
            "current_topic_idx": 0,
            "current_question_idx": 0,
            "current_followup_idx": -1,
            "interview_status": "in_progress",
            "evaluations": [],
            "messages": [AIMessage(content="Why MSc AI?")],
        }

        agent = InterviewAgent(
            interview_session=session,
            voice_session=self.mock_voice_session,
            room=self.mock_room,
        )

        turn_ctx = MagicMock(spec=llm.ChatContext)

        # Turn 1: Candidate answers Q1
        msg1 = llm.ChatMessage(role="user", content=["I love Machine Learning."])
        await agent.on_user_turn_completed(turn_ctx, msg1)

        self.assertFalse(agent.is_interview_concluded)
        self.mock_voice_session.say.assert_called_with("What are your career ambitions with AI?")

        # Turn 2: Candidate answers Follow-up
        session.latest_state["current_followup_idx"] = 0
        session.latest_state["messages"].append(AIMessage(content="What are your career ambitions with AI?"))
        msg2 = llm.ChatMessage(role="user", content=["I want to work in Robotics."])

        with patch("asyncio.sleep", new_callable=AsyncMock):
            await agent.on_user_turn_completed(turn_ctx, msg2)

        self.assertTrue(agent.is_interview_concluded)
        self.mock_voice_session.say.assert_called_with("Thank you for your time today.")
        self.mock_room.disconnect.assert_called_once()

    @patch("interview.service.interview_graph")
    async def test_scenario_struggling_student_reask_progression(self, mock_graph):
        """
        Scenario 2: Candidate struggles on Turn 1 (scores 30% -> re-ask triggered),
        then succeeds on Attempt 2 (scores 85% -> progresses).
        """
        topics = [
            TopicItem(
                id=1,
                name="Financial Capability",
                expected_time_to_ans=45,
                questions=[
                    QuestionItem(
                        question="How do you satisfy the 28-day maintenance requirement?",
                        expected_answer_keywords=["28-day rule", "12500"],
                        followups=[],
                    )
                ],
            )
        ]

        # Turn 1: Failed attempt 1 -> re-ask state
        turn_1_state = {
            "interview_status": "in_progress",
            "evaluations": [
                MagicMock(accuracy_score=30.0, is_passed=False, matched_keywords=[], unmatched_keywords=["28-day rule"])
            ],
            "messages": [AIMessage(content="Could you please explain how long the funds were in your account?")],
        }

        # Turn 2: Passed attempt 2 -> completed
        turn_2_state = {
            "interview_status": "completed",
            "evaluations": [
                MagicMock(accuracy_score=30.0, is_passed=False, matched_keywords=[], unmatched_keywords=["28-day rule"]),
                MagicMock(accuracy_score=85.0, is_passed=True, matched_keywords=["28-day rule", "12500"], unmatched_keywords=[]),
            ],
            "messages": [AIMessage(content="Thank you, interview complete.")],
        }

        mock_graph.invoke.side_effect = [turn_1_state, turn_2_state]

        session = InterviewSession(topics=topics)
        session.latest_state = {
            "topics": topics,
            "current_topic_idx": 0,
            "current_question_idx": 0,
            "current_followup_idx": -1,
            "interview_status": "in_progress",
            "evaluations": [],
            "messages": [AIMessage(content="How do you satisfy the 28-day maintenance requirement?")],
        }

        agent = InterviewAgent(
            interview_session=session,
            voice_session=self.mock_voice_session,
            room=self.mock_room,
        )

        turn_ctx = MagicMock(spec=llm.ChatContext)

        # Candidate fails Turn 1
        msg1 = llm.ChatMessage(role="user", content=["My father has money."])
        await agent.on_user_turn_completed(turn_ctx, msg1)

        self.assertFalse(agent.is_interview_concluded)
        self.mock_voice_session.say.assert_called_with(
            "Could you please explain how long the funds were in your account?"
        )

        # Candidate succeeds on Attempt 2
        msg2 = llm.ChatMessage(role="user", content=["The 12500 funds were held for 30 days, meeting the 28-day rule."])
        with patch("asyncio.sleep", new_callable=AsyncMock):
            await agent.on_user_turn_completed(turn_ctx, msg2)

        self.assertTrue(agent.is_interview_concluded)
        self.mock_voice_session.say.assert_called_with("Thank you, interview complete.")
        self.mock_room.disconnect.assert_called_once()


if __name__ == "__main__":
    unittest.main()
