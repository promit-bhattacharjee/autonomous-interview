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
    InitialExtracedTextOutputState,
    InitialExtracedTextState,
    InterviewState,
    QuestionListModelState,
)


def extract_initial_text(state: InitialExtracedTextState) -> dict:
    """
    Reads the initial raw questions/resume/material from state,
    and calls the LLM with structured output to extract key information.
    """
    raw_material = state.get("extraced_text", "")

    messages = [
        SystemMessage(content=DOCUMENT_EXTRACTION_PROMPT),
        HumanMessage(content=f"Document / Material to analyze:\n{raw_material}"),
    ]

    llm = get_llm(model_name="gemini-3.6-flash", model_provider="google_genai")
    structured_llm = llm.with_structured_output(InitialExtracedTextOutputState)
    result: InitialExtracedTextOutputState = structured_llm.invoke(messages)

    return result.model_dump()


def generate_questions_node(state: InitialExtracedTextState) -> dict:
    """
    Consumes the extracted text, difficulty, and duration requirements from InitialExtracedTextState,
    formats the prompt via QUESTION_GENERATION_HUMAN_PROMPT, generates the structured interview plan,
    and initializes turn-by-turn tracking in InterviewState.
    """
    human_content = QUESTION_GENERATION_HUMAN_PROMPT.format(
        extraced_text=state.get("extraced_text", ""),
        difficulty=state.get("difficulty", "Medium"),
        expected_time_to_ans=state.get("expected_time_to_ans", 30),
        expected_words_to_ans=state.get("expected_words_to_ans", 1000),
        expected_answer_keywords=",".join(state.get("expected_answer_keywords", [])),
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
        "is_followup": False,
        "interview_status": "in_progress",
        "retry_count": 0,
        "is_reask": False,
        "last_accuracy": 0.0,
        "is_passed": False,
        "matched_keywords": [],
        "unmatched_keywords": [],
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

    if not last_human_msg:
        return {
            "last_accuracy": 100.0,
            "is_passed": True,
            "matched_keywords": [],
            "unmatched_keywords": [],
        }

    questions = state.get("questions", [])
    index = state.get("current_question_index", 0)
    is_followup = state.get("is_followup", False)

    if index >= len(questions):
        return {
            "last_accuracy": 100.0,
            "is_passed": True,
            "matched_keywords": [],
            "unmatched_keywords": [],
        }

    q = questions[index]
    q_id = q.question_id
    q_tid = q.topic_id

    # Locate topic name
    topic_name = "Technical Proficiency"
    for t in state.get("topics", []):
        if t.id == q_tid:
            topic_name = t.name
            break

    # Determine keywords and context based on whether this is a follow-up or main question
    if is_followup:
        followups = state.get("suggested_followups", [])
        matching_f = [f for f in followups if f.question_id == q_id]
        if matching_f:
            keywords_list = matching_f[0].expected_answer_keywords
        else:
            keywords_list = q.expected_answer_keywords
        context_type = "Follow-up Question"
    else:
        keywords_list = q.expected_answer_keywords
        context_type = "Main Question"

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

    return {
        "last_accuracy": float(result.accuracy_score),
        "is_passed": bool(result.is_passed),
        "matched_keywords": result.matched_keywords,
        "unmatched_keywords": result.unmatched_keywords,
    }


def ask_question_node(state: InterviewState) -> dict:
    """
    Interviewer turn: Formulates and asks the active main question, follow-up, or re-ask.
    Concludes the interview if all questions are completed.
    """
    questions = state.get("questions", [])
    index = state.get("current_question_index", 0)
    is_followup = state.get("is_followup", False)
    is_reask = state.get("is_reask", False)
    unmatched_keywords = state.get("unmatched_keywords", [])

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
    q_id = q.question_id
    q_tid = q.topic_id

    # Locate topic name
    topic_name = "Technical Proficiency"
    for t in state.get("topics", []):
        if t.id == q_tid:
            topic_name = t.name
            break

    # Determine question or follow-up text
    if is_followup:
        followups = state.get("suggested_followups", [])
        matching_f = [f for f in followups if f.question_id == q_id]
        if matching_f:
            question_to_ask = matching_f[0].followup
        else:
            question_to_ask = q.question
    else:
        question_to_ask = q.question

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
    Consumes evaluation results.
    - If accuracy < 70% and not yet re-asked, triggers a re-ask of the same question/followup.
    - If accuracy >= 70% (or retry already used), branches into suggested follow-up or advances to next question.
    """
    index = state.get("current_question_index", 0)
    is_followup = state.get("is_followup", False)
    questions = state.get("questions", [])
    followups = state.get("suggested_followups", [])
    is_passed = state.get("is_passed", False)
    retry_count = state.get("retry_count", 0)

    if index >= len(questions):
        return {"interview_status": "completed"}

    # 1. If accuracy is not matched (< 70%), re-ask one more time
    if not is_passed and retry_count < 1:
        return {
            "retry_count": retry_count + 1,
            "is_reask": True,
        }

    # 2. If accuracy matched (>= 70%) OR re-ask retry was already used:
    if not is_followup:
        q = questions[index]
        q_id = q.question_id
        matching_f = [f for f in followups if f.question_id == q_id]
        if matching_f:
            # Transition to asking follow-up on next turn
            return {
                "retry_count": 0,
                "is_reask": False,
                "is_followup": True,
                "matched_keywords": [],
                "unmatched_keywords": [],
            }

    # If we just finished a follow-up (or no follow-up existed), move to next question
    return {
        "current_question_index": index + 1,
        "is_followup": False,
        "retry_count": 0,
        "is_reask": False,
        "matched_keywords": [],
        "unmatched_keywords": [],
    }
