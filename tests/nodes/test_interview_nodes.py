import sys
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch

src_path = str(Path(__file__).resolve().parent.parent.parent / "src")
if src_path not in sys.path:
    sys.path.insert(0, src_path)

from langchain_core.messages import AIMessage, HumanMessage
from interview.nodes import (
    ask_question_node,
    evaluate_answer_node,
    generate_final_evaluation_node,
    generate_questions_node,
    process_answer_node,
)
from interview.state import (
    AnswerAccuracyEvaluation,
    EvaluationRecord,
    FinalEvaluation,
    FollowupItem,
    InterviewState,
    QuestionItem,
    QuestionPlanModel,
    StudentData,
    TopicEvaluationSummary,
    TopicItem,
    UniversityData,
)


class TestGenerateQuestionsNode(unittest.TestCase):
    """Unit tests for generate_questions_node (Node 1)."""

    def setUp(self):
        self.student = StudentData(
            student_id="STU-001",
            full_name="Alex Turner",
            target_university="University of Hertfordshire",
            target_course="MSc Computer Science",
            tuition_fee_gbp=16500.0,
            living_cost_gbp=9207.0,
            available_funds_gbp=28000.0,
            sponsor_details="Father bank savings, 28-day rule satisfied",
            post_study_plan="Return to India as Senior Software Engineer",
        )
        self.univ = UniversityData(
            university_id="HERTS-01",
            official_name="University of Hertfordshire",
            target_course="MSc Computer Science",
            core_modules=[{"title": "Advanced Computer Science"}, {"title": "Software Engineering"}],
            tuition_fee_gbp=16500.0,
            living_cost_guideline_gbp=9207.0,
        )

    @patch("interview.nodes.get_structured_thinking_llm")
    def test_generate_questions_success(self, mock_get_llm):
        """Generates structured topics with questions and follow-ups, setting initial cursors."""
        mock_plan = QuestionPlanModel(
            topics=[
                TopicItem(
                    id=1,
                    name="Academic Fit",
                    questions=[
                        QuestionItem(
                            question="Why MSc Computer Science?",
                            expected_answer_keywords=["Advanced Computer Science"],
                            followups=[
                                FollowupItem(
                                    followup_order=1,
                                    followup="Which lab facility will you use?",
                                    expected_answer_keywords=["Computing Lab"],
                                )
                            ],
                        )
                    ],
                )
            ],
            expected_total_time_to_ans=45,
            difficulty="Medium",
        )
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = mock_plan
        mock_get_llm.return_value = mock_llm

        state: InterviewState = {
            "student_data": self.student,
            "university_data": self.univ,
            "difficulty": "Medium",
            "expected_total_time_to_ans": 45,
        }

        output = generate_questions_node(state)

        self.assertEqual(len(output["topics"]), 1)
        self.assertEqual(output["topics"][0].name, "Academic Fit")
        self.assertEqual(output["current_topic_idx"], 0)
        self.assertEqual(output["current_question_idx"], 0)
        self.assertEqual(output["current_followup_idx"], -1)
        self.assertEqual(output["interview_status"], "in_progress")
        self.assertEqual(output["evaluations"], [])

    @patch("interview.nodes.get_structured_thinking_llm")
    def test_generate_questions_with_empty_data(self, mock_get_llm):
        """Generates questions gracefully even when student_data and university_data are None."""
        mock_plan = QuestionPlanModel(
            topics=[
                TopicItem(
                    id=1,
                    name="General Credibility",
                    questions=[QuestionItem(question="Why UK?", expected_answer_keywords=["UK"])],
                )
            ],
            expected_total_time_to_ans=30,
            difficulty="Easy",
        )
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = mock_plan
        mock_get_llm.return_value = mock_llm

        state: InterviewState = {"difficulty": "Easy"}
        output = generate_questions_node(state)

        self.assertEqual(len(output["topics"]), 1)
        self.assertEqual(output["difficulty"], "Easy")


class TestEvaluateAnswerNode(unittest.TestCase):
    """Unit tests for evaluate_answer_node (Node 2)."""

    def setUp(self):
        self.topics = [
            TopicItem(
                id=1,
                name="Academic Fit",
                questions=[
                    QuestionItem(
                        question="Why MSc Computer Science?",
                        expected_answer_keywords=["Advanced Computer Science", "Algorithms"],
                        followups=[],
                    )
                ],
            )
        ]

    def test_evaluate_answer_missing_human_message(self):
        """When candidate has not submitted a response, returns empty dict."""
        state: InterviewState = {
            "topics": self.topics,
            "messages": [AIMessage(content="Why MSc Computer Science?")],
        }
        self.assertEqual(evaluate_answer_node(state), {})

    def test_evaluate_answer_missing_target_question(self):
        """When no target question can be resolved, returns empty dict."""
        state: InterviewState = {
            "topics": [],
            "messages": [HumanMessage(content="My answer")],
        }
        self.assertEqual(evaluate_answer_node(state), {})

    @patch("interview.nodes.get_structured_thinking_llm")
    def test_evaluate_answer_passed_record(self, mock_get_llm):
        """Evaluates passing response, computes attempt 1, and appends EvaluationRecord."""
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = AnswerAccuracyEvaluation(
            accuracy_score=85.0,
            is_passed=True,
            matched_keywords=["Advanced Computer Science", "Algorithms"],
            unmatched_keywords=[],
            feedback="Great technical explanation.",
        )
        mock_get_llm.return_value = mock_llm

        state: InterviewState = {
            "topics": self.topics,
            "current_topic_idx": 0,
            "current_question_idx": 0,
            "current_followup_idx": -1,
            "evaluations": [],
            "messages": [
                AIMessage(content="Why MSc Computer Science?"),
                HumanMessage(content="I want to study Advanced Computer Science and Algorithms."),
            ],
        }

        result = evaluate_answer_node(state)
        evals = result.get("evaluations", [])

        self.assertEqual(len(evals), 1)
        record = evals[0]
        self.assertEqual(record.topic_id, 0)
        self.assertEqual(record.question_id, 0)
        self.assertIsNone(record.followup_order)
        self.assertEqual(record.turn_type, "question")
        self.assertEqual(record.attempt_number, 1)
        self.assertEqual(record.accuracy_score, 85.0)
        self.assertTrue(record.is_passed)
        self.assertEqual(record.matched_keywords, ["Advanced Computer Science", "Algorithms"])

    @patch("interview.nodes.get_structured_thinking_llm")
    def test_evaluate_answer_retry_attempt_counter(self, mock_get_llm):
        """Increments attempt_number to 2 on re-ask retry for the same question."""
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = AnswerAccuracyEvaluation(
            accuracy_score=75.0,
            is_passed=True,
            matched_keywords=["Algorithms"],
            unmatched_keywords=[],
            feedback="Improved answer on retry.",
        )
        mock_get_llm.return_value = mock_llm

        prior_eval = EvaluationRecord(
            topic_id=0,
            question_id=0,
            followup_order=None,
            turn_type="question",
            attempt_number=1,
            accuracy_score=40.0,
            is_passed=False,
            matched_keywords=[],
            unmatched_keywords=["Algorithms"],
            feedback="Missed core modules.",
        )

        state: InterviewState = {
            "topics": self.topics,
            "current_topic_idx": 0,
            "current_question_idx": 0,
            "current_followup_idx": -1,
            "evaluations": [prior_eval],
            "messages": [
                AIMessage(content="Could you elaborate on the modules?"),
                HumanMessage(content="Yes, I will study Algorithms."),
            ],
        }

        result = evaluate_answer_node(state)
        evals = result.get("evaluations", [])

        self.assertEqual(len(evals), 2)
        self.assertEqual(evals[1].attempt_number, 2)
        self.assertTrue(evals[1].is_passed)


class TestAskQuestionNode(unittest.TestCase):
    """Unit tests for ask_question_node (Node 3)."""

    def setUp(self):
        self.topics = [
            TopicItem(
                id=1,
                name="Academic Fit",
                questions=[
                    QuestionItem(
                        question="Why MSc Computer Science?",
                        expected_answer_keywords=["AI"],
                        followups=[
                            FollowupItem(
                                followup_order=1,
                                followup="What are your project goals?",
                                expected_answer_keywords=["Research"],
                            )
                        ],
                    )
                ],
            )
        ]

    @patch("interview.nodes.get_speech_llm")
    def test_ask_primary_question(self, mock_get_speech):
        """Formulates primary standalone question."""
        mock_speech = MagicMock()
        mock_speech.invoke.return_value = AIMessage(content="Welcome. Why did you choose MSc Computer Science?")
        mock_get_speech.return_value = mock_speech

        state: InterviewState = {
            "topics": self.topics,
            "current_topic_idx": 0,
            "current_question_idx": 0,
            "current_followup_idx": -1,
            "interview_status": "in_progress",
            "messages": [],
        }

        result = ask_question_node(state)
        messages = result.get("messages", [])

        self.assertEqual(len(messages), 1)
        self.assertIn("Why did you choose", messages[0].content)
        self.assertEqual(result.get("interview_status"), "in_progress")

    @patch("interview.nodes.get_speech_llm")
    def test_ask_followup_question(self, mock_get_speech):
        """Formulates follow-up question when current_followup_idx >= 0."""
        mock_speech = MagicMock()
        mock_speech.invoke.return_value = AIMessage(content="Interesting. What are your specific project goals?")
        mock_get_speech.return_value = mock_speech

        state: InterviewState = {
            "topics": self.topics,
            "current_topic_idx": 0,
            "current_question_idx": 0,
            "current_followup_idx": 0,
            "interview_status": "in_progress",
            "messages": [AIMessage(content="Why MSc Computer Science?"), HumanMessage(content="I love AI.")],
        }

        result = ask_question_node(state)
        messages = result.get("messages", [])

        self.assertEqual(len(messages), 1)
        self.assertIn("project goals", messages[0].content)

    @patch("interview.nodes.get_speech_llm")
    def test_ask_reask_question(self, mock_get_speech):
        """Prompts candidate to elaborate when previous attempt failed."""
        mock_speech = MagicMock()
        mock_speech.invoke.return_value = AIMessage(
            content="Could you provide more detail on your background regarding AI?"
        )
        mock_get_speech.return_value = mock_speech

        failing_eval = EvaluationRecord(
            topic_id=0,
            question_id=0,
            followup_order=None,
            turn_type="question",
            attempt_number=1,
            accuracy_score=35.0,
            is_passed=False,
            matched_keywords=[],
            unmatched_keywords=["AI"],
            feedback="Did not mention AI.",
        )

        state: InterviewState = {
            "topics": self.topics,
            "current_topic_idx": 0,
            "current_question_idx": 0,
            "current_followup_idx": -1,
            "evaluations": [failing_eval],
            "interview_status": "in_progress",
            "messages": [AIMessage(content="Why MSc?"), HumanMessage(content="Just general interest.")],
        }

        result = ask_question_node(state)
        messages = result.get("messages", [])

        self.assertEqual(len(messages), 1)
        self.assertIn("provide more detail", messages[0].content)

    @patch("interview.nodes.get_speech_llm")
    def test_ask_concluding_remarks_when_completed(self, mock_get_speech):
        """Delivers concluding speech when interview_status is completed."""
        mock_speech = MagicMock()
        mock_speech.invoke.return_value = AIMessage(content="Thank you for your time today. Best of luck!")
        mock_get_speech.return_value = mock_speech

        state: InterviewState = {
            "topics": self.topics,
            "interview_status": "completed",
            "messages": [],
        }

        result = ask_question_node(state)
        messages = result.get("messages", [])

        self.assertEqual(result.get("interview_status"), "completed")
        self.assertEqual(len(messages), 1)
        self.assertIn("Thank you for your time", messages[0].content)


class TestProcessAnswerNode(unittest.TestCase):
    """Unit tests for process_answer_node (Node 4)."""

    def setUp(self):
        self.topics = [
            TopicItem(
                id=1,
                name="Topic 1",
                questions=[
                    QuestionItem(
                        question="Q1",
                        expected_answer_keywords=["K1"],
                        followups=[FollowupItem(followup_order=1, followup="F1", expected_answer_keywords=["FK1"])],
                    )
                ],
            ),
            TopicItem(
                id=2,
                name="Topic 2",
                questions=[QuestionItem(question="Q2", expected_answer_keywords=["K2"], followups=[])],
            ),
        ]

    def test_reask_retention_on_first_attempt_failure(self):
        """Retains cursors for re-ask when attempt 1 failed."""
        failing_eval = EvaluationRecord(
            topic_id=0,
            question_id=0,
            followup_order=None,
            turn_type="question",
            attempt_number=1,
            accuracy_score=40.0,
            is_passed=False,
            matched_keywords=[],
            unmatched_keywords=["K1"],
            feedback="Weak response.",
        )
        state: InterviewState = {
            "topics": self.topics,
            "current_topic_idx": 0,
            "current_question_idx": 0,
            "current_followup_idx": -1,
            "evaluations": [failing_eval],
            "interview_status": "in_progress",
        }

        result = process_answer_node(state)

        # In LangGraph, returning {} preserves existing cursors
        self.assertEqual(result, {})

    def test_advance_to_followup_on_pass(self):
        """Advances cursor to follow-up (current_followup_idx = 0) on pass."""
        passed_eval = EvaluationRecord(
            topic_id=0,
            question_id=0,
            followup_order=None,
            turn_type="question",
            attempt_number=1,
            accuracy_score=85.0,
            is_passed=True,
            matched_keywords=["K1"],
            unmatched_keywords=[],
            feedback="Strong response.",
        )
        state: InterviewState = {
            "topics": self.topics,
            "current_topic_idx": 0,
            "current_question_idx": 0,
            "current_followup_idx": -1,
            "evaluations": [passed_eval],
            "interview_status": "in_progress",
        }

        result = process_answer_node(state)

        self.assertEqual(result.get("current_followup_idx"), 0)

    def test_advance_to_next_topic_when_questions_exhaust(self):
        """Advances to Topic 2 (idx 1, Q0, F-1) after completing Topic 1 follow-up."""
        followup_passed = EvaluationRecord(
            topic_id=0,
            question_id=0,
            followup_order=0,
            turn_type="suggested_followup",
            attempt_number=1,
            accuracy_score=90.0,
            is_passed=True,
            matched_keywords=["FK1"],
            unmatched_keywords=[],
            feedback="Accurate follow-up.",
        )
        state: InterviewState = {
            "topics": self.topics,
            "current_topic_idx": 0,
            "current_question_idx": 0,
            "current_followup_idx": 0,
            "evaluations": [followup_passed],
            "interview_status": "in_progress",
        }

        result = process_answer_node(state)

        self.assertEqual(result.get("current_topic_idx"), 1)
        self.assertEqual(result.get("current_question_idx"), 0)
        self.assertEqual(result.get("current_followup_idx"), -1)

    def test_conclude_when_all_topics_finish(self):
        """Marks interview_status = completed when final topic question passes."""
        final_passed = EvaluationRecord(
            topic_id=1,
            question_id=0,
            followup_order=None,
            turn_type="question",
            attempt_number=1,
            accuracy_score=80.0,
            is_passed=True,
            matched_keywords=["K2"],
            unmatched_keywords=[],
            feedback="Good answer.",
        )
        state: InterviewState = {
            "topics": self.topics,
            "current_topic_idx": 1,
            "current_question_idx": 0,
            "current_followup_idx": -1,
            "evaluations": [final_passed],
            "interview_status": "in_progress",
        }

        result = process_answer_node(state)

        self.assertEqual(result.get("interview_status"), "completed")


class TestGenerateFinalEvaluationNode(unittest.TestCase):
    """Unit tests for generate_final_evaluation_node (Node 5)."""

    @patch("interview.nodes.get_structured_thinking_llm")
    def test_generate_final_evaluation_synthesis(self, mock_get_llm):
        """Synthesizes verbatim transcript and evaluations into FinalEvaluation model."""
        expected_report = FinalEvaluation(
            overall_score=88.5,
            overall_status="PASSED",
            topic_breakdown=[
                TopicEvaluationSummary(
                    topic_id=1,
                    topic_name="Academic Fit",
                    average_score=88.5,
                    is_passed=True,
                    summary_feedback="Demonstrated high technical competence.",
                )
            ],
            strengths=["Detailed knowledge of course modules"],
            areas_for_improvement=["Elaborate more on post-study plans"],
            recommendation="Recommend visa credibility and course admission.",
        )

        mock_llm = MagicMock()
        mock_llm.invoke.return_value = expected_report
        mock_get_llm.return_value = mock_llm

        state: InterviewState = {
            "student_data": StudentData(
                student_id="STU-01",
                full_name="Alex",
                target_university="Herts",
                target_course="MSc CS",
            ),
            "university_data": UniversityData(
                university_id="HERTS-01",
                official_name="Herts",
                target_course="MSc CS",
            ),
            "messages": [
                AIMessage(content="Why this course?"),
                HumanMessage(content="Because of the advanced curriculum."),
            ],
            "evaluations": [
                EvaluationRecord(
                    topic_id=1,
                    question_id=0,
                    followup_order=None,
                    turn_type="question",
                    attempt_number=1,
                    accuracy_score=88.5,
                    is_passed=True,
                    matched_keywords=["advanced curriculum"],
                    unmatched_keywords=[],
                    feedback="Very good.",
                )
            ],
        }

        result = generate_final_evaluation_node(state)

        self.assertEqual(result.get("interview_status"), "completed")
        report: FinalEvaluation = result.get("final_evaluation")
        self.assertIsNotNone(report)
        self.assertEqual(report.overall_score, 88.5)
        self.assertEqual(report.overall_status, "PASSED")
        self.assertEqual(len(report.topic_breakdown), 1)
        self.assertEqual(report.strengths, ["Detailed knowledge of course modules"])


if __name__ == "__main__":
    unittest.main()
