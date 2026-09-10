"""
Comprehensive unit tests for FollowupItem and SuggestedFollowupState models.
Verifies:
1. Minimal initialization with required fields.
2. Default assignments for unrequired fields.
3. Custom values for unrequired fields.
4. Validation failure on missing required fields.
5. Acceptance and preservation of arbitrary additional fields (extra="allow").
6. Serialization / deserialization round-trip.
7. Independence of default list factories across instances.
8. Backward compatibility aliases.
"""
import sys
from pathlib import Path

src_path = str(Path(__file__).resolve().parent.parent.parent / "src")
if src_path not in sys.path:
    sys.path.insert(0, src_path)

import unittest
from pydantic import ValidationError
from interview.state import FollowupItem, SuggestedFollowupState


class TestFollowupState(unittest.TestCase):
    def test_minimal_initialization(self):
        """Verify FollowupItem can be created with only the required 'followup' field."""
        item = FollowupItem(followup="Could you explain your dissertation in detail?")
        self.assertEqual(item.followup, "Could you explain your dissertation in detail?")
        self.assertEqual(item.followup_order, 1)
        self.assertEqual(item.expected_time_to_ans, 30)
        self.assertEqual(item.expected_answer_keywords, [])

    def test_unrequired_fields_defaults(self):
        """Verify explicit default values for all unrequired fields."""
        item = FollowupItem(followup="What was your main research methodology?")
        # followup_order defaults to 1
        self.assertEqual(item.followup_order, 1)
        # expected_time_to_ans defaults to 30 seconds
        self.assertEqual(item.expected_time_to_ans, 30)
        # expected_answer_keywords defaults to empty list
        self.assertIsInstance(item.expected_answer_keywords, list)
        self.assertEqual(len(item.expected_answer_keywords), 0)

    def test_custom_unrequired_fields(self):
        """Verify custom values override defaults cleanly."""
        keywords = ["transformer", "attention mechanism", "BERT", "embeddings"]
        item = FollowupItem(
            followup="How did you apply attention in your NLP module?",
            followup_order=3,
            expected_time_to_ans=60,
            expected_answer_keywords=keywords,
        )
        self.assertEqual(item.followup, "How did you apply attention in your NLP module?")
        self.assertEqual(item.followup_order, 3)
        self.assertEqual(item.expected_time_to_ans, 60)
        self.assertEqual(item.expected_answer_keywords, keywords)

    def test_missing_required_field_raises_validation_error(self):
        """Verify that omitting 'followup' triggers a Pydantic ValidationError."""
        with self.assertRaises(ValidationError) as ctx:
            FollowupItem()  # Missing 'followup'
        errors = ctx.exception.errors()
        self.assertTrue(any(e["loc"] == ("followup",) for e in errors))

    def test_accepting_additional_extra_fields(self):
        """Verify that extra arbitrary fields are accepted due to extra='allow'."""
        item = FollowupItem(
            followup="Tell me about your financial sponsor.",
            custom_rubric="UKVI_28_DAY_RULE",
            priority="HIGH",
            probe_depth=2,
            metadata={"source": "auto_generated", "version": 1.2},
        )
        # Attributes should be accessible directly
        self.assertEqual(getattr(item, "custom_rubric"), "UKVI_28_DAY_RULE")
        self.assertEqual(getattr(item, "priority"), "HIGH")
        self.assertEqual(getattr(item, "probe_depth"), 2)
        self.assertEqual(getattr(item, "metadata")["source"], "auto_generated")

    def test_extra_fields_persisted_in_model_dump(self):
        """Verify that extra fields persist in model_dump() and serialization."""
        item = FollowupItem(
            followup="Probe question",
            extra_tag="visa_compliance",
            score_multiplier=1.5,
        )
        dumped = item.model_dump()
        self.assertIn("extra_tag", dumped)
        self.assertEqual(dumped["extra_tag"], "visa_compliance")
        self.assertEqual(dumped["score_multiplier"], 1.5)

    def test_json_roundtrip_with_extra_fields(self):
        """Verify serialization to JSON string and re-parsing retains extra fields."""
        original = FollowupItem(
            followup="Can you explain your tuition fee breakdown?",
            expected_answer_keywords=["16500", "GBP", "installment"],
            arbitrary_note="Candidate hesitated initially",
        )
        json_str = original.model_dump_json()
        reconstructed = FollowupItem.model_validate_json(json_str)
        self.assertEqual(original.followup, reconstructed.followup)
        self.assertEqual(original.expected_answer_keywords, reconstructed.expected_answer_keywords)
        self.assertEqual(getattr(reconstructed, "arbitrary_note"), "Candidate hesitated initially")

    def test_default_factory_independence(self):
        """Verify that expected_answer_keywords does not suffer from mutable default side effects."""
        item1 = FollowupItem(followup="Question 1")
        item2 = FollowupItem(followup="Question 2")
        item1.expected_answer_keywords.append("unique_to_1")
        self.assertIn("unique_to_1", item1.expected_answer_keywords)
        self.assertNotIn("unique_to_1", item2.expected_answer_keywords)

    def test_invalid_data_types_rejected(self):
        """Verify that invalid types for numeric fields trigger ValidationError."""
        with self.assertRaises(ValidationError):
            FollowupItem(followup="Question", expected_time_to_ans="not_a_number")

    def test_backward_compatibility_alias(self):
        """Verify SuggestedFollowupState is an alias of FollowupItem."""
        self.assertIs(SuggestedFollowupState, FollowupItem)
        alias_item = SuggestedFollowupState(followup="Alias test question")
        self.assertIsInstance(alias_item, FollowupItem)


if __name__ == "__main__":
    unittest.main()
