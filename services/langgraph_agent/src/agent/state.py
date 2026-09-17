from typing import Any, Optional, TypedDict


class QuestionGenerationState(TypedDict, total=False):
    """State for Graph 1: question_generation_graph (Admin workflow)."""
    title: str
    difficulty: str
    curriculum_text: str
    university_id: Optional[str]
    synthesized_topics: list[dict[str, Any]]
    is_reviewed_by_admin: bool
    admin_modifications: Optional[list[dict[str, Any]]]
    published_bank_id: Optional[str]
    error: Optional[str]


class TurnRecord(TypedDict):
    turn_type: str  # question, followup, reask
    reference_id: str
    spoken_prompt: str
    candidate_transcript: str
    score: float
    rubric_hits: list[str]
    missed_keywords: list[str]


class InterviewExecutionState(TypedDict, total=False):
    """
    State for Graph 2: interview_execution_graph (Student Live Runtime).
    STRICT INVARIANT: Operates purely on pre-approved questions fetched from SQLite.
    ZERO on-the-fly question generation is permitted.
    """
    user_id: str
    bank_id: str
    bank_title: str
    difficulty: str
    topics: list[dict[str, Any]]
    current_topic_index: int
    current_question_index: int
    current_followup_index: int
    attempt_count: int
    is_reask_active: bool
    current_prompt: str
    expected_time_to_ans: int
    expected_keywords: list[str]
    latest_transcript: str
    latest_score: float
    turns: list[TurnRecord]
    is_interview_concluded: bool
    overall_score: float
    ukvi_recommendation: str  # Genuine, Inconclusive, Not Genuine
    final_report_json: str
    active_question_id: str
    active_question_hits: list[str]
    total_question_keywords: list[str]
    keyword_ledger: dict[str, list[str]]

