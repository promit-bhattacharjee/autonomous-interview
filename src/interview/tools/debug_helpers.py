from typing import Any, Dict, List


def print_interview_state_debug(state: Dict[str, Any]) -> None:
    """
    Renders a comprehensive, structured debug inspection of the LangGraph
    interview state in the terminal. Shows how LLM extracted context,
    generated topics, formed questions, expected keywords, and formulated Turn 1.
    """
    topics: List[Any] = state.get("topics", [])
    questions: List[Any] = state.get("questions", [])
    followups: List[Any] = state.get("suggested_followups", [])
    difficulty = state.get("difficulty", "Medium")
    time_limit = state.get("expected_total_time_to_ans", 45)
    active_topic_id = state.get("active_topic_id")
    active_question_id = state.get("active_question_id")
    interview_status = state.get("interview_status", "in_progress")
    messages = state.get("messages", [])
    first_question_text = messages[-1].content if messages else "No question formulated."

    print("\n" + "=" * 80)
    print(" 🧠 LANGGRAPH BRAIN: QUESTION GENERATION & STATE INSPECTION REPORT")
    print("=" * 80)

    # 1. State Metadata & Extraction Summary
    print("\n[STAGE 1: DOCUMENT EXTRACTION & SESSION CONFIG]")
    print(f" • Interview Status        : {interview_status.upper()}")
    print(f" • Configured Difficulty   : {difficulty}")
    print(f" • Expected Response Time  : {time_limit} seconds per question")
    print(f" • Active Topic Pointer    : Topic ID {active_topic_id}")
    print(f" • Active Question Pointer : Question ID {active_question_id}")
    print(f" • Extracted Raw Length    : {len(state.get('extraced_text', ''))} characters")

    # 2. Generated Topics
    print(f"\n[STAGE 2: GENERATED TOPICS ({len(topics)} Total)]")
    for t in topics:
        t_id = getattr(t, "id", None)
        t_name = getattr(t, "name", "Unnamed Topic")
        t_order = getattr(t, "topic_order", 0)
        t_time = getattr(t, "expected_time_to_ans", 45)
        t_kw = getattr(t, "expected_answer_keywords", [])
        active_marker = "  📍 [ACTIVE]" if t_id == active_topic_id else ""
        print(f"\n  ┌─ Topic #{t_id} (Order {t_order}): {t_name}{active_marker}")
        print(f"  │  Target Time: {t_time}s")
        print(f"  └─ Core Topic Keywords: {', '.join(t_kw) if t_kw else 'None'}")

    # 3. Generated Questions
    print(f"\n[STAGE 3: GENERATED QUESTIONS & RUBRICS ({len(questions)} Total)]")
    for q in questions:
        q_id = getattr(q, "question_id", None)
        q_top = getattr(q, "topic_id", None)
        q_text = getattr(q, "question", "")
        q_diff = getattr(q, "difficulty", "Medium")
        q_time = getattr(q, "expected_time_to_ans", 45)
        q_kw = getattr(q, "expected_answer_keywords", [])
        active_marker = "  📍 [ACTIVE QUESTION 1]" if q_id == active_question_id else ""
        print(f"\n  ┌─ Question ID #{q_id} [Mapped to Topic #{q_top}] ({q_diff}){active_marker}")
        print(f"  │  Raw Rubric Question : \"{q_text}\"")
        print(f"  │  Expected Answer Time : {q_time}s")
        print(f"  └─ Expected Keywords (>=70% threshold):")
        for kw in q_kw:
            print(f"      • {kw}")

    # 4. Suggested Follow-ups
    if followups:
        print(f"\n[STAGE 4: SUGGESTED FOLLOW-UP PROBES ({len(followups)} Total)]")
        for f in followups:
            f_qid = getattr(f, "question_id", None)
            f_order = getattr(f, "followup_order", 1)
            f_text = getattr(f, "followup", "")
            f_kw = getattr(f, "expected_answer_keywords", [])
            print(f"\n  ┌─ Follow-up #{f_order} for Question #{f_qid}")
            print(f"  │  Probe Question : \"{f_text}\"")
            print(f"  └─ Probe Keywords : {', '.join(f_kw) if f_kw else 'None'}")

    # 5. Formulated Question 1 (Speech Output)
    print("\n" + "-" * 80)
    print("🎙️ [STAGE 5: FINAL INTERVIEWER CONVERSATIONAL SPEECH (TURN 1)]")
    print("-" * 80)
    print(f"{first_question_text.strip()}\n")
    print("-" * 80)
