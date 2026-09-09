"""
Hierarchical turn sequencing utilities for the Nested Tree Architecture (Pattern A).
Leverages native Pydantic models (TopicItem -> QuestionItem -> FollowupItem)
for direct, type-safe cursor progression across topics, questions, and follow-ups.
"""
from typing import List, Optional, Tuple
from interview.state import (
    EvaluationRecord,
    InterviewState,
    TopicItem,
    QuestionItem,
    FollowupItem,
)


def get_latest_evaluation(state: InterviewState) -> Optional[EvaluationRecord]:
    """Retrieves the most recent evaluation record from state history."""
    evals = state.get("evaluations", [])
    return evals[-1] if evals else None


def is_current_turn_reask(state: InterviewState) -> bool:
    """
    Determines if current turn is a re-ask.
    Returns True if the latest evaluation for the current turn failed on attempt 1.
    """
    latest = get_latest_evaluation(state)
    return bool(latest and latest.attempt_number == 1 and not latest.is_passed)


def get_current_turn_target(state: InterviewState) -> Tuple[str, List[str], str, bool]:
    """
    Direct hierarchical lookup: Resolves active question/follow-up text,
    expected evaluation keywords, topic name, and follow-up flag.

    Returns:
        Tuple of:
        - question_text (str): The question or follow-up to ask/evaluate.
        - keywords_list (List[str]): Expected keywords / evaluation rubrics.
        - topic_name (str): The name of the current topic.
        - is_followup (bool): True if current turn is a follow-up, False if primary question.
    """
    topics = state.get("topics", [])
    t_idx = state.get("current_topic_idx", 0)
    q_idx = state.get("current_question_idx", 0)
    f_idx = state.get("current_followup_idx", -1)

    if not topics or t_idx >= len(topics):
        return ("", [], "Completed", False)

    topic = topics[t_idx]
    if not topic.questions or q_idx >= len(topic.questions):
        return ("", [], topic.name, False)

    question_obj = topic.questions[q_idx]

    # Primary standalone question (f_idx == -1)
    if f_idx < 0:
        return (question_obj.question, question_obj.expected_answer_keywords, topic.name, False)

    # Follow-up probe question (f_idx >= 0)
    if f_idx < len(question_obj.followups):
        f_obj = question_obj.followups[f_idx]
        return (f_obj.followup, f_obj.expected_answer_keywords, topic.name, True)

    return ("", [], topic.name, False)


def advance_turn(state: InterviewState) -> dict:
    """
    Idiomatic LangGraph Turn Sequencer (Pattern A):
    1. If turn was a failed attempt 1, re-asks (preserves existing cursors).
    2. Advances through follow-ups under the current question.
    3. Advances to the next question in the current topic (if any).
    4. Advances to the next topic with questions (skipping any empty topics).
    5. Concludes the interview once all topics and questions are exhausted.
    """
    if is_current_turn_reask(state):
        return {}

    topics = state.get("topics", [])
    t_idx = state.get("current_topic_idx", 0)
    q_idx = state.get("current_question_idx", 0)
    f_idx = state.get("current_followup_idx", -1)

    if not topics or t_idx >= len(topics):
        return {"interview_status": "completed"}

    topic = topics[t_idx]
    if not topic.questions or q_idx >= len(topic.questions):
        # Current topic has no questions; advance to next available topic
        for next_t in range(t_idx + 1, len(topics)):
            if topics[next_t].questions:
                return {"current_topic_idx": next_t, "current_question_idx": 0, "current_followup_idx": -1}
        return {"interview_status": "completed"}

    question_obj = topic.questions[q_idx]

    # 1. Advance through follow-up probe questions
    if f_idx + 1 < len(question_obj.followups):
        return {"current_followup_idx": f_idx + 1}

    # 2. Advance to next question in same topic (if any)
    if q_idx + 1 < len(topic.questions):
        return {"current_question_idx": q_idx + 1, "current_followup_idx": -1}

    # 3. Advance to next topic with questions (skip any empty topics)
    for next_t in range(t_idx + 1, len(topics)):
        if topics[next_t].questions:
            return {"current_topic_idx": next_t, "current_question_idx": 0, "current_followup_idx": -1}

    # 4. All topics and questions exhausted -> Conclude interview
    return {"interview_status": "completed"}


# Backward compatibility aliases
is_active_turn_reask = is_current_turn_reask
get_active_turn_target = get_current_turn_target
get_next_relational_turn = advance_turn
