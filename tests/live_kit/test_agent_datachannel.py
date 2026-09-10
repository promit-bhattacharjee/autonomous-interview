import asyncio
import json
import sys
from pathlib import Path
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

src_path = str(Path(__file__).resolve().parent.parent.parent / "src")
if src_path not in sys.path:
    sys.path.insert(0, src_path)

from livekit.agents import llm
from interview.api.session_store import default_session_store
from interview.live_kit.agent import InterviewAgent
from interview.service import InterviewSession


class TestAgentDataChannel(unittest.IsolatedAsyncioTestCase):
    """
    Validates WebRTC Data Channel broadcasts from the LiveKit Agent.
    Confirms that client receives real-time scorecards and reports directly over WebRTC,
    eliminating any need for custom WebSockets.
    """

    async def asyncSetUp(self):
        default_session_store.clear()
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

    async def asyncTearDown(self):
        default_session_store.clear()

    async def test_turn_evaluation_broadcasts_over_datachannel(self):
        """Emits structured evaluation metrics over WebRTC Data Channel on each answer."""
        eval_payload = {
            "accuracy_score": 92.5,
            "is_passed": True,
            "is_reask": False,
            "attempt_number": 1,
            "matched_keywords": ["Artificial Intelligence", "Robotics"],
            "unmatched_keywords": [],
            "feedback": "Flawless technical articulation.",
        }
        self.mock_session.submit_candidate_answer.return_value = (
            "Excellent. Let's discuss your financial sponsorship.",
            False,
            eval_payload,
        )

        turn_ctx = MagicMock(spec=llm.ChatContext)
        user_msg = llm.ChatMessage(
            role="user",
            content=["I have studied Artificial Intelligence and built robotics systems."],
        )

        await self.agent.on_user_turn_completed(turn_ctx, user_msg)

        # Confirm data channel publish_data was called
        self.mock_local_participant.publish_data.assert_called()
        call_args = self.mock_local_participant.publish_data.call_args[0][0]
        data = json.loads(call_args.decode("utf-8"))

        self.assertEqual(data.get("accuracy_score"), 92.5)
        self.assertTrue(data.get("is_passed"))
        self.assertFalse(data.get("is_reask"))
        self.assertIn("Robotics", data.get("matched_keywords"))

    async def test_reask_signal_broadcasts_over_datachannel(self):
        """Signals is_reask=True over WebRTC Data Channel when score is below 70% on attempt 1."""
        reask_eval_payload = {
            "accuracy_score": 45.0,
            "is_passed": False,
            "is_reask": True,
            "attempt_number": 1,
            "matched_keywords": [],
            "unmatched_keywords": ["living costs", "funds held 28 days"],
            "feedback": "Answer lacked financial specifics.",
        }
        self.mock_session.submit_candidate_answer.return_value = (
            "Could you clarify the living costs and how long funds have been held?",
            False,
            reask_eval_payload,
        )

        turn_ctx = MagicMock(spec=llm.ChatContext)
        user_msg = llm.ChatMessage(
            role="user",
            content=["My parents are sponsoring my studies."],
        )

        await self.agent.on_user_turn_completed(turn_ctx, user_msg)

        # Assert data channel packet contains reask flag
        call_args = self.mock_local_participant.publish_data.call_args[0][0]
        data = json.loads(call_args.decode("utf-8"))
        self.assertEqual(data.get("accuracy_score"), 45.0)
        self.assertFalse(data.get("is_passed"))
        self.assertTrue(data.get("is_reask"))

    async def test_final_evaluation_broadcasts_on_conclusion(self):
        """Broadcasts complete final UKVI evaluation report over WebRTC Data Channel when interview concludes."""
        turn_eval_payload = {
            "accuracy_score": 85.0,
            "is_passed": True,
            "is_reask": False,
        }
        final_report = {
            "overall_score": 88.5,
            "overall_status": "PASSED",
            "recommendation": "Candidate demonstrated full credibility and academic preparedness for UKVI visa sponsorship.",
            "topic_breakdown": [],
            "strengths": ["Clear academic trajectory", "Strong financial backing"],
            "areas_for_improvement": [],
        }
        self.mock_session.submit_candidate_answer.return_value = (
            "Thank you. That concludes our interview.",
            True,  # is_done = True
            turn_eval_payload,
        )
        self.mock_session.get_final_evaluation.return_value = final_report

        turn_ctx = MagicMock(spec=llm.ChatContext)
        user_msg = llm.ChatMessage(
            role="user",
            content=["After graduation, I plan to return home to lead an AI engineering team."],
        )

        await self.agent.on_user_turn_completed(turn_ctx, user_msg)

        # Check published calls: 1st for turn eval, 2nd for final eval
        self.assertEqual(self.mock_local_participant.publish_data.call_count, 2)
        final_call_args = self.mock_local_participant.publish_data.call_args_list[1][0][0]
        data = json.loads(final_call_args.decode("utf-8"))

        self.assertEqual(data.get("type"), "final_evaluation")
        self.assertEqual(data.get("final_evaluation", {}).get("overall_status"), "PASSED")
        self.assertEqual(data.get("final_evaluation", {}).get("overall_score"), 88.5)
        self.assertTrue(self.agent.is_interview_concluded)
        self.mock_room.disconnect.assert_called_once()
