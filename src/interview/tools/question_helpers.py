"""
Helper utilities for resolving active questions, follow-ups, and turn types in the interview graph.
"""
from typing import List, Optional, Tuple
from interview.state import InterviewState, QuestionState, SuggestedFollowupState


def get_current_followup(state: InterviewState) -> Optional[SuggestedFollowupState]:
    """
    Retrieves the matching SuggestedFollowupState for the active main question.
    Returns None if all questions are finished or no follow-up exists for this question.
    """
    questions = state.get("questions", [])
    index = state.get("current_question_index", 0)
    if index >= len(questions):
        return None

    current_q = questions[index]
    followups = state.get("suggested_followups", [])
    return next((f for f in followups if f.question_id == current_q.question_id), None)


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
    questions = state.get("questions", [])
    index = state.get("current_question_index", 0)
    if index >= len(questions):
        return ("", [], "Completed")

    current_q = questions[index]

    if is_followup_turn(state):
        followup = get_current_followup(state)
        if followup:
            return (followup.followup, followup.expected_answer_keywords, "Follow-up Question")

    return (current_q.question, current_q.expected_answer_keywords, "Main Question")
