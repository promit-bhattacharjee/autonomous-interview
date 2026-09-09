"""
Unit tests for Hierarchical State Management and Sequencing in interviewv2 (Pattern A).
Verifies:
1. Native nested tree cursor progression (Topic -> Question -> Follow-ups).
2. Re-ask derivation on failed attempt 1.
3. Automatic skipping of empty intermediate topics without premature termination.
4. Interview completion guard in InterviewSession.
"""
import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from pathlib import Path
src_path = str(Path(__file__).resolve().parent.parent / "src")
if src_path not in sys.path:
    sys.path.insert(0, src_path)

import unittest
from interview.state import (
    EvaluationRecord,
    FollowupItem,
    InterviewState,
    QuestionItem,
    TopicItem,
)
from interview.tools.question_helpers import (
    advance_turn,
    get_current_turn_target,
    is_current_turn_reask,
    get_next_relational_turn,
    is_active_turn_reask,
    get_active_turn_target,
)


class TestHierarchicalStateMachine(unittest.TestCase):
    def test_hierarchical_sequencing_flow(self):
        print("=" * 60)
        print("Testing Hierarchical State Management & Cursor Progression")
        print("=" * 60)

        # 1. Setup nested tree entities (Topic -> Questions -> Followups)
        topics = [
            TopicItem(
                id=1,
                name="Topic 1",
                expected_time_to_ans=60,
                questions=[
                    QuestionItem(
                        question="Q1 Primary",
                        difficulty="Medium",
                        expected_time_to_ans=45,
                        expected_answer_keywords=["k1", "k2"],
                        followups=[
                            FollowupItem(
                                followup_order=1,
                                followup="F1.1 Probe",
                                expected_time_to_ans=30,
                                expected_answer_keywords=["kf1"],
                            )
                        ],
                    ),
                    QuestionItem(
                        question="Q2 Standalone",
                        difficulty="Medium",
                        expected_time_to_ans=45,
                        expected_answer_keywords=["k3"],
                        followups=[],
                    ),
                ],
            ),
            TopicItem(
                id=2,
                name="Topic 2",
                expected_time_to_ans=60,
                questions=[
                    QuestionItem(
                        question="Q3 Primary",
                        difficulty="Medium",
                        expected_time_to_ans=45,
                        expected_answer_keywords=["k4"],
                        followups=[],
                    )
                ],
            ),
        ]

        # Initial state on Q1 Primary
        state: InterviewState = {
            "topics": topics,
            "current_topic_idx": 0,
            "current_question_idx": 0,
            "current_followup_idx": -1,
            "evaluations": [],
            "interview_status": "in_progress",
        }

        # Step A: Verify initial turn target
        q_text, keywords, topic_name, is_followup = get_current_turn_target(state)
        self.assertEqual(q_text, "Q1 Primary")
        self.assertEqual(keywords, ["k1", "k2"])
        self.assertEqual(topic_name, "Topic 1")
        self.assertFalse(is_followup)
        self.assertFalse(is_current_turn_reask(state))
        print("✅ Initial primary question lookup passed.")

        # Step B: Test Re-ask Derivation on failed attempt 1
        state["evaluations"].append(
            EvaluationRecord(
                topic_id=0,
                question_id=0,
                followup_order=None,
                turn_type="question",
                attempt_number=1,
                accuracy_score=50.0,
                is_passed=False,
            )
        )
        self.assertTrue(is_current_turn_reask(state))
        # When reask is True, advance_turn() should return {} (keep same cursor)
        update = advance_turn(state)
        self.assertEqual(update, {})
        print("✅ Re-ask derived as True on failed attempt 1; cursors maintained.")

        # Step C: Attempt 2 passed
        state["evaluations"].append(
            EvaluationRecord(
                topic_id=0,
                question_id=0,
                followup_order=None,
                turn_type="question",
                attempt_number=2,
                accuracy_score=75.0,
                is_passed=True,
            )
        )
        self.assertFalse(is_current_turn_reask(state))
        print("✅ Re-ask derived as False after attempt 2.")

        # Step D: Advance to Follow-up 1 (F1.1)
        update = advance_turn(state)
        self.assertEqual(update, {"current_followup_idx": 0})
        state.update(update)

        q_text, keywords, topic_name, is_followup = get_current_turn_target(state)
        self.assertEqual(q_text, "F1.1 Probe")
        self.assertEqual(keywords, ["kf1"])
        self.assertTrue(is_followup)
        print("✅ Advanced to follow-up probe 1.")

        # Simulate pass on follow-up
        state["evaluations"].append(
            EvaluationRecord(
                topic_id=0,
                question_id=0,
                followup_order=0,
                turn_type="suggested_followup",
                attempt_number=1,
                accuracy_score=80.0,
                is_passed=True,
            )
        )

        # Step E: Advance to Q2 in same topic
        update = advance_turn(state)
        self.assertEqual(update, {"current_question_idx": 1, "current_followup_idx": -1})
        state.update(update)

        q_text, keywords, topic_name, is_followup = get_current_turn_target(state)
        self.assertEqual(q_text, "Q2 Standalone")
        self.assertFalse(is_followup)
        print("✅ Advanced to Question 2 in Topic 1.")

        # Simulate pass on Q2
        state["evaluations"].append(
            EvaluationRecord(
                topic_id=0,
                question_id=1,
                followup_order=None,
                turn_type="question",
                attempt_number=1,
                accuracy_score=85.0,
                is_passed=True,
            )
        )

        # Step F: Advance across topics to Topic 2, Q3
        update = advance_turn(state)
        self.assertEqual(update, {"current_topic_idx": 1, "current_question_idx": 0, "current_followup_idx": -1})
        state.update(update)

        q_text, keywords, topic_name, is_followup = get_current_turn_target(state)
        self.assertEqual(q_text, "Q3 Primary")
        self.assertEqual(topic_name, "Topic 2")
        print("✅ Advanced across topics to Topic 2.")

        # Simulate pass on Q3
        state["evaluations"].append(
            EvaluationRecord(
                topic_id=1,
                question_id=0,
                followup_order=None,
                turn_type="question",
                attempt_number=1,
                accuracy_score=90.0,
                is_passed=True,
            )
        )

        # Step G: Conclude interview
        update = advance_turn(state)
        self.assertEqual(update, {"interview_status": "completed"})
        print("✅ Concluded interview when all topics and questions exhausted.")

    def test_skip_empty_intermediate_topic(self):
        """
        Verify that if an intermediate topic has no generated questions,
        the sequencer skips it and moves to the next topic with questions
        instead of prematurely concluding the interview.
        """
        topics = [
            TopicItem(
                id=1,
                name="Topic 1",
                questions=[QuestionItem(question="Q1", expected_answer_keywords=[])],
            ),
            TopicItem(
                id=2,
                name="Topic 2 (Empty)",
                questions=[],  # Topic 2 has no questions!
            ),
            TopicItem(
                id=3,
                name="Topic 3",
                questions=[QuestionItem(question="Q3", expected_answer_keywords=[])],
            ),
        ]
        state: InterviewState = {
            "topics": topics,
            "current_topic_idx": 0,
            "current_question_idx": 0,
            "current_followup_idx": -1,
            "evaluations": [],
            "interview_status": "in_progress",
        }

        # Finishing Q1 in Topic 1 must advance directly to Topic 3 (skipping empty Topic 2)
        update = advance_turn(state)
        self.assertEqual(update, {"current_topic_idx": 2, "current_question_idx": 0, "current_followup_idx": -1})
        state.update(update)

        q_text, _, topic_name, _ = get_current_turn_target(state)
        self.assertEqual(q_text, "Q3")
        self.assertEqual(topic_name, "Topic 3")
        print("✅ Successfully skipped empty Topic 2 and advanced to Topic 3 (Q3).")

    def test_completed_session_guard(self):
        """
        Verify that InterviewSession.submit_candidate_answer guards against
        re-evaluating or re-invoking the graph once marked completed.
        """
        from interview.service import InterviewSession
        session = InterviewSession()
        session.latest_state = {
            "interview_status": "completed",
            "messages": [],
            "final_evaluation": {"overall_score": 85.0, "overall_status": "PASSED"},
        }
        next_text, is_completed, eval_data = session.submit_candidate_answer("hello after end")
        self.assertTrue(is_completed)
        self.assertEqual(next_text, "")
        self.assertIn("final_evaluation", eval_data)
        print("✅ Completed session guard safely returned without graph invocation.")


if __name__ == "__main__":
    unittest.main()
