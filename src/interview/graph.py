from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from interview.nodes import (
    ask_question_node,
    evaluate_answer_node,
    generate_final_evaluation_node,
    generate_questions_node,
    process_answer_node,
)
from interview.state import InterviewState


def route_start(state: InterviewState) -> str:
    """
    Routes the initial turn entry:
    - If interview is already completed and needs final evaluation synthesis: generate_final_evaluation
    - If interview is completed and already evaluated: END
    - If interview is in progress: evaluate_answer
    - If questions already exist: ask_question
    - Otherwise: generate_questions
    """
    if state.get("interview_status") == "completed" and not state.get("final_evaluation"):
        return "generate_final_evaluation"
    if state.get("interview_status") == "completed":
        return END
    if state.get("interview_status") == "in_progress":
        return "evaluate_answer"
    if state.get("topics") or state.get("questions"):
        return "ask_question"
    return "generate_questions"


# Backward compatibility alias
route_after_init = route_start


def route_after_ask(state: InterviewState) -> str:
    """
    If the interview was concluded in ask_question_node, route to generate_final_evaluation.
    Otherwise pause turn execution by routing to END.
    """
    if state.get("interview_status") == "completed":
        return "generate_final_evaluation"
    return END


def create_interview_graph():
    """
    Builds and compiles the turn-by-turn LangGraph interview workflow:
    - Initial Question Generation: START -> generate_questions -> ask_question -> END
    - Active Response Turns: START -> evaluate_answer -> process_answer -> ask_question -> [END or generate_final_evaluation]
    - Interview Concluded: ask_question -> generate_final_evaluation -> END
    """
    workflow = StateGraph(InterviewState)

    # Register Nodes
    workflow.add_node("generate_questions", generate_questions_node)
    workflow.add_node("evaluate_answer", evaluate_answer_node)
    workflow.add_node("process_answer", process_answer_node)
    workflow.add_node("ask_question", ask_question_node)
    workflow.add_node("generate_final_evaluation", generate_final_evaluation_node)

    # Primary entry point conditional routing
    workflow.add_conditional_edges(
        START,
        route_start,
        {
            "generate_questions": "generate_questions",
            "evaluate_answer": "evaluate_answer",
            "ask_question": "ask_question",
            "generate_final_evaluation": "generate_final_evaluation",
            END: END,
        },
    )

    # Question generation flows directly to asking the first question
    workflow.add_edge("generate_questions", "ask_question")

    # Turn cycle
    workflow.add_edge("evaluate_answer", "process_answer")
    workflow.add_edge("process_answer", "ask_question")

    # Conclude or pause turn
    workflow.add_conditional_edges(
        "ask_question",
        route_after_ask,
        {
            "generate_final_evaluation": "generate_final_evaluation",
            END: END,
        },
    )

    # Final evaluation concludes the workflow
    workflow.add_edge("generate_final_evaluation", END)

    # Compile with checkpointer for multi-turn thread persistence
    checkpointer = MemorySaver()
    app = workflow.compile(checkpointer=checkpointer)
    return app


# Compiled graph instance
interview_graph = create_interview_graph()

