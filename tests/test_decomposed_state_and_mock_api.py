"""
Unit tests for decomposed states, standardized mock API JSON loading,
and Final Evaluation structure.
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
from mock_api import fetch_student_api, fetch_university_api
from interview.state import (
    AnswerAccuracyEvaluation,
    EvaluationRecord,
    FinalEvaluation,
    InterviewState,
    QuestionListModelState,
    QuestionState,
    StudentData,
    SuggestedFollowupState,
    TopicEvaluationSummary,
    TopicState,
    FollowupItem,
    UniversityData,
)
from interview.graph import create_interview_graph, route_after_ask, route_start


class TestDecomposedStatesAndMockApi(unittest.TestCase):
    def test_mock_api_student_loading(self):
        """Verify student data loads cleanly from data/students/ JSON."""
        raw_student = fetch_student_api("UK-CAS-2026-9041")
        self.assertIsInstance(raw_student, dict)
        self.assertEqual(raw_student["student_id"], "UK-CAS-2026-9041")
        self.assertEqual(raw_student["full_name"], "Tariqul Islam")

        # Verify StudentData parsing
        student = StudentData(**{k: v for k, v in raw_student.items() if k in StudentData.model_fields})
        self.assertEqual(student.student_id, "UK-CAS-2026-9041")
        self.assertEqual(student.tuition_fee_gbp, 16500.0)
        self.assertEqual(student.living_cost_gbp, 12500.0)
        print("✅ Mock Student API correctly loads from data/students/ JSON into StudentData.")

    def test_mock_api_university_loading(self):
        """Verify university data loads cleanly from data/universities/ JSON."""
        raw_univ = fetch_university_api("UK-HERTS-01")
        self.assertIsInstance(raw_univ, dict)
        self.assertEqual(raw_univ["university_id"], "UK-HERTS-01")
        self.assertIn("Hertfordshire", raw_univ["official_name"])

        # Verify UniversityData parsing
        univ = UniversityData(**{k: v for k, v in raw_univ.items() if k in UniversityData.model_fields})
        self.assertEqual(univ.university_id, "UK-HERTS-01")
        self.assertEqual(univ.tuition_fee_gbp, 16500.0)
        self.assertEqual(len(univ.core_modules), 3)
        print("✅ Mock University API correctly loads from data/universities/ JSON into UniversityData.")

    def test_followup_state_questions(self):
        """Verify FollowupItem model."""
        keywords = [
            "AI", "Transformer", "distillation", "vector", "quantization", "transformers", "deep learning"
        ]
        item = FollowupItem(
            followup="Could you explain this topic thoroughly?",
            expected_answer_keywords=keywords,
        )
        self.assertEqual(item.followup, "Could you explain this topic thoroughly?")
        self.assertEqual(item.expected_time_to_ans, 30)
        self.assertEqual(item.expected_answer_keywords, keywords)
        self.assertEqual(item.followup_order, 1)
        print("✅ FollowupItem model verified.")

    def test_topic_state(self):
        """Verify Topic model."""
        topic = TopicState(
            id=1,
            name="Academic Fit & Course Selection",
            questions=[],
        )
        self.assertEqual(topic.id, 1)
        self.assertEqual(topic.name, "Academic Fit & Course Selection")
        print("✅ Topic model verified.")


    def test_final_evaluation_model(self):
        """Verify FinalEvaluation schema and calculation structures."""
        topic_summary = TopicEvaluationSummary(
            topic_id=1,
            topic_name="Academic Fit & Course Selection",
            average_score=85.0,
            is_passed=True,
            summary_feedback="Strong knowledge of ML and Robotics modules.",
        )
        final_eval = FinalEvaluation(
            overall_score=82.5,
            overall_status="PASSED",
            topic_breakdown=[topic_summary],
            strengths=["Detailed knowledge of core modules", "Met 28-day rule"],
            areas_for_improvement=["Could articulate competitor fees faster"],
            recommendation="Recommend unconditional CAS issuance for UK Student Visa.",
        )
        self.assertEqual(final_eval.overall_score, 82.5)
        self.assertEqual(final_eval.overall_status, "PASSED")
        self.assertEqual(len(final_eval.topic_breakdown), 1)
        print("✅ FinalEvaluation and TopicEvaluationSummary validate cleanly.")

    def test_graph_routing_lifecycle(self):
        """Verify StateGraph routes dynamically from init to turn to conclusion."""
        # 1. Start of interview
        init_state: InterviewState = {"interview_status": "not_started"}
        self.assertEqual(route_start(init_state), "generate_questions")

        # 2. Turn in progress
        turn_state: InterviewState = {"interview_status": "in_progress"}
        self.assertEqual(route_start(turn_state), "evaluate_answer")

        # 3. Direct questions start
        direct_state: InterviewState = {
            "questions": [QuestionState(topic_id=1, question_id=1, question_order=1, question="Q", expected_answer_keywords=[])],
        }
        self.assertEqual(route_start(direct_state), "ask_question")

        # 4. Turn conclusion routing
        ongoing_state: InterviewState = {"interview_status": "in_progress"}
        from langgraph.graph import END
        self.assertEqual(route_after_ask(ongoing_state), END)

        concluded_state: InterviewState = {"interview_status": "completed"}
        self.assertEqual(route_after_ask(concluded_state), "generate_final_evaluation")
        print("✅ StateGraph conditional edges and lifecycle routing verified.")


if __name__ == "__main__":
    unittest.main()
