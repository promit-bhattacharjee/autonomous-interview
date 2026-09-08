import uuid
from typing import List, Optional, Tuple
from langchain_core.messages import HumanMessage
from interview.graph import interview_graph
from interview.state import QuestionState, TopicState


class InterviewSession:
    """
    Encapsulates the LangGraph session state and lifecycle.
    Keeps thread_id, checkpointing, and graph execution completely isolated
    from the audio/communication layer.
    """

    def __init__(
        self,
        session_id: Optional[str] = None,
        questions: Optional[List[QuestionState]] = None,
        topics: Optional[List[TopicState]] = None,
    ):
        self.session_id = session_id or f"session-{uuid.uuid4().hex[:8]}"
        self.config = {"configurable": {"thread_id": self.session_id}}
        self.questions = questions or []
        self.topics = topics or []
        self.latest_state = {}

    def start(self) -> str:
        """
        Initializes the interview session with direct questions.
        Executes START -> ask_question -> END.
        Returns the formulated first question string for TTS to speak.
        """
        first_topic_id = self.topics[0].id if self.topics else None
        first_question_id = self.questions[0].question_id if self.questions else None

        initial_state = {
            "topics": self.topics,
            "questions": self.questions,
            "suggested_followups": [],
            "active_topic_id": first_topic_id,
            "active_question_id": first_question_id,
            "active_followup_order": None,
            "evaluations": [],
            "messages": [],
        }

        self.latest_state = interview_graph.invoke(initial_state, config=self.config)
        first_question_text = self.latest_state.get("messages", [])[-1].content
        return first_question_text

    def submit_candidate_answer(self, candidate_text: str) -> Tuple[str, bool, dict]:
        """
        Feeds candidate's transcribed speech into the LangGraph brain.
        Executes: START -> evaluate_answer -> process_answer -> ask_question -> END.

        Returns:
            Tuple of:
            - next_text (str): Next question or concluding remarks to speak.
            - is_completed (bool): True if the interview has concluded.
            - eval_data (dict): Accuracy score and keyword coverage for live display.
        """
        self.latest_state = interview_graph.invoke(
            {"messages": [HumanMessage(content=candidate_text)]},
            config=self.config,
        )

        is_completed = self.latest_state.get("interview_status") == "completed"
        messages = self.latest_state.get("messages", [])
        next_text = messages[-1].content if messages else ""

        # Extract latest evaluation metrics relationally
        evals = self.latest_state.get("evaluations", [])
        latest_eval = evals[-1] if evals else None
        eval_data = {}
        if latest_eval:
            is_reask = bool(latest_eval.attempt_number == 1 and not latest_eval.is_passed)
            eval_data = {
                "accuracy_score": latest_eval.accuracy_score,
                "is_passed": latest_eval.is_passed,
                "matched_keywords": latest_eval.matched_keywords,
                "unmatched_keywords": latest_eval.unmatched_keywords,
                "feedback": latest_eval.feedback,
                "attempt_number": latest_eval.attempt_number,
                "is_reask": is_reask,
                "active_question_id": latest_eval.question_id,
                "active_topic_id": latest_eval.topic_id,
            }

        return next_text, is_completed, eval_data
