from typing import List
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from interview.llm import get_llm
from interview.prompts import (
    DOCUMENT_EXTRACTION_PROMPT,
    QUESTION_GENERATION_FROM_STATE_PROMPT,
    QUESTION_GENERATION_HUMAN_PROMPT,
    INTERVIEW_QUESTION_PROMPT,
    INTERVIEW_CONCLUDE_PROMPT,
)
from interview.state import (
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

    result_dict = result.model_dump()
    result_dict["current_question_index"] = 0
    result_dict["is_followup"] = False
    result_dict["interview_status"] = "in_progress"

    first_topic_id = None
    if result_dict.get("topics"):
        t0 = result_dict["topics"][0]
        first_topic_id = t0.id if hasattr(t0, "id") else t0.get("id")
    result_dict["topic_id"] = first_topic_id
    result_dict["current_topic_id"] = first_topic_id

    return result_dict


def _ensure_text_content(msg: AIMessage) -> AIMessage:
    """Normalizes list-based multimodal content blocks into clean string text."""
    if isinstance(msg.content, list):
        text_parts = [
            p.get("text", "") if isinstance(p, dict) else str(p)
            for p in msg.content
        ]
        msg.content = "".join(text_parts).strip()
    return msg


def ask_question_node(state: InterviewState) -> dict:
    """
    Interviewer turn: Formulates and asks the active main question or follow-up question.
    Concludes the interview if all questions are completed.
    """
    questions = state.get("questions", [])
    index = state.get("current_question_index", 0)
    is_followup = state.get("is_followup", False)

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
    q_id = q.question_id if hasattr(q, "question_id") else q.get("question_id")
    q_tid = q.topic_id if hasattr(q, "topic_id") else q.get("topic_id")

    # Locate topic name
    topic_name = ""
    for t in state.get("topics", []):
        t_id = t.id if hasattr(t, "id") else t.get("id")
        if t_id == q_tid:
            topic_name = t.name if hasattr(t, "name") else t.get("name", "")
            break

    # Determine question or follow-up text
    if is_followup:
        followups = state.get("suggested_followups", [])
        matching_f = [
            f for f in followups
            if (f.question_id if hasattr(f, "question_id") else f.get("question_id")) == q_id
        ]
        if matching_f:
            f = matching_f[0]
            question_to_ask = f.followup if hasattr(f, "followup") else f.get("followup", "")
        else:
            q_text = q.question if hasattr(q, "question") else q.get("question", "")
            question_to_ask = q_text
    else:
        question_to_ask = q.question if hasattr(q, "question") else q.get("question", "")

    prompt_content = INTERVIEW_QUESTION_PROMPT.format(
        topic_name=topic_name,
        question_text=question_to_ask,
        is_followup="Yes" if is_followup else "No",
    )

    history = state.get("messages", [])[-2:] if state.get("messages") else []
    request_instruction = (
        "Please ask the candidate this follow-up question naturally."
        if is_followup
        else "Please introduce and present this interview question to the candidate."
    )

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
    Candidate response evaluation turn:
    Consumes candidate answer, decides whether to branch into a suggested follow-up
    or advance to the next main question.
    """
    index = state.get("current_question_index", 0)
    is_followup = state.get("is_followup", False)
    questions = state.get("questions", [])
    followups = state.get("suggested_followups", [])

    if index >= len(questions):
        return {"interview_status": "completed"}

    # If we just answered a main question, check if there's a suggested follow-up
    if not is_followup:
        q = questions[index]
        q_id = q.question_id if hasattr(q, "question_id") else q.get("question_id")
        matching_f = [
            f for f in followups
            if (f.question_id if hasattr(f, "question_id") else f.get("question_id")) == q_id
        ]
        if matching_f:
            # Transition to asking follow-up on next turn
            return {"is_followup": True}

    # If we just finished a follow-up (or no follow-up existed), move to next question
    return {
        "current_question_index": index + 1,
        "is_followup": False,
    }
