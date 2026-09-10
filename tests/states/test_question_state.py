"""
Comprehensive unit tests for QuestionItem and QuestionState models.
Verifies:
1. Minimal initialization with required field (question).
2. Default assignments for unrequired fields (difficulty, expected_time_to_ans, expected_answer_keywords, followups).
3. Custom values for unrequired fields.
4. Validation failure on missing required 'question'.
5. Acceptance and preservation of arbitrary additional fields (extra="allow").
6. Dict coercion for nested FollowupItem objects.
7. Serialization / deserialization round-trip.
8. Independence of default lists across instances.
9. Backward compatibility alias QuestionState.
"""
import sys
from pathlib import Path

src_path = str(Path(__file__).resolve().parent.parent.parent / "src")
if src_path not in sys.path:
    sys.path.insert(0, src_path)

import unittest
from pydantic import ValidationError
from interview.state import QuestionItem, QuestionState, FollowupItem


class TestQuestionState(unittest.TestCase):
    def test_minimal_initialization(self):
        """Verify QuestionItem can be instantiated with only the question text."""
        q = QuestionItem(question="Why did you select this specific program?")
        self.assertEqual(q.question, "Why did you select this specific program?")
        self.assertEqual(q.difficulty, "Medium")
        self.assertEqual(q.expected_time_to_ans, 45)
        self.assertEqual(q.expected_answer_keywords, [])
        self.assertEqual(q.followups, [])

    def test_unrequired_fields_defaults(self):
        """Verify explicit default values for unrequired fields."""
        q = QuestionItem(question="Tell me about your financial sponsor.")
        self.assertEqual(q.difficulty, "Medium")
        self.assertEqual(q.expected_time_to_ans, 45)
        self.assertIsInstance(q.expected_answer_keywords, list)
        self.assertEqual(len(q.expected_answer_keywords), 0)
        self.assertIsInstance(q.followups, list)
        self.assertEqual(len(q.followups), 0)

    def test_custom_unrequired_fields(self):
        """Verify overriding all unrequired fields with custom values."""
        f1 = FollowupItem(followup="Probe 1")
        f2 = FollowupItem(followup="Probe 2")
        keywords = ["tuition", "maintenance", "savings", "28-day rule"]
        q = QuestionItem(
            question="How will you fund your studies and living expenses in the UK?",
            difficulty="Hard",
            expected_time_to_ans=60,
            expected_answer_keywords=keywords,
            followups=[f1, f2],
        )
        self.assertEqual(q.difficulty, "Hard")
        self.assertEqual(q.expected_time_to_ans, 60)
        self.assertEqual(q.expected_answer_keywords, keywords)
        self.assertEqual(len(q.followups), 2)
        self.assertEqual(q.followups[0].followup, "Probe 1")
        self.assertEqual(q.followups[1].followup, "Probe 2")

    def test_missing_required_question_raises_validation_error(self):
        """Verify omitting question triggers ValidationError."""
        with self.assertRaises(ValidationError) as ctx:
            QuestionItem()
        errors = ctx.exception.errors()
        self.assertTrue(any(e["loc"] == ("question",) for e in errors))

    def test_accepting_additional_extra_fields(self):
        """Verify arbitrary extra attributes are accepted due to extra='allow'."""
        q = QuestionItem(
            question="Explain your post-graduation career path.",
            question_id=101,
            topic_id=2,
            rubric_benchmark="Tier 4 General Credibility",
            scoring_notes="Check for clear company names and salary projections",
            weight=1.25,
        )
        self.assertEqual(getattr(q, "question_id"), 101)
        self.assertEqual(getattr(q, "topic_id"), 2)
        self.assertEqual(getattr(q, "rubric_benchmark"), "Tier 4 General Credibility")
        self.assertEqual(getattr(q, "scoring_notes"), "Check for clear company names and salary projections")
        self.assertEqual(getattr(q, "weight"), 1.25)

    def test_extra_fields_persisted_in_model_dump(self):
        """Verify extra fields persist in model_dump()."""
        q = QuestionItem(
            question="What modules are taught in semester 1?",
            custom_flag="module_probe",
            is_mandatory=True,
        )
        dumped = q.model_dump()
        self.assertIn("custom_flag", dumped)
        self.assertEqual(dumped["custom_flag"], "module_probe")
        self.assertTrue(dumped["is_mandatory"])

    def test_dict_coercion_for_nested_followups(self):
        """Verify passing list of dicts into followups converts them into FollowupItem instances."""
        q = QuestionItem(
            question="Describe your previous work experience.",
            followups=[
                {"followup": "What was your specific role?", "followup_order": 1},
                {"followup": "How does it connect to this MSc?", "followup_order": 2, "expected_time_to_ans": 40},
            ],
        )
        self.assertEqual(len(q.followups), 2)
        self.assertIsInstance(q.followups[0], FollowupItem)
        self.assertIsInstance(q.followups[1], FollowupItem)
        self.assertEqual(q.followups[0].followup, "What was your specific role?")
        self.assertEqual(q.followups[1].expected_time_to_ans, 40)

    def test_json_roundtrip(self):
        """Verify JSON roundtrip retains all fields and nested followups."""
        original = QuestionItem(
            question="Compare Hertfordshire to other UK universities you considered.",
            difficulty="Hard",
            expected_answer_keywords=["location", "facilities", "curriculum", "tuition difference"],
            followups=[FollowupItem(followup="Why didn't you select Coventry or Greenwich?")],
            additional_context="Competitor analysis probe",
        )
        json_data = original.model_dump_json()
        restored = QuestionItem.model_validate_json(json_data)
        self.assertEqual(original.question, restored.question)
        self.assertEqual(original.difficulty, restored.difficulty)
        self.assertEqual(len(restored.followups), 1)
        self.assertEqual(restored.followups[0].followup, "Why didn't you select Coventry or Greenwich?")
        self.assertEqual(getattr(restored, "additional_context"), "Competitor analysis probe")

    def test_default_lists_independence(self):
        """Verify expected_answer_keywords and followups lists are not shared between instances."""
        q1 = QuestionItem(question="Q1")
        q2 = QuestionItem(question="Q2")
        q1.expected_answer_keywords.append("kw1")
        q1.followups.append(FollowupItem(followup="F1"))
        self.assertEqual(len(q1.expected_answer_keywords), 1)
        self.assertEqual(len(q1.followups), 1)
        self.assertEqual(len(q2.expected_answer_keywords), 0)
        self.assertEqual(len(q2.followups), 0)

    def test_backward_compatibility_alias(self):
        """Verify QuestionState is an exact alias of QuestionItem."""
        self.assertIs(QuestionState, QuestionItem)
        q = QuestionState(question="Alias Question")
        self.assertIsInstance(q, QuestionItem)


if __name__ == "__main__":
    unittest.main()
