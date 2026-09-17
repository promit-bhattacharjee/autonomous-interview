import json
from typing import Any
from langgraph.graph import END, StateGraph
from src.agent.keyword_ledger import RelationalKeywordLedger
from src.agent.prompts.rubrics import compute_ukvi_recommendation, evaluate_response_keywords
from src.agent.state import InterviewExecutionState, TurnRecord


def evaluate_answer_node(state: InterviewExecutionState) -> dict[str, Any]:
    """Scores candidate transcript against expected keywords using deduplicated relational ledger."""
    transcript = state.get("latest_transcript", "").strip()
    total_kws = state.get("total_question_keywords") or state.get("expected_keywords", [])
    active_q_id = state.get("active_question_id") or f"q-{state.get('current_topic_index', 0)}-{state.get('current_question_index', 0)}"

    text_lower = transcript.lower()
    new_hits = [kw for kw in total_kws if kw.lower() in text_lower]

    # Relational Deduplicated Keyword Ledger:
    # When a keyword matches, it is appended to the question's ledger.
    # Duplicates are automatically eliminated (e.g. A, then B, then A results in [A, B]).
    ledger = RelationalKeywordLedger(state.get("keyword_ledger", {}))
    cumulative_hits = ledger.append_matches(active_q_id, new_hits)
    missed = ledger.get_missing(active_q_id, total_kws)
    score = ledger.calculate_score(active_q_id, total_kws)

    turn: TurnRecord = {
        "turn_type": "reask" if state.get("is_reask_active") else "question",
        "reference_id": f"turn-{len(state.get('turns', [])) + 1}",
        "spoken_prompt": state.get("current_prompt", ""),
        "candidate_transcript": transcript,
        "score": score,
        "rubric_hits": cumulative_hits,
        "missed_keywords": missed,
    }

    updated_turns = list(state.get("turns", []))
    updated_turns.append(turn)

    return {
        "latest_score": score,
        "turns": updated_turns,
        "active_question_hits": cumulative_hits,
        "total_question_keywords": total_kws,
        "active_question_id": active_q_id,
        "keyword_ledger": ledger.to_dict(),
    }


def process_answer_node(state: InterviewExecutionState) -> dict[str, Any]:
    """
    Evaluates progression conditions:
    - If score < 70% on Attempt 1 -> Re-ask targeting missed keywords.
    - On Pass (>= 70%) or Attempt 2 -> Advance to follow-up or next question/topic.
    """
    score = state.get("latest_score", 0.0)
    attempt = state.get("attempt_count", 1)
    is_reask = state.get("is_reask_active", False)

    # Trigger re-ask if score < 70% on attempt 1
    if score < 70.0 and attempt == 1 and not is_reask:
        return {
            "attempt_count": 2,
            "is_reask_active": True,
        }

    # Otherwise, advance turn sequence and reset active question ledger
    topics = state.get("topics", [])
    t_idx = state.get("current_topic_index", 0)
    q_idx = state.get("current_question_index", 0)
    f_idx = state.get("current_followup_index", 0)

    curr_topic = topics[t_idx] if t_idx < len(topics) else None
    questions = curr_topic.get("questions", []) if curr_topic else []
    curr_q = questions[q_idx] if q_idx < len(questions) else None
    followups = curr_q.get("followups", []) if curr_q else []

    # Check if there is an unasked followup
    if f_idx < len(followups):
        return {
            "current_followup_index": f_idx + 1,
            "attempt_count": 1,
            "is_reask_active": False,
            "active_question_hits": [],
            "total_question_keywords": [],
        }

    # Otherwise advance to next question in this topic
    if q_idx + 1 < len(questions):
        return {
            "current_question_index": q_idx + 1,
            "current_followup_index": 0,
            "attempt_count": 1,
            "is_reask_active": False,
            "active_question_hits": [],
            "total_question_keywords": [],
        }

    # Otherwise advance to next topic
    if t_idx + 1 < len(topics):
        return {
            "current_topic_index": t_idx + 1,
            "current_question_index": 0,
            "current_followup_index": 0,
            "attempt_count": 1,
            "is_reask_active": False,
            "active_question_hits": [],
            "total_question_keywords": [],
        }

    # All topics and questions exhausted -> Conclude interview
    return {
        "is_interview_concluded": True,
        "is_reask_active": False,
        "active_question_hits": [],
        "total_question_keywords": [],
    }


def ask_question_node(state: InterviewExecutionState) -> dict[str, Any]:
    """Prepares the spoken prompt and expected keywords for the active turn."""
    if state.get("is_interview_concluded"):
        return {
            "current_prompt": "Thank you. That concludes your UKVI credibility assessment.",
            "expected_keywords": [],
            "expected_time_to_ans": 0,
        }

    # Handle Re-ask targeting remaining uneliminated keywords
    if state.get("is_reask_active"):
        total_kws = state.get("total_question_keywords", [])
        active_q_id = state.get("active_question_id") or f"q-{state.get('current_topic_index', 0)}-{state.get('current_question_index', 0)}"
        ledger = RelationalKeywordLedger(state.get("keyword_ledger", {}))
        missing = ledger.get_missing(active_q_id, total_kws)
        missed_str = ", ".join(missing[:2]) if missing else "specific details"
        return {
            "current_prompt": f"Could you elaborate further regarding {missed_str}?",
            "expected_time_to_ans": 30,
            "expected_keywords": missing or total_kws,
        }

    topics = state.get("topics", [])
    t_idx = state.get("current_topic_index", 0)
    q_idx = state.get("current_question_index", 0)
    f_idx = state.get("current_followup_index", 0)

    curr_topic = topics[t_idx] if t_idx < len(topics) else {}
    questions = curr_topic.get("questions", [])
    curr_q = questions[q_idx] if q_idx < len(questions) else {}

    # If asking a follow-up
    if f_idx > 0:
        followups = curr_q.get("followups", [])
        active_f = followups[f_idx - 1] if f_idx - 1 < len(followups) else {}
        kws = active_f.get("expected_answer_keywords", [])
        prompt_id = f"{curr_q.get('question_id', f'q-{q_idx}')}-f{f_idx}"
        return {
            "current_prompt": active_f.get("followup_text", ""),
            "expected_time_to_ans": active_f.get("expected_time_to_ans", 30),
            "expected_keywords": kws,
            "total_question_keywords": kws,
            "active_question_hits": [],
            "active_question_id": prompt_id,
        }

    # Otherwise primary question
    kws = curr_q.get("expected_answer_keywords", [])
    prompt_id = f"{curr_q.get('question_id', f'q-{q_idx}')}-main"
    return {
        "current_prompt": curr_q.get("question_text", ""),
        "expected_time_to_ans": curr_q.get("expected_time_to_ans", 45),
        "expected_keywords": kws,
        "total_question_keywords": kws,
        "active_question_hits": [],
        "active_question_id": prompt_id,
    }


def generate_final_evaluation_node(state: InterviewExecutionState) -> dict[str, Any]:
    """Synthesizes overall scorecard and UKVI genuine student recommendation."""
    turns = state.get("turns", [])
    if not turns:
        return {
            "overall_score": 0.0,
            "ukvi_recommendation": "Inconclusive",
            "final_report_json": json.dumps({"summary": "No turns recorded."}),
        }

    scores = [t.get("score", 0.0) for t in turns]
    overall = round(sum(scores) / len(scores), 1)
    rec = compute_ukvi_recommendation(overall)

    report = {
        "candidate_user_id": state.get("user_id"),
        "bank_id": state.get("bank_id"),
        "difficulty": state.get("difficulty"),
        "total_turns": len(turns),
        "overall_score": overall,
        "recommendation": rec,
        "turn_breakdown": turns,
    }

    return {
        "overall_score": overall,
        "ukvi_recommendation": rec,
        "final_report_json": json.dumps(report),
    }


def should_continue_interview(state: InterviewExecutionState) -> str:
    """Routing condition after process_answer."""
    if state.get("is_interview_concluded"):
        return "generate_final_evaluation"
    return "ask_question"


def build_interview_execution_graph():
    """Builds and compiles the decoupled interview_execution_graph."""
    builder = StateGraph(InterviewExecutionState)

    builder.add_node("ask_question", ask_question_node)
    builder.add_node("evaluate_answer", evaluate_answer_node)
    builder.add_node("process_answer", process_answer_node)
    builder.add_node("generate_final_evaluation", generate_final_evaluation_node)

    builder.set_entry_point("ask_question")
    builder.add_edge("ask_question", "evaluate_answer")
    builder.add_edge("evaluate_answer", "process_answer")

    builder.add_conditional_edges(
        "process_answer",
        should_continue_interview,
        {
            "ask_question": "ask_question",
            "generate_final_evaluation": "generate_final_evaluation",
        },
    )
    builder.add_edge("generate_final_evaluation", END)

    return builder.compile()
