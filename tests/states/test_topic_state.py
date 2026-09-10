"""
Comprehensive unit tests for TopicItem and TopicState models.
Verifies:
1. Minimal initialization with required fields (id, name).
2. Default assignments for unrequired fields (expected_time_to_ans, questions).
3. Custom values for unrequired fields and nested questions.
4. Validation failure on missing required fields.
5. Acceptance and preservation of arbitrary additional fields (extra="allow").
6. Dict coercion for nested QuestionItem objects.
7. Serialization / deserialization round-trip.
8. Independence of default questions factory.
9. Backward compatibility alias TopicState.
"""
import sys
from pathlib import Path

src_path = str(Path(__file__).resolve().parent.parent.parent / "src")
if src_path not in sys.path:
    sys.path.insert(0, src_path)

import unittest
from pydantic import ValidationError
from interview.state import TopicItem, TopicState, QuestionItem


class TestTopicState(unittest.TestCase):
    def test_minimal_initialization(self):
        """Verify TopicItem can be instantiated with only id and name."""
        topic = TopicItem(id=1, name="Academic Fit & Course Selection")
        self.assertEqual(topic.id, 1)
        self.assertEqual(topic.name, "Academic Fit & Course Selection")
        self.assertEqual(topic.expected_time_to_ans, 60)
        self.assertEqual(topic.questions, [])

    def test_unrequired_fields_defaults(self):
        """Verify explicit default values for unrequired fields."""
        topic = TopicItem(id=2, name="Financial Credibility")
        self.assertEqual(topic.expected_time_to_ans, 60)
        self.assertIsInstance(topic.questions, list)
        self.assertEqual(len(topic.questions), 0)

    def test_custom_unrequired_fields(self):
        """Verify custom time limits and nested QuestionItem instances."""
        q1 = QuestionItem(question="Why did you choose Hertfordshire?")
        topic = TopicItem(
            id=3,
            name="University Selection Rationale",
            expected_time_to_ans=120,
            questions=[q1],
        )
        self.assertEqual(topic.id, 3)
        self.assertEqual(topic.name, "University Selection Rationale")
        self.assertEqual(topic.expected_time_to_ans, 120)
        self.assertEqual(len(topic.questions), 1)
        self.assertEqual(topic.questions[0].question, "Why did you choose Hertfordshire?")

    def test_missing_required_fields_raises_validation_error(self):
        """Verify omitting id or name raises Pydantic ValidationError."""
        # Missing both
        with self.assertRaises(ValidationError):
            TopicItem()

        # Missing name
        with self.assertRaises(ValidationError) as ctx:
            TopicItem(id=1)
        errors = ctx.exception.errors()
        self.assertTrue(any(e["loc"] == ("name",) for e in errors))

        # Missing id
        with self.assertRaises(ValidationError) as ctx:
            TopicItem(name="Course Fit")
        errors = ctx.exception.errors()
        self.assertTrue(any(e["loc"] == ("id",) for e in errors))

    def test_accepting_additional_extra_fields(self):
        """Verify extra arbitrary fields are accepted due to extra='allow'."""
        topic = TopicItem(
            id=10,
            name="Post-Study Career Goals",
            topic_order=4,
            category="compliance",
            rubric_id="UKVI_CAREER_01",
            passing_score=75.0,
        )
        self.assertEqual(getattr(topic, "topic_order"), 4)
        self.assertEqual(getattr(topic, "category"), "compliance")
        self.assertEqual(getattr(topic, "rubric_id"), "UKVI_CAREER_01")
        self.assertEqual(getattr(topic, "passing_score"), 75.0)

    def test_extra_fields_persisted_in_model_dump(self):
        """Verify that extra fields persist in model_dump()."""
        topic = TopicItem(
            id=5,
            name="Immigration History",
            custom_flag=True,
            audit_notes="Needs thorough inspection",
        )
        data = topic.model_dump()
        self.assertIn("custom_flag", data)
        self.assertTrue(data["custom_flag"])
        self.assertEqual(data["audit_notes"], "Needs thorough inspection")

    def test_nested_questions_dict_coercion(self):
        """Verify Pydantic automatically validates dict inputs in questions list into QuestionItem."""
        topic = TopicItem(
            id=1,
            name="Course Modules",
            questions=[
                {"question": "What is covered in the Advanced AI module?", "difficulty": "Hard"}
            ],
        )
        self.assertEqual(len(topic.questions), 1)
        self.assertIsInstance(topic.questions[0], QuestionItem)
        self.assertEqual(topic.questions[0].question, "What is covered in the Advanced AI module?")
        self.assertEqual(topic.questions[0].difficulty, "Hard")

    def test_json_roundtrip(self):
        """Verify serialization to JSON string and restoration retains all fields."""
        original = TopicItem(
            id=7,
            name="Accommodation & Living",
            expected_time_to_ans=90,
            extra_metadata={"reviewer": "Senior Officer"},
        )
        raw_json = original.model_dump_json()
        restored = TopicItem.model_validate_json(raw_json)
        self.assertEqual(original.id, restored.id)
        self.assertEqual(original.name, restored.name)
        self.assertEqual(original.expected_time_to_ans, restored.expected_time_to_ans)
        self.assertEqual(getattr(restored, "extra_metadata")["reviewer"], "Senior Officer")

    def test_default_questions_factory_independence(self):
        """Verify questions lists across different TopicItem instances do not share state."""
        t1 = TopicItem(id=1, name="Topic 1")
        t2 = TopicItem(id=2, name="Topic 2")
        t1.questions.append(QuestionItem(question="Q for topic 1"))
        self.assertEqual(len(t1.questions), 1)
        self.assertEqual(len(t2.questions), 0)

    def test_invalid_type_rejection(self):
        """Verify non-integer id triggers ValidationError."""
        with self.assertRaises(ValidationError):
            TopicItem(id="not_an_int", name="Invalid Topic")

    def test_backward_compatibility_alias(self):
        """Verify TopicState is an exact alias of TopicItem."""
        self.assertIs(TopicState, TopicItem)
        topic = TopicState(id=1, name="Alias Topic")
        self.assertIsInstance(topic, TopicItem)


if __name__ == "__main__":
    unittest.main()
