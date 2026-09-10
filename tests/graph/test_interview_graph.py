import sys
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch

src_path = str(Path(__file__).resolve().parent.parent.parent / "src")
if src_path not in sys.path:
    sys.path.insert(0, src_path)

from langgraph.graph import END, START
from interview.graph import (
    create_interview_graph,
    interview_graph,
    route_after_ask,
    route_after_init,
    route_start,
)
from interview.state import (
    FinalEvaluation,
    FollowupItem,
    InterviewState,
    QuestionItem,
    TopicItem,
)
from langchain_core.messages import AIMessage, HumanMessage


class TestInterviewGraphRouting(unittest.TestCase):
    """Unit tests for LangGraph conditional edge routers."""

    def test_route_start_uninitialized(self):
        """When state has no topics or questions and is not completed, route to generate_questions."""
        state: InterviewState = {
            "interview_status": "not_started",
            "topics": [],
        }
        self.assertEqual(route_start(state), "generate_questions")

    def test_route_start_empty_state(self):
        """Empty dictionary state routes to generate_questions."""
        state: InterviewState = {}
        self.assertEqual(route_start(state), "generate_questions")

    def test_route_start_with_topics_ready_to_ask(self):
        """When state has topics generated and status is not in_progress, route to ask_question."""
        topic = TopicItem(
            id=1,
            name="Academic Fit",
            questions=[QuestionItem(question="Why this course?", expected_answer_keywords=["AI"])],
        )
        state: InterviewState = {
            "topics": [topic],
            "interview_status": "not_started",
        }
        self.assertEqual(route_start(state), "ask_question")

    def test_route_start_in_progress(self):
        """When interview is in_progress and candidate provides input, route to evaluate_answer."""
        state: InterviewState = {
            "interview_status": "in_progress",
            "topics": [
                TopicItem(
                    id=1,
                    name="Academic Fit",
                    questions=[QuestionItem(question="Q1", expected_answer_keywords=["AI"])],
                )
            ],
            "messages": [HumanMessage(content="My answer here")],
        }
        self.assertEqual(route_start(state), "evaluate_answer")

    def test_route_start_completed_needs_final_evaluation(self):
        """When interview is marked completed but lacks final_evaluation, route to generate_final_evaluation."""
        state: InterviewState = {
            "interview_status": "completed",
            "final_evaluation": None,
        }
        self.assertEqual(route_start(state), "generate_final_evaluation")

    def test_route_start_completed_with_final_evaluation(self):
        """When interview is marked completed and has final_evaluation, route to END."""
        mock_eval = FinalEvaluation(
            overall_score=85.0,
            overall_status="PASSED",
            topic_breakdown=[],
            strengths=["Clear articulation"],
            areas_for_improvement=["More depth on modules"],
            recommendation="Strong Pass",
        )
        state: InterviewState = {
            "interview_status": "completed",
            "final_evaluation": mock_eval,
        }
        self.assertEqual(route_start(state), END)

    def test_route_after_ask_in_progress(self):
        """When an interview turn is asked and ongoing, route to END to wait for candidate voice input."""
        state: InterviewState = {
            "interview_status": "in_progress",
            "messages": [AIMessage(content="What modules did you choose?")],
        }
        self.assertEqual(route_after_ask(state), END)

    def test_route_after_ask_completed(self):
        """When ask_question concludes the interview, route to generate_final_evaluation."""
        state: InterviewState = {
            "interview_status": "completed",
            "messages": [AIMessage(content="Thank you, the interview is now concluded.")],
        }
        self.assertEqual(route_after_ask(state), "generate_final_evaluation")

    def test_route_after_init_alias(self):
        """Backward compatibility alias route_after_init behaves identically to route_start."""
        self.assertIs(route_after_init, route_start)


class TestInterviewGraphStructure(unittest.TestCase):
    """Validates structural assembly of the compiled LangGraph workflow."""

    def test_compiled_graph_nodes(self):
        """Graph contains all required cognitive and sequencing nodes."""
        graph = create_interview_graph()
        self.assertIsNotNone(graph)
        node_keys = graph.nodes.keys()
        expected_nodes = [
            "generate_questions",
            "evaluate_answer",
            "process_answer",
            "ask_question",
            "generate_final_evaluation",
        ]
        for node in expected_nodes:
            self.assertIn(node, node_keys)

    def test_singleton_graph_instance(self):
        """Pre-compiled interview_graph instance is ready for execution."""
        self.assertIsNotNone(interview_graph)
        self.assertTrue(hasattr(interview_graph, "invoke"))
        self.assertTrue(hasattr(interview_graph, "stream"))


class TestInterviewGraphExecution(unittest.TestCase):
    """End-to-end integration and mock tests for graph turn executions and checkpoints."""

    def setUp(self):
        self.sample_topics = [
            TopicItem(
                id=1,
                name="Academic Fit & Course Selection",
                expected_time_to_ans=45,
                questions=[
                    QuestionItem(
                        question="Why MSc AI?",
                        expected_answer_keywords=["Machine Learning", "Python"],
                        followups=[
                            FollowupItem(
                                followup_order=1,
                                followup="Which specific AI module?",
                                expected_answer_keywords=["Deep Learning"],
                            )
                        ],
                    )
                ],
            )
        ]

    @patch("interview.nodes.get_speech_llm")
    def test_graph_start_turn_asks_first_question(self, mock_speech_llm):
        """Starting graph with topics executes ask_question_node and persists state."""
        mock_model = MagicMock()
        mock_model.invoke.return_value = AIMessage(content="Welcome. Why did you choose MSc AI?")
        mock_speech_llm.return_value = mock_model

        graph = create_interview_graph()
        config = {"configurable": {"thread_id": "test-graph-start-thread"}}

        init_state: InterviewState = {
            "topics": self.sample_topics,
            "current_topic_idx": 0,
            "current_question_idx": 0,
            "current_followup_idx": -1,
            "interview_status": "not_started",
            "evaluations": [],
            "messages": [],
        }

        result = graph.invoke(init_state, config=config)

        self.assertEqual(result.get("interview_status"), "in_progress")
        messages = result.get("messages", [])
        self.assertTrue(len(messages) > 0)
        self.assertIn("Why did you choose MSc AI?", messages[-1].content)

    @patch("interview.nodes.get_structured_thinking_llm")
    @patch("interview.nodes.get_speech_llm")
    def test_graph_active_turn_evaluates_and_progresses(self, mock_speech_llm, mock_thinking_llm):
        """Active turn executes evaluate_answer -> process_answer -> ask_question cycle."""
        # 1. Mock answer evaluation output
        from interview.state import AnswerAccuracyEvaluation
        mock_eval_model = MagicMock()
        mock_eval_model.invoke.return_value = AnswerAccuracyEvaluation(
            accuracy_score=88.0,
            is_passed=True,
            matched_keywords=["Machine Learning", "Python"],
            unmatched_keywords=[],
            feedback="Strong technical answer.",
        )
        mock_thinking_llm.return_value = mock_eval_model

        # 2. Mock speech asking output
        mock_ask_model = MagicMock()
        mock_ask_model.invoke.return_value = AIMessage(content="Great. Which specific AI module will you focus on?")
        mock_speech_llm.return_value = mock_ask_model

        graph = create_interview_graph()
        config = {"configurable": {"thread_id": "test-graph-active-turn"}}

        # State with active question asked and candidate answering
        active_state: InterviewState = {
            "topics": self.sample_topics,
            "current_topic_idx": 0,
            "current_question_idx": 0,
            "current_followup_idx": -1,
            "interview_status": "in_progress",
            "evaluations": [],
            "messages": [
                AIMessage(content="Why MSc AI?"),
                HumanMessage(content="I have background in Python and Machine Learning projects."),
            ],
        }

        result = graph.invoke(active_state, config=config)

        # Verified evaluation appended
        evals = result.get("evaluations", [])
        self.assertEqual(len(evals), 1)
        self.assertEqual(evals[0].accuracy_score, 88.0)
        self.assertTrue(evals[0].is_passed)

        # Verified cursor advanced to follow-up (current_followup_idx == 0)
        self.assertEqual(result.get("current_followup_idx"), 0)

        # Verified next question formulated
        messages = result.get("messages", [])
        self.assertIn("Which specific AI module", messages[-1].content)

    @patch("interview.nodes.get_structured_thinking_llm")
    def test_graph_final_evaluation_transition(self, mock_thinking_llm):
        """When state is completed, graph routes to generate_final_evaluation and finishes at END."""
        mock_final = FinalEvaluation(
            overall_score=92.0,
            overall_status="PASSED",
            topic_breakdown=[],
            strengths=["Excellent preparation"],
            areas_for_improvement=[],
            recommendation="Pass without reservations",
        )
        mock_structured = MagicMock()
        mock_structured.invoke.return_value = mock_final
        mock_thinking_llm.return_value = mock_structured

        graph = create_interview_graph()
        config = {"configurable": {"thread_id": "test-graph-final-eval"}}

        completed_state: InterviewState = {
            "interview_status": "completed",
            "final_evaluation": None,
            "topics": self.sample_topics,
            "messages": [
                AIMessage(content="Why MSc AI?"),
                HumanMessage(content="My passion is Machine Learning."),
                AIMessage(content="Interview concluded. Thank you!"),
            ],
            "evaluations": [],
        }

        result = graph.invoke(completed_state, config=config)

        self.assertEqual(result.get("interview_status"), "completed")
        self.assertIsNotNone(result.get("final_evaluation"))
        self.assertEqual(result["final_evaluation"].overall_score, 92.0)
        self.assertEqual(result["final_evaluation"].overall_status, "PASSED")


if __name__ == "__main__":
    unittest.main()
