"""
Comprehensive unit tests for the Nested Tree Architecture (Pattern A):
QuestionPlanModel -> TopicItem -> QuestionItem -> FollowupItem

Verifies:
1. Deep hierarchical construction (multi-topic, multi-question, multi-followup).
2. Heterogeneous and empty branches (empty topics, questions without follow-ups).
3. Propagation and preservation of additional/extra fields at every tier simultaneously (extra="allow").
4. Cascading unrequired field defaults across the entire tree.
5. Full tree serialization / deserialization round-trip (dict & JSON).
6. Recursive dictionary coercion into proper nested Pydantic models.
7. Cursor navigation alignment with InterviewState indexing (topic_idx, question_idx, followup_idx).
8. Backward compatibility aliases (QuestionListModelState, TopicState, QuestionState, SuggestedFollowupState).
"""
import sys
from pathlib import Path

src_path = str(Path(__file__).resolve().parent.parent.parent / "src")
if src_path not in sys.path:
    sys.path.insert(0, src_path)

import unittest
from pydantic import ValidationError
from interview.state import (
    FollowupItem,
    QuestionItem,
    QuestionPlanModel,
    QuestionListModelState,
    TopicItem,
    TopicState,
    QuestionState,
    SuggestedFollowupState,
)


class TestNestedTreeStructure(unittest.TestCase):
    def test_complete_deep_tree_construction(self):
        """Verify multi-tier tree construction with topics, questions, and follow-ups."""
        tree = QuestionPlanModel(
            topics=[
                TopicItem(
                    id=1,
                    name="Academic Fit & Course Modules",
                    questions=[
                        QuestionItem(
                            question="Why MSc AI at Hertfordshire?",
                            difficulty="Medium",
                            expected_time_to_ans=45,
                            expected_answer_keywords=["robotics", "machine learning", "HPC"],
                            followups=[
                                FollowupItem(
                                    followup_order=1,
                                    followup="Which specific lab facilities will you use?",
                                    expected_answer_keywords=["HPC cluster"],
                                ),
                                FollowupItem(
                                    followup_order=2,
                                    followup="Who is the lead faculty for this module?",
                                    expected_answer_keywords=["Faculty Lead"],
                                ),
                            ],
                        ),
                        QuestionItem(
                            question="How does this course build on your previous degree?",
                            expected_answer_keywords=["BSc Software Engineering"],
                        ),
                    ],
                ),
                TopicItem(
                    id=2,
                    name="Financial Credibility & UKVI Maintenance",
                    questions=[
                        QuestionItem(
                            question="Who is sponsoring your education in the UK?",
                            followups=[
                                FollowupItem(
                                    followup="Can you explain the 28-day holding rule for your bank funds?",
                                    expected_answer_keywords=["28-day rule", "consecutive days"],
                                )
                            ],
                        )
                    ],
                ),
            ],
            expected_total_time_to_ans=30,
            difficulty="Hard",
        )

        self.assertEqual(len(tree.topics), 2)
        self.assertEqual(len(tree.topics[0].questions), 2)
        self.assertEqual(len(tree.topics[0].questions[0].followups), 2)
        self.assertEqual(len(tree.topics[0].questions[1].followups), 0)
        self.assertEqual(len(tree.topics[1].questions), 1)
        self.assertEqual(len(tree.topics[1].questions[0].followups), 1)
        self.assertEqual(tree.expected_total_time_to_ans, 30)
        self.assertEqual(tree.difficulty, "Hard")

    def test_unrequired_fields_defaults_cascade_through_tree(self):
        """Verify that omitting unrequired fields at each level assigns the proper defaults."""
        plan = QuestionPlanModel(
            topics=[
                TopicItem(
                    id=1,
                    name="Minimal Topic",
                    questions=[
                        QuestionItem(
                            question="Minimal Question",
                            followups=[
                                FollowupItem(followup="Minimal Followup")
                            ],
                        )
                    ],
                )
            ]
        )
        # Plan-level defaults
        self.assertEqual(plan.expected_total_time_to_ans, 45)
        self.assertEqual(plan.difficulty, "Medium")

        # Topic-level defaults
        topic = plan.topics[0]
        self.assertEqual(topic.expected_time_to_ans, 60)

        # Question-level defaults
        question = topic.questions[0]
        self.assertEqual(question.difficulty, "Medium")
        self.assertEqual(question.expected_time_to_ans, 45)
        self.assertEqual(question.expected_answer_keywords, [])

        # Followup-level defaults
        followup = question.followups[0]
        self.assertEqual(followup.followup_order, 1)
        self.assertEqual(followup.expected_time_to_ans, 30)
        self.assertEqual(followup.expected_answer_keywords, [])

    def test_empty_and_heterogeneous_branches(self):
        """Verify tree allows topics with no questions, or questions with no followups."""
        tree = QuestionPlanModel(
            topics=[
                TopicItem(id=1, name="Empty Topic", questions=[]),
                TopicItem(
                    id=2,
                    name="Single Question Topic",
                    questions=[QuestionItem(question="Standalone Question", followups=[])],
                ),
            ]
        )
        self.assertEqual(len(tree.topics), 2)
        self.assertEqual(len(tree.topics[0].questions), 0)
        self.assertEqual(len(tree.topics[1].questions), 1)
        self.assertEqual(len(tree.topics[1].questions[0].followups), 0)

    def test_additional_extra_fields_at_all_tiers_simultaneously(self):
        """Verify arbitrary extra attributes are accepted and retained at every tier of the tree."""
        # Note: QuestionPlanModel does not declare extra="allow", but TopicItem, QuestionItem, FollowupItem do.
        tree = QuestionPlanModel(
            topics=[
                TopicItem(
                    id=1,
                    name="Topic with extra",
                    topic_tier_extra="custom_topic_attr",
                    priority_rank=1,
                    questions=[
                        QuestionItem(
                            question="Question with extra",
                            question_tier_extra="custom_question_attr",
                            compliance_tag="UKVI_ACADEMIC",
                            followups=[
                                FollowupItem(
                                    followup="Followup with extra",
                                    followup_tier_extra="custom_followup_attr",
                                    probe_type="deep",
                                )
                            ],
                        )
                    ],
                )
            ]
        )

        topic = tree.topics[0]
        question = topic.questions[0]
        followup = question.followups[0]

        # Verify attributes exist and match
        self.assertEqual(getattr(topic, "topic_tier_extra"), "custom_topic_attr")
        self.assertEqual(getattr(topic, "priority_rank"), 1)
        self.assertEqual(getattr(question, "question_tier_extra"), "custom_question_attr")
        self.assertEqual(getattr(question, "compliance_tag"), "UKVI_ACADEMIC")
        self.assertEqual(getattr(followup, "followup_tier_extra"), "custom_followup_attr")
        self.assertEqual(getattr(followup, "probe_type"), "deep")

        # Verify model_dump retains extra fields
        dumped = tree.model_dump()
        self.assertEqual(dumped["topics"][0]["topic_tier_extra"], "custom_topic_attr")
        self.assertEqual(dumped["topics"][0]["questions"][0]["question_tier_extra"], "custom_question_attr")
        self.assertEqual(dumped["topics"][0]["questions"][0]["followups"][0]["followup_tier_extra"], "custom_followup_attr")

    def test_dict_deserialization_and_coercion_across_tree(self):
        """Verify passing nested raw dicts (such as from LLM json output) coerces cleanly into models."""
        raw_tree_payload = {
            "topics": [
                {
                    "id": 1,
                    "name": "Academic Progression",
                    "expected_time_to_ans": 90,
                    "questions": [
                        {
                            "question": "What modules did you take in undergrad?",
                            "difficulty": "Easy",
                            "expected_time_to_ans": 40,
                            "expected_answer_keywords": ["Data Structures", "Algorithms"],
                            "followups": [
                                {
                                    "followup": "What was your final year thesis about?",
                                    "expected_time_to_ans": 35,
                                    "expected_answer_keywords": ["Machine Learning", "Thesis"],
                                }
                            ],
                        }
                    ],
                }
            ],
            "expected_total_time_to_ans": 40,
            "difficulty": "Medium",
        }

        tree = QuestionPlanModel.model_validate(raw_tree_payload)
        self.assertIsInstance(tree.topics[0], TopicItem)
        self.assertIsInstance(tree.topics[0].questions[0], QuestionItem)
        self.assertIsInstance(tree.topics[0].questions[0].followups[0], FollowupItem)
        self.assertEqual(tree.topics[0].questions[0].followups[0].followup_order, 1)

    def test_full_tree_json_roundtrip(self):
        """Verify full tree serialization to JSON string and restoration produces an identical tree."""
        original_tree = QuestionPlanModel(
            topics=[
                TopicItem(
                    id=101,
                    name="Career Objectives",
                    questions=[
                        QuestionItem(
                            question="Where do you see yourself in 3 years?",
                            followups=[
                                FollowupItem(
                                    followup="What target salary and job title do you expect back home?",
                                    extra_probe_note="Check salary feasibility",
                                )
                            ],
                        )
                    ],
                )
            ]
        )
        json_output = original_tree.model_dump_json()
        restored_tree = QuestionPlanModel.model_validate_json(json_output)

        self.assertEqual(original_tree.model_dump(), restored_tree.model_dump())
        self.assertEqual(
            getattr(restored_tree.topics[0].questions[0].followups[0], "extra_probe_note"),
            "Check salary feasibility",
        )

    def test_cursor_navigation_tree_compatibility(self):
        """Verify that cursor indices map directly to tree hierarchy nodes."""
        plan = QuestionPlanModel(
            topics=[
                TopicItem(
                    id=1,
                    name="Topic A",
                    questions=[
                        QuestionItem(
                            question="QA.1",
                            followups=[
                                FollowupItem(followup="FA.1.1"),
                                FollowupItem(followup="FA.1.2"),
                            ],
                        )
                    ],
                ),
                TopicItem(
                    id=2,
                    name="Topic B",
                    questions=[
                        QuestionItem(question="QB.1", followups=[]),
                    ],
                ),
            ]
        )

        # Primary question for Topic 0
        current_topic_idx = 0
        current_question_idx = 0
        current_followup_idx = -1

        topic = plan.topics[current_topic_idx]
        question = topic.questions[current_question_idx]
        self.assertEqual(question.question, "QA.1")

        # First followup probe
        current_followup_idx = 0
        followup = question.followups[current_followup_idx]
        self.assertEqual(followup.followup, "FA.1.1")

        # Second followup probe
        current_followup_idx = 1
        followup = question.followups[current_followup_idx]
        self.assertEqual(followup.followup, "FA.1.2")

        # Transition to next topic
        current_topic_idx = 1
        current_question_idx = 0
        current_followup_idx = -1
        topic_b = plan.topics[current_topic_idx]
        self.assertEqual(topic_b.questions[current_question_idx].question, "QB.1")

    def test_backward_compatibility_aliases(self):
        """Verify QuestionListModelState alias is identical to QuestionPlanModel."""
        self.assertIs(QuestionListModelState, QuestionPlanModel)
        self.assertIs(TopicState, TopicItem)
        self.assertIs(QuestionState, QuestionItem)
        self.assertIs(SuggestedFollowupState, FollowupItem)


if __name__ == "__main__":
    unittest.main()
