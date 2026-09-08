"""
Unit tests for the Relational State Management and Sequencing in interviewv2.
"""
import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from interview.state import (
    EvaluationRecord,
    InterviewState,
    QuestionState,
    SuggestedFollowupState,
    TopicState,
)
from interview.tools.question_helpers import (
    get_active_followup,
    get_active_question,
    get_active_topic,
    get_next_relational_turn,
    is_active_turn_followup,
    is_active_turn_reask,
)


import unittest


class TestRelationalStateMachine(unittest.TestCase):
    def test_relational_state_machine(self):
        print("=" * 60)
        print("Testing Pure Relational State Management & Sequencing")
        print("=" * 60)

        # 1. Setup relational entities (Topics, Questions, Followups)
        topics = [
            TopicState(id=1, name="Topic 1", topic_order=1, expected_time_to_ans=60, expected_answer_keywords=[]),
            TopicState(id=2, name="Topic 2", topic_order=2, expected_time_to_ans=60, expected_answer_keywords=[]),
        ]

        questions = [
            QuestionState(topic_id=1, question_id=101, question_order=1, question="Q1", difficulty="M", expected_time_to_ans=45, expected_answer_keywords=[]),
            QuestionState(topic_id=1, question_id=102, question_order=2, question="Q2", difficulty="M", expected_time_to_ans=45, expected_answer_keywords=[]),
            QuestionState(topic_id=2, question_id=201, question_order=1, question="Q3", difficulty="M", expected_time_to_ans=45, expected_answer_keywords=[]),
        ]

        suggested_followups = [
            SuggestedFollowupState(topic_id=1, question_id=101, followup_order=1, followup="F1.1", expected_time_to_ans=30, expected_answer_keywords=[]),
        ]

        # Initial state on Q1 (no array index!)
        state: InterviewState = {
            "topics": topics,
            "questions": questions,
            "suggested_followups": suggested_followups,
            "evaluations": [],
            "active_topic_id": 1,
            "active_question_id": 101,
            "active_followup_order": None,
            "interview_status": "in_progress",
        }

        # Verify active lookups by ID
        q = get_active_question(state)
        self.assertIsNotNone(q)
        self.assertEqual(q.question_id, 101)
        t = get_active_topic(state)
        self.assertIsNotNone(t)
        self.assertEqual(t.id, 1)
        self.assertFalse(is_active_turn_followup(state))
        self.assertFalse(is_active_turn_reask(state))
        print("✅ Initial active question & topic lookup by Foreign Key passed.")

        # 2. Test Re-ask Relational Derivation
        state["evaluations"].append(
            EvaluationRecord(
                topic_id=1,
                question_id=101,
                followup_order=None,
                turn_type="question",
                attempt_number=1,
                accuracy_score=50.0,
                is_passed=False,
            )
        )
        self.assertTrue(is_active_turn_reask(state))
        print("✅ Re-ask derived relationally as True on failed attempt 1.")

        state["evaluations"].append(
            EvaluationRecord(
                topic_id=1,
                question_id=101,
                followup_order=None,
                turn_type="question",
                attempt_number=2,
                accuracy_score=75.0,
                is_passed=True,
            )
        )
        self.assertFalse(is_active_turn_reask(state))
        print("✅ Re-ask derived relationally as False after attempt 2.")

        # 3. Test Relational Sequencing
        next_t, next_q, next_f, is_done = get_next_relational_turn(state)
        self.assertEqual((next_t, next_q, next_f, is_done), (1, 101, 1, False))
        print("✅ Advanced to follow-up 1 via relational foreign keys.")

        state["active_followup_order"] = 1
        self.assertTrue(is_active_turn_followup(state))
        f = get_active_followup(state)
        self.assertIsNotNone(f)
        self.assertEqual(f.followup, "F1.1")

        next_t, next_q, next_f, is_done = get_next_relational_turn(state)
        self.assertEqual((next_t, next_q, next_f, is_done), (1, 102, None, False))
        print("✅ Advanced to next question in topic (Q2) via relational ordering.")

        state["active_question_id"] = 102
        state["active_followup_order"] = None

        next_t, next_q, next_f, is_done = get_next_relational_turn(state)
        self.assertEqual((next_t, next_q, next_f, is_done), (2, 201, None, False))
        print("✅ Advanced across topics to Topic 2, Question 3 via relational foreign keys.")

        state["active_topic_id"] = 2
        state["active_question_id"] = 201

        next_t, next_q, next_f, is_done = get_next_relational_turn(state)
        self.assertTrue(is_done)
        print("✅ Concluded interview when all relational entities completed.")

        print("\n🎉 ALL RELATIONAL STATE UNIT TESTS PASSED!")


if __name__ == "__main__":
    unittest.main()
