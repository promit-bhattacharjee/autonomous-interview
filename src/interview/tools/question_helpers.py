"""
Helper utilities for resolving active questions, follow-ups, and turn types in the interview graph.
"""
from typing import List, Optional, Tuple
from interview.state import EvaluationRecord, InterviewState, QuestionState, SuggestedFollowupState


def get_current_question(state: InterviewState) -> Optional[QuestionState]:
    """
    Retrieves the active QuestionState for the current question index.
    Returns None if all questions are completed.
    """
    questions = state.get("questions", [])
    index = state.get("current_question_index", 0)
    if 0 <= index < len(questions):
        return questions[index]
    return None


def get_question_followups(state: InterviewState, question_id: int) -> List[SuggestedFollowupState]:
    """
    Retrieves all SuggestedFollowupState objects for a given question_id,
    sorted sequentially by followup_order.
    """
    return sorted(
        [f for f in state.get("suggested_followups", []) if f.question_id == question_id],
        key=lambda f: f.followup_order,
    )


def get_current_followup(state: InterviewState) -> Optional[SuggestedFollowupState]:
    """
    Retrieves the active SuggestedFollowupState for the active main question
    according to current_followup_index.
    Returns None if all questions are finished or no follow-up exists at this index.
    """
    current_q = get_current_question(state)
    if not current_q:
        return None

    followups = get_question_followups(state, current_q.question_id)
    f_idx = state.get("current_followup_index", 0)
    if 0 <= f_idx < len(followups):
        return followups[f_idx]
    return None


def is_followup_turn(state: InterviewState) -> bool:
    """
    Identifies whether the current active turn is a follow-up question.
    Returns True if state['is_followup'] is True and a valid matching follow-up exists;
    otherwise returns False (indicating a main question).
    """
    if not state.get("is_followup", False):
        return False
    return get_current_followup(state) is not None


def get_active_turn_target(state: InterviewState) -> Tuple[str, List[str], str]:
    """
    Identifies and resolves the active target for the current turn.

    Returns:
        tuple of (question_text, expected_keywords, context_type)
        where context_type is 'Follow-up Question' or 'Main Question'.
    """
    current_q = get_current_question(state)
    if not current_q:
        return ("", [], "Completed")

    if is_followup_turn(state):
        followup = get_current_followup(state)
        if followup:
            label = f"Follow-up Question #{followup.followup_order}"
            return (followup.followup, followup.expected_answer_keywords, label)

    return (current_q.question, current_q.expected_answer_keywords, "Main Question")


def get_evaluations_for_question(state: InterviewState, question_id: int) -> List[EvaluationRecord]:
    """Retrieves all evaluations for a specific main question."""
    return [
        e for e in state.get("evaluations", [])
        if e.question_id == question_id and e.turn_type == "question"
    ]


def get_evaluations_for_followup(
    state: InterviewState, question_id: int, followup_order: Optional[int] = None
) -> List[EvaluationRecord]:
    """Retrieves all evaluations for a specific suggested follow-up."""
    return [
        e for e in state.get("evaluations", [])
        if e.question_id == question_id
        and e.turn_type == "suggested_followup"
        and (followup_order is None or e.followup_order == followup_order)
    ]


def get_topic_evaluations(state: InterviewState, topic_id: int) -> List[EvaluationRecord]:
    """Retrieves all evaluation records for a specific topic."""
    return [
        e for e in state.get("evaluations", [])
        if e.topic_id == topic_id
    ]


def get_topic_score(state: InterviewState, topic_id: int) -> float:
    """Calculates average accuracy percentage across all turns for a specific topic."""
    evals = get_topic_evaluations(state, topic_id)
    if not evals:
        return 0.0
    return sum(e.accuracy_score for e in evals) / len(evals)


def get_latest_evaluation(state: InterviewState) -> Optional[EvaluationRecord]:
    """Retrieves the most recent evaluation record from state."""
    evals = state.get("evaluations", [])
    return evals[-1] if evals else None


def get_evaluations_for_turn(
    state: InterviewState,
    question_id: int,
    turn_type: str,
    followup_order: Optional[int] = None,
) -> List[EvaluationRecord]:
    """Retrieves evaluations for a specific question/follow-up turn."""
    return [
        e for e in state.get("evaluations", [])
        if e.question_id == question_id
        and e.turn_type == turn_type
        and (followup_order is None or e.followup_order == followup_order)
    ]
