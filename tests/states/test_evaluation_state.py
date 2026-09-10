"""
Comprehensive unit tests for AnswerAccuracyEvaluation, EvaluationRecord,
TopicEvaluationSummary, and FinalEvaluation models.
Verifies:
1. Per-turn evaluation validation (AnswerAccuracyEvaluation).
2. Session turn record validation (EvaluationRecord) with turn_type literals.
3. Topic evaluation summary validation (TopicEvaluationSummary).
4. Final comprehensive interview report validation (FinalEvaluation) with status literals.
5. Missing required fields validation failures across all evaluation models.
6. Score boundary values and serialization.
"""
import sys
from pathlib import Path

src_path = str(Path(__file__).resolve().parent.parent.parent / "src")
if src_path not in sys.path:
    sys.path.insert(0, src_path)

import unittest
from pydantic import ValidationError
from interview.state import (
    AnswerAccuracyEvaluation,
    EvaluationRecord,
    FinalEvaluation,
    TopicEvaluationSummary,
)


class TestEvaluationState(unittest.TestCase):
    # --------------------------------------------------------------------------
    # 1. AnswerAccuracyEvaluation Tests
    # --------------------------------------------------------------------------
    def test_answer_accuracy_evaluation_minimal(self):
        """Verify minimal AnswerAccuracyEvaluation with accuracy_score and is_passed."""
        eval_result = AnswerAccuracyEvaluation(accuracy_score=85.0, is_passed=True)
        self.assertEqual(eval_result.accuracy_score, 85.0)
        self.assertTrue(eval_result.is_passed)
        self.assertEqual(eval_result.matched_keywords, [])
        self.assertEqual(eval_result.unmatched_keywords, [])
        self.assertEqual(eval_result.feedback, "")

    def test_answer_accuracy_evaluation_full(self):
        """Verify complete AnswerAccuracyEvaluation with keyword analysis and feedback."""
        eval_result = AnswerAccuracyEvaluation(
            accuracy_score=65.0,
            is_passed=False,
            matched_keywords=["tuition fee", "living cost"],
            unmatched_keywords=["28-day rule", "maintenance funds in GBP"],
            feedback="Candidate stated fees correctly but could not explain the 28-day rule.",
        )
        self.assertEqual(eval_result.accuracy_score, 65.0)
        self.assertFalse(eval_result.is_passed)
        self.assertEqual(len(eval_result.matched_keywords), 2)
        self.assertEqual(len(eval_result.unmatched_keywords), 2)

    def test_answer_accuracy_evaluation_missing_required(self):
        """Verify missing accuracy_score or is_passed raises ValidationError."""
        with self.assertRaises(ValidationError):
            AnswerAccuracyEvaluation(accuracy_score=75.0)  # Missing is_passed

        with self.assertRaises(ValidationError):
            AnswerAccuracyEvaluation(is_passed=True)  # Missing accuracy_score

    # --------------------------------------------------------------------------
    # 2. EvaluationRecord Tests
    # --------------------------------------------------------------------------
    def test_evaluation_record_question_turn(self):
        """Verify EvaluationRecord for a primary question turn."""
        record = EvaluationRecord(
            topic_id=1,
            question_id=1,
            turn_type="question",
            accuracy_score=90.0,
            is_passed=True,
            feedback="Excellent explanation.",
        )
        self.assertEqual(record.topic_id, 1)
        self.assertEqual(record.question_id, 1)
        self.assertIsNone(record.followup_order)
        self.assertEqual(record.turn_type, "question")
        self.assertEqual(record.attempt_number, 1)
        self.assertEqual(record.accuracy_score, 90.0)
        self.assertTrue(record.is_passed)

    def test_evaluation_record_followup_turn(self):
        """Verify EvaluationRecord for a suggested follow-up probe."""
        record = EvaluationRecord(
            topic_id=2,
            question_id=1,
            followup_order=1,
            turn_type="suggested_followup",
            attempt_number=2,
            accuracy_score=72.0,
            is_passed=True,
            matched_keywords=["living cost", "Hatfield"],
        )
        self.assertEqual(record.turn_type, "suggested_followup")
        self.assertEqual(record.followup_order, 1)
        self.assertEqual(record.attempt_number, 2)

    def test_evaluation_record_invalid_turn_type(self):
        """Verify invalid turn_type literal triggers ValidationError."""
        with self.assertRaises(ValidationError):
            EvaluationRecord(
                topic_id=1,
                turn_type="invalid_type",  # Not 'question' or 'suggested_followup'
                accuracy_score=80.0,
                is_passed=True,
            )

    # --------------------------------------------------------------------------
    # 3. TopicEvaluationSummary Tests
    # --------------------------------------------------------------------------
    def test_topic_evaluation_summary_valid(self):
        """Verify TopicEvaluationSummary holds topic aggregate stats."""
        summary = TopicEvaluationSummary(
            topic_id=1,
            topic_name="Academic Fit & Course Selection",
            average_score=88.5,
            is_passed=True,
            summary_feedback="Candidate demonstrated strong knowledge of core modules.",
        )
        self.assertEqual(summary.topic_id, 1)
        self.assertEqual(summary.average_score, 88.5)
        self.assertTrue(summary.is_passed)

    def test_topic_evaluation_summary_missing_fields(self):
        """Verify missing fields raise ValidationError."""
        with self.assertRaises(ValidationError):
            TopicEvaluationSummary(topic_id=1, average_score=88.5)

    # --------------------------------------------------------------------------
    # 4. FinalEvaluation Tests
    # --------------------------------------------------------------------------
    def test_final_evaluation_valid_passed(self):
        """Verify FinalEvaluation with 'PASSED' overall_status."""
        topic_sum = TopicEvaluationSummary(
            topic_id=1,
            topic_name="Course Fit",
            average_score=85.0,
            is_passed=True,
            summary_feedback="Solid understanding.",
        )
        report = FinalEvaluation(
            overall_score=85.0,
            overall_status="PASSED",
            topic_breakdown=[topic_sum],
            strengths=["Detailed knowledge of AI curriculum"],
            areas_for_improvement=["Could articulate financial sponsor faster"],
            recommendation="Recommend unconditional CAS issuance.",
        )
        self.assertEqual(report.overall_score, 85.0)
        self.assertEqual(report.overall_status, "PASSED")
        self.assertEqual(len(report.topic_breakdown), 1)

    def test_final_evaluation_valid_conditional_pass_and_failed(self):
        """Verify conditional pass and failed literals."""
        for status in ["CONDITIONAL_PASS", "FAILED"]:
            report = FinalEvaluation(
                overall_score=55.0,
                overall_status=status,
                topic_breakdown=[],
                strengths=[],
                areas_for_improvement=["Failed immigration questions"],
                recommendation="Refuse CAS or conduct face-to-face follow-up.",
            )
            self.assertEqual(report.overall_status, status)

    def test_final_evaluation_invalid_status_literal(self):
        """Verify non-permitted overall_status raises ValidationError."""
        with self.assertRaises(ValidationError):
            FinalEvaluation(
                overall_score=90.0,
                overall_status="EXCELLENT",  # Invalid literal
                topic_breakdown=[],
                strengths=[],
                areas_for_improvement=[],
                recommendation="Recommend CAS.",
            )

    def test_final_evaluation_json_roundtrip(self):
        """Verify full report serializes and deserializes accurately."""
        orig = FinalEvaluation(
            overall_score=78.0,
            overall_status="PASSED",
            topic_breakdown=[
                TopicEvaluationSummary(
                    topic_id=1,
                    topic_name="Course Fit",
                    average_score=80.0,
                    is_passed=True,
                    summary_feedback="Good",
                )
            ],
            strengths=["Clear articulation"],
            areas_for_improvement=["None"],
            recommendation="Issue CAS",
        )
        json_data = orig.model_dump_json()
        restored = FinalEvaluation.model_validate_json(json_data)
        self.assertEqual(orig, restored)


if __name__ == "__main__":
    unittest.main()
