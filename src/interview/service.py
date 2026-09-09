import threading
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
        if not (self.questions or self.topics or self.initial_payload):
            self.student_id = student_id or "UK-CAS-2026-9041"
            self.university_id = university_id or "UK-HERTS-01"
        else:
            self.student_id = student_id
            self.university_id = university_id
        self.difficulty = difficulty
        self.latest_state: Dict[str, Any] = {}
        self._lock = threading.Lock()

        # Orchestration Layer: Resolve data from data repository, enforcing strict Pydantic validation
        if self.student_data is None and self.student_id:
            from mock_api import fetch_student_api
            raw_student = fetch_student_api(self.student_id)
            if raw_student:
                self.student_data = StudentData(**raw_student)
        elif isinstance(self.student_data, dict):
            self.student_data = StudentData(**self.student_data)

        if self.university_data is None and self.university_id:
            from mock_api import fetch_university_api
            raw_univ = fetch_university_api(self.university_id)
            if raw_univ:
                self.university_data = UniversityData(**raw_univ)
        elif isinstance(self.university_data, dict):
            self.university_data = UniversityData(**self.university_data)

    def start(self) -> str:
        """
        Initializes the interview session.
        If direct questions were provided, executes START -> ask_question -> END.
        Otherwise, executes START -> generate_questions (using OpenRouter DeepSeek V4 Flash 0731) -> ask_question -> END.
        Returns the formulated first question string for TTS to speak.
        """
        if self.topics or self.questions:
            topics = list(self.topics)
            if topics and self.questions and not any(t.questions for t in topics):
                topic_map = {t.id: t for t in topics}
                for q in self.questions:
                    t_id = getattr(q, "topic_id", None)
                    if t_id and t_id in topic_map:
                        topic_map[t_id].questions.append(q)
                    else:
                        topics[0].questions.append(q)
            elif not topics and self.questions:
                topics = [
                    TopicState(
                        id=1,
                        name="Interview Topic",
                        questions=self.questions,
                    )
                ]

            initial_state = {
                "student_data": self.student_data,
                "university_data": self.university_data,
                "student_id": self.student_id,
                "university_id": self.university_id,
                "difficulty": self.difficulty,
                "topics": topics,
                "current_topic_idx": 0,
                "current_question_idx": 0,
                "current_followup_idx": -1,
                "interview_status": "not_started",
                "evaluations": [],
                "messages": [],
            }
        elif self.initial_payload:
            initial_state = dict(self.initial_payload)
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
        if self.latest_state.get("interview_status") == "completed":
            final_eval = self.get_final_evaluation()
            eval_data: Dict[str, Any] = {}
            if final_eval:
                eval_data["final_evaluation"] = final_eval
            return "", True, eval_data

        with self._lock:
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
