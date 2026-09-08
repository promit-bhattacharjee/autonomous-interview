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
    get_active_turn_target,
    get_current_followup,
    get_current_question,
    get_evaluations_for_turn,
    get_latest_evaluation,
    get_question_followups,
    is_followup_turn,
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

    return {
        "extraced_text": result.extraced_text,
        "difficulty": result.difficulty,
        "expected_total_words_to_ans": result.expected_total_words_to_ans,
        "expected_total_time_to_ans": result.expected_total_time_to_ans,
        "iterations": 0,
    }


def generate_questions_node(state: InterviewState) -> dict:
    """
    Takes the extracted information, difficulty, and time from state,
    and generates topics, questions, and suggested follow-ups.
    """
    human_content = QUESTION_GENERATION_HUMAN_PROMPT.format(
        extraced_text=state.get("extraced_text", ""),
        difficulty=state.get("difficulty", "Medium"),
        expected_time_to_ans=state.get("expected_total_time_to_ans", 30),
        expected_words_to_ans=state.get("expected_total_words_to_ans", 300),
    )

    messages = [
        SystemMessage(content=QUESTION_GENERATION_FROM_STATE_PROMPT),
        HumanMessage(content=human_content),
    ]

    llm = get_llm(model_name="gemini-3.6-flash", model_provider="google_genai")
    structured_llm = llm.with_structured_output(QuestionListModelState)
    result: QuestionListModelState = structured_llm.invoke(messages)

    first_topic_id = result.topics[0].id if result.topics else None

    return {
        "topics": result.topics,
        "questions": result.questions,
        "suggested_followups": result.suggested_followups,
        "expected_total_words_to_ans": result.expected_total_words_to_ans,
        "expected_total_time_to_ans": result.expected_total_time_to_ans,
        "difficulty": result.difficulty,
        "current_question_index": 0,
        "current_followup_index": 0,
        "is_followup": False,
        "is_reask": False,
        "interview_status": "in_progress",
        "evaluations": [],
        "topic_id": first_topic_id,
        "current_topic_id": first_topic_id,
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
    Evaluates candidate's latest response against the interviewer's prompt,
    the active topic, and target expected_answer_keywords (checking >= 70% threshold).
    Tracks matched and unmatched keywords.
    """
    messages_list = state.get("messages", [])
    last_ai_msg = next((m for m in reversed(messages_list) if isinstance(m, AIMessage)), None)
    last_human_msg = next((m for m in reversed(messages_list) if isinstance(m, HumanMessage)), None)

    if not last_human_msg or state.get("current_question_index", 0) >= len(state.get("questions", [])):
        return {}

    questions = state.get("questions", [])
    index = state.get("current_question_index", 0)
    q = questions[index]
    q_tid = q.topic_id

    # Locate topic name
    topic_name = "Technical Proficiency"
    for t in state.get("topics", []):
        if t.id == q_tid:
            topic_name = t.name
            break

    # Determine keywords and context via helper
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

    is_followup = is_followup_turn(state)
    followup_obj = get_current_followup(state) if is_followup else None
    turn_type = "suggested_followup" if is_followup else "question"
    followup_order = followup_obj.followup_order if followup_obj else None

    prior_evals = get_evaluations_for_turn(
        state, q.question_id, turn_type, followup_order=followup_order
    )
    attempt_number = len(prior_evals) + 1

    record = EvaluationRecord(
        topic_id=q_tid,
        question_id=q.question_id,
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
    Interviewer turn: Formulates and asks the active main question, follow-up, or re-ask.
    Concludes the interview if all questions are completed.
    """
    questions = state.get("questions", [])
    index = state.get("current_question_index", 0)
    is_reask = state.get("is_reask", False)

    # Retrieve unmatched keywords from the latest evaluation if this turn is a re-ask
    latest_eval = get_latest_evaluation(state)
    unmatched_keywords = latest_eval.unmatched_keywords if (latest_eval and is_reask) else []

    # Check if all questions are completed
    if index >= len(questions):
        llm = get_llm(model_name="gemini-3.6-flash", model_provider="google_genai")
        conclude_msg = llm.invoke([
            SystemMessage(content=INTERVIEW_CONCLUDE_PROMPT),
            HumanMessage(content="All questions are completed. Please deliver your concluding remarks."),
        ])
        return {
            "interview_status": "completed",
            "messages": [_ensure_text_content(conclude_msg)],
        }

    q = questions[index]
    q_tid = q.topic_id

    # Locate topic name
    topic_name = "Technical Proficiency"
    for t in state.get("topics", []):
        if t.id == q_tid:
            topic_name = t.name
            break

    # Determine question text and turn type via helpers
    is_followup = is_followup_turn(state)
    question_to_ask, _, _ = get_active_turn_target(state)

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
        "topic_id": q_tid,
        "current_topic_id": q_tid,
    }


def process_answer_node(state: InterviewState) -> dict:
    """
    Candidate response routing turn:
    Consumes evaluation results from relational evaluation records.
    - If accuracy < 70% and this was the 1st attempt, triggers a re-ask of the same question/followup.
    - If accuracy >= 70% (or 2nd attempt completed):
      - If on main question and follow-ups exist: branch to 1st follow-up (current_followup_index = 0).
      - If on a follow-up and more follow-ups remain: advance to next follow-up (current_followup_index += 1).
      - Otherwise: advance to next main question (current_question_index += 1, current_followup_index = 0, is_followup = False).
    """
    index = state.get("current_question_index", 0)
    questions = state.get("questions", [])

    if index >= len(questions):
        return {"interview_status": "completed"}

    current_q = questions[index]
    latest_eval = get_latest_evaluation(state)

    # 1. If accuracy is below threshold (< 70%) and this was the 1st attempt, re-ask once
    if latest_eval and not latest_eval.is_passed and latest_eval.attempt_number == 1:
        return {
            "is_reask": True,
        }

    # 2. If accuracy passed (>= 70%) OR retry was already used (attempt >= 2):
    q_followups = get_question_followups(state, current_q.question_id)
    f_idx = state.get("current_followup_index", 0)

    if not is_followup_turn(state):
        # Just finished main question: start follow-up sequence if follow-ups exist
        if q_followups:
            return {
                "is_reask": False,
                "is_followup": True,
                "current_followup_index": 0,
            }
    else:
        # Just finished a follow-up: check if more follow-ups remain for this question
        if f_idx + 1 < len(q_followups):
            return {
                "is_reask": False,
                "is_followup": True,
                "current_followup_index": f_idx + 1,
            }

    # If all follow-ups for this question are finished (or question had no follow-ups),
    # advance to the next main question
    return {
        "current_question_index": index + 1,
        "current_followup_index": 0,
        "is_followup": False,
        "is_reask": False,
    }
