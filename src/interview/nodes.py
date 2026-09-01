from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from interview.llm import get_llm
from interview.prompts import (
    DOCUMENT_EXTRACTION_PROMPT,
    QUESTION_GENERATION_FROM_STATE_PROMPT,
    QUESTION_GENERATION_HUMAN_PROMPT,
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
        HumanMessage(content=f"Document / Material to analyze:\n{raw_material}")
    ]

    llm = get_llm(model_name="gemini-3.6-flash", model_provider="google_genai")
    structured_llm = llm.with_structured_output(InitialExtracedTextOutputState)
    result: InitialExtracedTextOutputState = structured_llm.invoke(messages)

    return result.model_dump()


def generate_questions_node(state: InitialExtracedTextState) -> InterviewState:
    """
    Consumes the extracted text, difficulty, and duration requirements from InitialExtracedTextState,
    formats the prompt via QUESTION_GENERATION_HUMAN_PROMPT, generates the structured interview plan,
    and transitions into the clean InterviewState.
    """
    human_content = QUESTION_GENERATION_HUMAN_PROMPT.format(
        extraced_text=state.get("extraced_text", ""),
        difficulty=state.get("difficulty", "Medium"),
        expected_time_to_ans=state.get("expected_time_to_ans", 30),
        expected_words_to_ans=state.get("expected_words_to_ans", 1500),
    )

    messages = [
        SystemMessage(content=QUESTION_GENERATION_FROM_STATE_PROMPT),
        HumanMessage(content=human_content),
    ]

    llm = get_llm(model_name="gemini-3.6-flash", model_provider="google_genai")
    structured_llm = llm.with_structured_output(QuestionListModelState)
    result: QuestionListModelState = structured_llm.invoke(messages)

    # Clean transition into InterviewState
    return result.model_dump()



