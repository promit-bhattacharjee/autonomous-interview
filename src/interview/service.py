import uuid
from typing import Any, Dict, List, Optional, Tuple
from langchain_core.messages import HumanMessage
from interview.graph import interview_graph
from interview.state import (
    FinalEvaluation,
    QuestionState,
    StudentData,
    TopicState,
    UniversityData,
)


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
        initial_payload: Optional[dict] = None,
        student_data: Optional[StudentData] = None,
        university_data: Optional[UniversityData] = None,
        student_id: Optional[str] = None,
        university_id: Optional[str] = None,
        difficulty: str = "Medium",
    ):
        self.session_id = session_id or f"session-{uuid.uuid4().hex[:8]}"
        self.config = {"configurable": {"thread_id": self.session_id}}
        self.questions = questions or []
        self.topics = topics or []
        self.initial_payload = initial_payload
        self.student_data = student_data
        self.university_data = university_data
        self.student_id = student_id or "UK-CAS-2026-9041"
        self.university_id = university_id or "UK-HERTS-01"
        self.difficulty = difficulty
        self.latest_state: Dict[str, Any] = {}

    def start(self) -> str:
        """
        Initializes the interview session.
        If direct questions were provided, executes START -> ask_question -> END.
        Otherwise, executes START -> generate_questions (using OpenRouter DeepSeek V4 Flash 0731) -> ask_question -> END.
        Returns the formulated first question string for TTS to speak.
        """
        if self.questions:
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
        elif self.initial_payload:
            initial_state = self.initial_payload
        else:
            initial_state = {
                "student_data": self.student_data,
                "university_data": self.university_data,
                "student_id": self.student_id,
                "university_id": self.university_id,
                "difficulty": self.difficulty,
                "interview_status": "not_started",
                "messages": [],
            }

        self.latest_state = interview_graph.invoke(initial_state, config=self.config)
        messages = self.latest_state.get("messages", [])
        first_question_text = messages[-1].content if messages else ""
        return first_question_text

    def submit_candidate_answer(self, candidate_text: str) -> Tuple[str, bool, dict]:
        """
        Feeds candidate's transcribed speech into the LangGraph brain.
        Executes: START -> evaluate_answer -> process_answer -> ask_question -> [generate_final_evaluation] -> END.

        Returns:
            Tuple of:
            - next_text (str): Next question or concluding remarks to speak.
            - is_completed (bool): True if the interview has concluded.
            - eval_data (dict): Accuracy score, keyword coverage, and final_evaluation (if concluded).
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
        eval_data: Dict[str, Any] = {}
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

        # If completed, attach the final evaluation report
        final_eval = self.get_final_evaluation()
        if final_eval:
            eval_data["final_evaluation"] = final_eval

        return next_text, is_completed, eval_data

    def get_final_evaluation(self) -> Optional[dict]:
        """Returns the final evaluation dictionary if generated."""
        final_eval = self.latest_state.get("final_evaluation")
        if final_eval:
            return final_eval.model_dump() if hasattr(final_eval, "model_dump") else final_eval
        return None
