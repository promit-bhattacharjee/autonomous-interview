from langgraph.graph import END, START, StateGraph
from interview.nodes import extract_initial_text, generate_questions_node
from interview.state import InitialExtracedTextState, InterviewState


def create_interview_graph():
    """
    Builds and compiles the LangGraph interview workflow:
    START -> extract_initial_text -> generate_questions -> END
    """
    workflow = StateGraph(InterviewState, input_schema=InitialExtracedTextState)

    # Add Nodes
    workflow.add_node("extract_initial_text", extract_initial_text)
    workflow.add_node("generate_questions", generate_questions_node)

    # Add Edges
    workflow.add_edge(START, "extract_initial_text")
    workflow.add_edge("extract_initial_text", "generate_questions")
    workflow.add_edge("generate_questions", END)

    # Compile Graph
    app = workflow.compile()
    return app


# Compiled graph instance ready to invoke or stream
interview_graph = create_interview_graph()
