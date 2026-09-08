"""
Relational helper utilities for querying active questions, topics, follow-ups,
and sequencing interview turns without imperative array indices.
"""
from typing import List, Optional, Tuple
from interview.state import (
    EvaluationRecord,
    InterviewState,
    QuestionState,
    SuggestedFollowupState,
    TopicState,
)


def get_active_question(state: InterviewState) -> Optional[QuestionState]:
    """
    Relational lookup: Retrieves the QuestionState matching active_question_id.
    Falls back to the first question in sequence if active_question_id is not set.
    """
    questions = state.get("questions", [])
    if not questions:
        return None

    active_id = state.get("active_question_id")
    if active_id is not None:
        for q in questions:
            if q.question_id == active_id:
                return q

    # Fallback to first question by topic_order and question_order
    topics_dict = {t.id: t.topic_order for t in state.get("topics", [])}
    sorted_questions = sorted(
        questions,
        key=lambda q: (topics_dict.get(q.topic_id, 0), q.question_order),
    )
    return sorted_questions[0] if sorted_questions else None


def get_active_topic(state: InterviewState) -> Optional[TopicState]:
    """
    Relational lookup: Retrieves the TopicState matching active_topic_id.
    Falls back to the topic of the active question.
    """
    topics = state.get("topics", [])
    active_t_id = state.get("active_topic_id")

    if active_t_id is not None:
        for t in topics:
            if t.id == active_t_id:
                return t

    active_q = get_active_question(state)
    if active_q is not None:
        for t in topics:
            if t.id == active_q.topic_id:
                return t

    return topics[0] if topics else None


def get_question_followups(state: InterviewState, question_id: int) -> List[SuggestedFollowupState]:
    """
    Relational query: Retrieves all SuggestedFollowupState records for a given question_id,
    sorted by followup_order.
    """
    return sorted(
        [f for f in state.get("suggested_followups", []) if f.question_id == question_id],
        key=lambda f: f.followup_order,
    )


def get_active_followup(state: InterviewState) -> Optional[SuggestedFollowupState]:
    """
    Relational lookup: Retrieves the SuggestedFollowupState matching
    active_question_id and active_followup_order.
    """
    followup_order = state.get("active_followup_order")
    if followup_order is None:
        return None

    active_q = get_active_question(state)
    if not active_q:
        return None

    for f in state.get("suggested_followups", []) if state.get("suggested_followups") else []:
        if f.question_id == active_q.question_id and f.followup_order == followup_order:
            return f

    return None


def is_active_turn_followup(state: InterviewState) -> bool:
    """Relational check: Returns True if active_followup_order is set."""
    return state.get("active_followup_order") is not None


def get_evaluations_for_turn(
    state: InterviewState,
    question_id: int,
    turn_type: str,
    followup_order: Optional[int] = None,
) -> List[EvaluationRecord]:
    """Relational query: Retrieves all evaluation records for a specific question/follow-up turn."""
    return [
        e for e in state.get("evaluations", [])
        if e.question_id == question_id
        and e.turn_type == turn_type
        and (followup_order is None or e.followup_order == followup_order)
    ]


def is_active_turn_reask(state: InterviewState) -> bool:
    """
    Derived relational state: Determines if current turn is a re-ask.
    Returns True if the latest evaluation for the active target failed on attempt 1.
    """
    active_q = get_active_question(state)
    if not active_q:
        return False

    turn_type = "suggested_followup" if is_active_turn_followup(state) else "question"
    followup_order = state.get("active_followup_order")

    prior_evals = get_evaluations_for_turn(
        state, active_q.question_id, turn_type, followup_order=followup_order
    )
    if prior_evals:
        latest = prior_evals[-1]
        return bool(latest.attempt_number == 1 and not latest.is_passed)

    return False


def get_active_turn_target(state: InterviewState) -> Tuple[str, List[str], str]:
    """
    Resolves the active text, keywords, and context label relationally.
    """
    active_q = get_active_question(state)
    if not active_q:
        return ("", [], "Completed")

    if is_active_turn_followup(state):
        followup = get_active_followup(state)
        if followup:
            label = f"Follow-up Question #{followup.followup_order}"
            return (followup.followup, followup.expected_answer_keywords, label)

    return (active_q.question, active_q.expected_answer_keywords, "Main Question")


def get_next_relational_turn(
    state: InterviewState,
) -> Tuple[Optional[int], Optional[int], Optional[int], bool]:
    """
    Relational turn sequencer:
    Finds the next active foreign keys in relation order:
    1. Remaining follow-ups for active question
    2. Next question in current topic (by question_order)
    3. Next topic (by topic_order) and its first question
    4. If no more items, returns is_completed = True

    Returns:
        Tuple of (next_topic_id, next_question_id, next_followup_order, is_completed)
    """
    active_q = get_active_question(state)
    if not active_q:
        return (None, None, None, True)

    # 1. Check if unasked follow-ups remain for the active question
    followups = get_question_followups(state, active_q.question_id)
    curr_f_order = state.get("active_followup_order")

    if curr_f_order is None and followups:
        # First follow-up
        return (active_q.topic_id, active_q.question_id, followups[0].followup_order, False)
    elif curr_f_order is not None:
        remaining_f = [f for f in followups if f.followup_order > curr_f_order]
        if remaining_f:
            return (active_q.topic_id, active_q.question_id, remaining_f[0].followup_order, False)

    # 2. Advance to next question in current topic
    topic_questions = sorted(
        [q for q in state.get("questions", []) if q.topic_id == active_q.topic_id],
        key=lambda q: q.question_order,
    )
    remaining_q = [q for q in topic_questions if q.question_order > active_q.question_order]
    if remaining_q:
        return (active_q.topic_id, remaining_q[0].question_id, None, False)

    # 3. Advance to next topic
    sorted_topics = sorted(state.get("topics", []), key=lambda t: t.topic_order)
    active_topic = get_active_topic(state)
    curr_t_order = active_topic.topic_order if active_topic else 0

    next_topics = [t for t in sorted_topics if t.topic_order > curr_t_order]
    if next_topics:
        next_topic = next_topics[0]
        next_t_questions = sorted(
            [q for q in state.get("questions", []) if q.topic_id == next_topic.id],
            key=lambda q: q.question_order,
        )
        if next_t_questions:
            return (next_topic.id, next_t_questions[0].question_id, None, False)

    # 4. Interview concluded
    return (None, None, None, True)


def get_latest_evaluation(state: InterviewState) -> Optional[EvaluationRecord]:
    """Retrieves the most recent evaluation record from state."""
    evals = state.get("evaluations", [])
    return evals[-1] if evals else None


def get_topic_evaluations(state: InterviewState, topic_id: int) -> List[EvaluationRecord]:
    """Retrieves all evaluation records for a specific topic."""
    return [e for e in state.get("evaluations", []) if e.topic_id == topic_id]


def get_topic_score(state: InterviewState, topic_id: int) -> float:
    """Calculates average accuracy percentage across all turns for a specific topic."""
    evals = get_topic_evaluations(state, topic_id)
    if not evals:
        return 0.0
    return sum(e.accuracy_score for e in evals) / len(evals)
