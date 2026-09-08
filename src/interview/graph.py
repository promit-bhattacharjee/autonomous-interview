from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from interview.nodes import (
    ask_question_node,
    evaluate_answer_node,
    extract_initial_text,
    generate_questions_node,
    process_answer_node,
)
from interview.state import InterviewState


def route_start(state: InterviewState) -> str:
    """
    Routes execution based on whether this is an ongoing interview
    session, a direct-question interview, or initial candidate document extraction.
    """
    if state.get("interview_status") == "in_progress":
        return "evaluate_answer"
    if state.get("questions"):
        return "ask_question"
    return "extract_initial_text"


def create_interview_graph():
    """
    Builds and compiles the turn-by-turn LangGraph interview workflow:
    - Direct Question Turn 1: START -> ask_question -> END
    - Document Initial Turn: START -> extract_initial_text -> generate_questions -> ask_question -> END
    - Response Turns: START -> evaluate_answer -> process_answer -> ask_question -> END
    """
    workflow = StateGraph(InterviewState)

    # Register Nodes
    workflow.add_node("extract_initial_text", extract_initial_text)
    workflow.add_node("generate_questions", generate_questions_node)
    workflow.add_node("evaluate_answer", evaluate_answer_node)
    workflow.add_node("process_answer", process_answer_node)
    workflow.add_node("ask_question", ask_question_node)

    # Conditional entry point from START
    workflow.add_conditional_edges(
        START,
        route_start,
        {
            "extract_initial_text": "extract_initial_text",
            "evaluate_answer": "evaluate_answer",
            "ask_question": "ask_question",
        },
    )

    # Initial flow
    workflow.add_edge("extract_initial_text", "generate_questions")
    workflow.add_edge("generate_questions", "ask_question")

    # Turn cycle:
    # 1. Candidate response enters evaluate_answer -> process_answer -> ask_question -> END
    workflow.add_edge("evaluate_answer", "process_answer")
    workflow.add_edge("process_answer", "ask_question")
    workflow.add_edge("ask_question", END)

    # Compile with in-memory checkpointer for multi-turn session persistence
    checkpointer = MemorySaver()
    app = workflow.compile(checkpointer=checkpointer)
    return app


# Compiled graph instance ready for multi-turn execution
interview_graph = create_interview_graph()
