import sys
from pathlib import Path

# Ensure Windows terminal outputs UTF-8 cleanly
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

src_path = str(Path(__file__).resolve().parent / "src")
if src_path not in sys.path:
    sys.path.insert(0, src_path)

from interview.service import InterviewSession


def print_final_evaluation_report(final_eval: dict):
    if not final_eval:
        return

    score = final_eval.get("overall_score", 0.0)
    status = final_eval.get("overall_status", "UNKNOWN")
    topics = final_eval.get("topic_breakdown", [])
    strengths = final_eval.get("strengths", [])
    improvements = final_eval.get("areas_for_improvement", [])
    recommendation = final_eval.get("recommendation", "")

    status_badge = f"[{status}]"
    if status == "PASSED":
        status_badge = f"✅ {status_badge}"
    elif status == "CONDITIONAL_PASS":
        status_badge = f"⚠️ {status_badge}"
    else:
        status_badge = f"❌ {status_badge}"

    print("\n" + "=" * 75)
    print("      🎓 OFFICIAL UKVI CREDIBILITY & ADMISSIONS FINAL EVALUATION REPORT      ")
    print("=" * 75)
    print(f"\n • OVERALL COMPOSITE SCORE : {score:.1f}%")
    print(f" • ADMISSIONS & VISA STATUS: {status_badge}")

    if topics:
        print("\n" + "-" * 75)
        print(" 📋 TOPIC-BY-TOPIC BREAKDOWN:")
        print("-" * 75)
        for t in topics:
            t_name = t.get("topic_name", "Topic")
            t_score = t.get("average_score", 0.0)
            t_pass = "PASSED" if t.get("is_passed") else "FAILED"
            t_feedback = t.get("summary_feedback", "")
            print(f" • {t_name:<35} | Score: {t_score:5.1f}% | {t_pass}")
            if t_feedback:
                print(f"   Assessment: {t_feedback}")

    if strengths:
        print("\n" + "-" * 75)
        print(" 🌟 CANDIDATE KEY STRENGTHS:")
        print("-" * 75)
        for s in strengths:
            print(f"  + {s}")

    if improvements:
        print("\n" + "-" * 75)
        print(" ⚠️  AREAS FOR IMPROVEMENT / NOTED GAPS:")
        print("-" * 75)
        for imp in improvements:
            print(f"  - {imp}")

    if recommendation:
        print("\n" + "-" * 75)
        print(" 📝 OFFICIAL RECOMMENDATION & VISA SPONSORSHIP JUSTIFICATION:")
        print("-" * 75)
        print(f"{recommendation.strip()}\n")

    print("=" * 75 + "\n")


def main():
    print("=" * 75)
    print("   AI UK CREDIBILITY & ACADEMIC INTERVIEWER -- TERMINAL RUNNER   ")
    print("   (Powered by OpenRouter DeepSeek V4 Flash 0731 Brain & Gemini Voice Interface)   ")
    print("=" * 75)

    print("\n[+] Initializing InterviewSession...")
    print("[+] Loading student & university data from standardized mock API JSON...")
    print("[+] Executing OpenRouter DeepSeek V4 Flash 0731 for dynamic question & rubric generation...")

    session = InterviewSession(student_id="UK-CAS-2026-9041", university_id="UK-HERTS-01")
    first_question = session.start()

    state = session.latest_state
    if state.get("interview_status") == "completed":
        print("\n" + "=" * 75)
        print("🛑 SESSION TERMINATED:")
        print(f"{first_question}")
        print("=" * 75 + "\n")
        return

    topics = state.get("topics", [])
    topics_count = len(topics)
    questions_count = sum(len(t.questions) for t in topics)
    followups_count = sum(sum(len(q.followups) for q in t.questions) for t in topics)
    print(f"\n[SUCCESS] Interview Plan Generated: {topics_count} Topics | {questions_count} Questions | {followups_count} Follow-ups\n")

    if first_question:
        print("-" * 75)
        print(f"\n🎙️  [Interviewer]:\n{first_question}\n")
        print("-" * 75)

    eval_data = {}

    # Turn-by-Turn Interactive Conversation Loop
    while session.latest_state.get("interview_status") != "completed":
        try:
            candidate_answer = input("\n👤 [Candidate] (type your answer, or 'quit' to exit):\n> ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n\n[-] Interview terminated by candidate.")
            break

        if not candidate_answer:
            continue

        if candidate_answer.lower() in ("quit", "exit"):
            print("\n[-] Exiting interview session.")
            break

        print("\n[+] OpenRouter DeepSeek V4 Flash 0731 evaluating your response...")

        next_text, is_completed, eval_data = session.submit_candidate_answer(candidate_answer)

        if eval_data:
            is_reask = eval_data.get("is_reask", False)
            status_label = "PASSED (>= 70%)" if eval_data.get("is_passed") else "BELOW THRESHOLD (< 70%)"
            action_label = "-> Re-asking question one more time..." if is_reask else "-> Proceeding to next turn..."
            print(f"\n📊 [Turn Evaluation]: {eval_data.get('accuracy_score', 0):.1f}% (Attempt {eval_data.get('attempt_number', 1)}) | {status_label} {action_label}")
            print(f"   Topic ID: {eval_data.get('active_topic_id')} | Question ID: {eval_data.get('active_question_id')}")
            if eval_data.get("matched_keywords"):
                print(f"   ✅ Matched: {', '.join(eval_data.get('matched_keywords'))}")
            if eval_data.get("unmatched_keywords"):
                print(f"   ❌ Unmatched: {', '.join(eval_data.get('unmatched_keywords'))}")
            if eval_data.get("feedback"):
                print(f"   💡 Feedback: {eval_data.get('feedback')}")

        if next_text:
            print("-" * 75)
            print(f"\n🎙️  [Interviewer]:\n{next_text}\n")
            print("-" * 75)

        # If completed, check for final evaluation report
        if is_completed:
            final_eval = eval_data.get("final_evaluation") or session.get_final_evaluation()
            print_final_evaluation_report(final_eval)
            break

    if session.latest_state.get("interview_status") == "completed" and not eval_data.get("final_evaluation"):
        final_eval = session.get_final_evaluation()
        if final_eval:
            print_final_evaluation_report(final_eval)


if __name__ == "__main__":
    main()
