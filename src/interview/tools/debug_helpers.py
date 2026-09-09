from typing import List
from interview.state import InterviewState, TopicItem


def print_interview_state_debug(state: InterviewState) -> None:
    """
    Renders a comprehensive, structured debug inspection of the LangGraph
    interview state in the terminal for the Nested Tree Architecture (Pattern A).
    """
    topics: List[TopicItem] = state.get("topics", [])
    difficulty = state.get("difficulty", "Medium")
    time_limit = state.get("expected_total_time_to_ans", 45)
    current_t_idx = state.get("current_topic_idx", 0)
    current_q_idx = state.get("current_question_idx", 0)
    current_f_idx = state.get("current_followup_idx", -1)
    interview_status = state.get("interview_status", "in_progress")
    messages = state.get("messages", [])
    first_question_text = messages[-1].content if messages else "No question formulated."

    total_questions = sum(len(t.questions) for t in topics)
    total_followups = sum(sum(len(q.followups) for q in t.questions) for t in topics)

    print("\n" + "=" * 80)
    print(" 🧠 LANGGRAPH BRAIN: QUESTION GENERATION & STATE INSPECTION REPORT")
    print("    (Pattern A: Nested Tree Architecture -- Topic -> Question -> Follow-ups)")
    print("=" * 80)

    # 1. State Metadata & Extraction Summary
    print("\n[STAGE 1: SESSION METADATA & CONFIG]")
    print(f" • Interview Status        : {interview_status.upper()}")
    print(f" • Configured Difficulty   : {difficulty}")
    print(f" • Expected Response Time  : {time_limit} seconds total")
    print(f" • Active Cursor Position  : Topic [{current_t_idx}], Question [{current_q_idx}], Followup [{current_f_idx}]")
    print(f" • Curriculum Breakdown    : {len(topics)} Topics | {total_questions} Questions | {total_followups} Follow-ups")

    # 2. Nested Tree Overview
    print("\n[STAGE 2: GENERATED INTERVIEW TREE HIERARCHY]")
    for t_idx, t in enumerate(topics):
        t_id = t.id
        t_name = t.name
        is_active_topic = " 📍 [ACTIVE TOPIC]" if t_idx == current_t_idx else ""
        print(f"\n 📂 Topic #{t_id}: {t_name}{is_active_topic}")

        for q_idx, q in enumerate(t.questions):
            q_text = q.question
            q_diff = q.difficulty
            q_kw = q.expected_answer_keywords
            is_active_q = " 📍 [ACTIVE QUESTION]" if (t_idx == current_t_idx and q_idx == current_q_idx and current_f_idx == -1) else ""
            print(f"   └── ❓ Primary Question ({q_diff}): \"{q_text}\"{is_active_q}")
            if q_kw:
                print(f"       ├── Target Rubric Keywords: {', '.join(q_kw)}")

            for f_idx, f in enumerate(q.followups):
                f_text = f.followup
                f_kw = f.expected_answer_keywords
                is_active_f = " 📍 [ACTIVE FOLLOW-UP]" if (t_idx == current_t_idx and q_idx == current_q_idx and f_idx == current_f_idx) else ""
                print(f"       └── 🔎 Follow-up #{f_idx + 1}: \"{f_text}\"{is_active_f}")
                if f_kw:
                    print(f"           └── Target Keywords: {', '.join(f_kw)}")

    # 3. Formulated Question 1 (Speech Output)
    print("\n" + "-" * 80)
    print("🎙️ [STAGE 3: FINAL INTERVIEWER CONVERSATIONAL SPEECH (TURN 1)]")
    print("-" * 80)
    print(f"{first_question_text.strip()}\n")
    print("-" * 80)
