from typing import List
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from interview.llm import get_llm
from interview.prompts import (
    ANSWER_EVALUATION_HUMAN_PROMPT,
    ANSWER_EVALUATION_SYSTEM_PROMPT,
    DOCUMENT_EXTRACTION_PROMPT,
    QUESTION_GENERATION_FROM_STATE_PROMPT,
    QUESTION_GENERATION_HUMAN_PROMPT,
    INTERVIEW_QUESTION_PROMPT,
    INTERVIEW_CONCLUDE_PROMPT,
)
from interview.state import (
    AnswerAccuracyEvaluation,
    EvaluationRecord,
    InitialExtracedTextOutputState,
    InitialExtracedTextState,
    InterviewState,
    QuestionListModelState,
)
from interview.tools.question_helpers import (
    get_active_followup,
    get_active_question,
    get_active_topic,
    get_active_turn_target,
    get_evaluations_for_turn,
    get_latest_evaluation,
    get_next_relational_turn,
    is_active_turn_followup,
    is_active_turn_reask,
)


def extract_initial_text(state: InitialExtracedTextState) -> dict:
    """
    Reads the initial raw questions/resume/material from state,
    and calls the LLM with structured output to extract key information.
    """
    raw_material = state.get("extraced_text", "")

    messages = [
        SystemMessage(content=DOCUMENT_EXTRACTION_PROMPT),
        HumanMessage(content=f"Document Text:\n{raw_material}"),
    ]

    llm = get_llm(model_name="gemini-3.6-flash", model_provider="google_genai")
    structured_llm = llm.with_structured_output(InitialExtracedTextOutputState)
    result: InitialExtracedTextOutputState = structured_llm.invoke(messages)

    expected_time = (
        getattr(result, "expected_total_time_to_ans", None)
        or getattr(result, "expected_time_to_ans", None)
        or state.get("expected_total_time_to_ans")
        or state.get("expected_time_to_ans")
        or 45
    )

    return {
        "extraced_text": getattr(result, "extraced_text", raw_material),
        "difficulty": getattr(result, "difficulty", state.get("difficulty", "Medium")),
        "expected_total_time_to_ans": expected_time,
        "expected_time_to_ans": expected_time,
        "iterations": 0,
    }


def generate_questions_node(state: InterviewState) -> dict:
    """
    Takes the extracted information, difficulty, and time from state,
    and generates relational topics, questions, and suggested follow-ups.
    """
    expected_time = state.get("expected_total_time_to_ans") or state.get("expected_time_to_ans") or 45
    expected_kw = state.get("expected_answer_keywords", [])
    human_content = QUESTION_GENERATION_HUMAN_PROMPT.format(
        extraced_text=state.get("extraced_text", ""),
        difficulty=state.get("difficulty", "Medium"),
        expected_time_to_ans=expected_time,
        expected_answer_keywords=", ".join(expected_kw) if expected_kw else "Core domain concepts",
    )

    messages = [
        SystemMessage(content=QUESTION_GENERATION_FROM_STATE_PROMPT),
        HumanMessage(content=human_content),
    ]

    llm = get_llm(model_name="gemini-3.6-flash", model_provider="google_genai")
    structured_llm = llm.with_structured_output(QuestionListModelState)
    result: QuestionListModelState = structured_llm.invoke(messages)

    first_topic_id = result.topics[0].id if result.topics else None
    first_question_id = result.questions[0].question_id if result.questions else None

    return {
        "topics": result.topics,
        "questions": result.questions,
        "suggested_followups": result.suggested_followups,
        "expected_total_time_to_ans": result.expected_total_time_to_ans,
        "difficulty": result.difficulty,
        "active_topic_id": first_topic_id,
        "active_question_id": first_question_id,
        "active_followup_order": None,
        "interview_status": "in_progress",
        "evaluations": [],
    }


def _ensure_text_content(msg: AIMessage) -> AIMessage:
    """Normalizes list-based multimodal content blocks into clean string text."""
    if isinstance(msg.content, list):
        text_parts = [
            p.get("text", "") if isinstance(p, dict) else str(p)
            for p in msg.content
        ]
        msg.content = "".join(text_parts).strip()
    return msg


def evaluate_answer_node(state: InterviewState) -> dict:
    """
    Evaluates candidate's latest response against the active relational question,
    topic, and target expected_answer_keywords (checking >= 70% threshold).
    Appends an EvaluationRecord with relational foreign keys.
    """
    messages_list = state.get("messages", [])
    last_ai_msg = next((m for m in reversed(messages_list) if isinstance(m, AIMessage)), None)
    last_human_msg = next((m for m in reversed(messages_list) if isinstance(m, HumanMessage)), None)

    active_q = get_active_question(state)
    if not last_human_msg or not active_q:
        return {}

    active_topic = get_active_topic(state)
    topic_name = active_topic.name if active_topic else "Technical Proficiency"

    # Determine keywords and context via relational helper
    question_text, keywords_list, context_type = get_active_turn_target(state)

    prompt_content = ANSWER_EVALUATION_HUMAN_PROMPT.format(
        topic_name=topic_name,
        context_type=context_type,
        last_ai_message=last_ai_msg.content if last_ai_msg else "N/A",
        last_human_message=last_human_msg.content if last_human_msg else "",
        expected_keywords=", ".join(keywords_list) if keywords_list else "General technical accuracy and relevant concepts",
    )

    eval_messages = [
        SystemMessage(content=ANSWER_EVALUATION_SYSTEM_PROMPT),
        HumanMessage(content=prompt_content),
    ]

    llm = get_llm(model_name="gemini-3.6-flash", model_provider="google_genai")
    structured_llm = llm.with_structured_output(AnswerAccuracyEvaluation)
    result: AnswerAccuracyEvaluation = structured_llm.invoke(eval_messages)

    is_followup = is_active_turn_followup(state)
    followup_order = state.get("active_followup_order")
    turn_type = "suggested_followup" if is_followup else "question"

    prior_evals = get_evaluations_for_turn(
        state, active_q.question_id, turn_type, followup_order=followup_order
    )
    attempt_number = len(prior_evals) + 1

    record = EvaluationRecord(
        topic_id=active_q.topic_id,
        question_id=active_q.question_id,
        followup_order=followup_order,
        turn_type=turn_type,
        attempt_number=attempt_number,
        accuracy_score=float(result.accuracy_score),
        is_passed=bool(result.is_passed),
        matched_keywords=result.matched_keywords,
        unmatched_keywords=result.unmatched_keywords,
        feedback=result.feedback,
    )

    current_evaluations = list(state.get("evaluations", []))
    current_evaluations.append(record)

    return {
        "evaluations": current_evaluations,
    }


def ask_question_node(state: InterviewState) -> dict:
    """
    Interviewer turn: Formulates and asks the active question, follow-up, or re-ask.
    Concludes the interview if all questions are completed.
    """
    active_q = get_active_question(state)
    is_completed = state.get("interview_status") == "completed" or not active_q

    # Check if interview is completed
    if is_completed:
        llm = get_llm(model_name="gemini-3.6-flash", model_provider="google_genai")
        conclude_msg = llm.invoke([
            SystemMessage(content=INTERVIEW_CONCLUDE_PROMPT),
            HumanMessage(content="All questions are completed. Please deliver your concluding remarks."),
        ])
        return {
            "interview_status": "completed",
            "messages": [_ensure_text_content(conclude_msg)],
            "active_topic_id": None,
            "active_question_id": None,
            "active_followup_order": None,
        }

    active_topic = get_active_topic(state)
    topic_name = active_topic.name if active_topic else "Technical Proficiency"

    is_reask = is_active_turn_reask(state)
    is_followup = is_active_turn_followup(state)
    question_to_ask, _, _ = get_active_turn_target(state)

    # Retrieve unmatched keywords from latest evaluation if this turn is a re-ask
    latest_eval = get_latest_evaluation(state)
    unmatched_keywords = latest_eval.unmatched_keywords if (latest_eval and is_reask) else []

    prompt_content = INTERVIEW_QUESTION_PROMPT.format(
        topic_name=topic_name,
        question_text=question_to_ask,
        is_followup="Yes" if is_followup else "No",
        is_reask="Yes" if is_reask else "No",
        unmatched_keywords=", ".join(unmatched_keywords) if unmatched_keywords else "None",
    )

    history = state.get("messages", [])[-2:] if state.get("messages") else []
    if is_reask:
        request_instruction = (
            "The candidate's previous answer missed some key technical details or scored below the required threshold. "
            "Please politely acknowledge their previous response and re-ask or prompt them to elaborate on the question."
        )
    elif is_followup:
        request_instruction = "Please ask the candidate this follow-up question naturally."
    else:
        request_instruction = "Please introduce and present this interview question to the candidate."

    messages = [SystemMessage(content=prompt_content)] + list(history) + [HumanMessage(content=request_instruction)]

    llm = get_llm(model_name="gemini-3.6-flash", model_provider="google_genai")
    ai_response = llm.invoke(messages)

    return {
        "messages": [_ensure_text_content(ai_response)],
        "active_topic_id": active_q.topic_id,
        "active_question_id": active_q.question_id,
        "interview_status": "in_progress",
    }


def process_answer_node(state: InterviewState) -> dict:
    """
    Candidate response routing turn (Pure Relational State Machine):
    - If accuracy < 70% and this was the 1st attempt, retains active pointers for re-ask.
    - If accuracy >= 70% OR retry already used (attempt >= 2):
      Advances relationally to the next follow-up, next question, next topic, or completion.
    """
    active_q = get_active_question(state)
    if not active_q or state.get("interview_status") == "completed":
        return {"interview_status": "completed"}

    # 1. If this turn requires a re-ask, pointers remain on the active question/followup
    if is_active_turn_reask(state):
        return {}

    # 2. Advance to the next relational target
    next_topic_id, next_question_id, next_followup_order, is_completed = get_next_relational_turn(state)

    if is_completed or next_question_id is None:
        return {
            "interview_status": "completed",
            "active_topic_id": None,
            "active_question_id": None,
            "active_followup_order": None,
        }

    return {
        "active_topic_id": next_topic_id,
        "active_question_id": next_question_id,
        "active_followup_order": next_followup_order,
    }
