import sys
import uuid
from langchain_core.messages import HumanMessage

# Ensure Windows terminal outputs UTF-8 cleanly
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import os
from pathlib import Path
from interview.graph import interview_graph
from interview.session_builder import (
    build_initial_interview_payload,
    load_question_file,
    load_student_profile,
)


def main():
    print("=" * 65)
    print("   AI UK CREDIBILITY & ACADEMIC INTERVIEWER -- TERMINAL RUNNER   ")
    print("=" * 65)

    base_dir = Path(__file__).resolve().parent
    question_path = base_dir / "data" / "questions" / "uk_credibility_questions.txt"
    student_path = base_dir / "data" / "students" / "sample_student.json"

    print(f"\n[1] Ingesting Admin Question File: {question_path.name}")
    question_content = load_question_file(str(question_path))

    print(f"[2] Ingesting Student Profile Data: {student_path.name}")
    student_data = load_student_profile(str(student_path))
    print(f"    - Student: {student_data.get('full_name')} (Target: {student_data.get('target_university')})")

    # Merge student profile + question file into initial payload
    interview_payload = build_initial_interview_payload(
        student_data=student_data,
        question_content=question_content,
        difficulty="Medium",
    )

    session_id = f"uk-interview-{uuid.uuid4().hex[:8]}"
    config = {"configurable": {"thread_id": session_id}}

    print("\n[+] Initializing interview and generating customized question rubric...")
    print(f"[+] Session Thread ID: {session_id}")

    # Turn 1: Process document, generate question rubric, formulate and ask Question 1
    state = interview_graph.invoke(interview_payload, config=config)

    topics_count = len(state.get("topics", []))
    questions_count = len(state.get("questions", []))
    followups_count = len(state.get("suggested_followups", []))
    print(f"\n[SUCCESS] Interview Plan Generated: {topics_count} Topics | {questions_count} Questions | {followups_count} Follow-ups\n")

    # Display the first interviewer question
    messages = state.get("messages", [])
    if messages:
        print("-" * 65)
        print(f"\n🎙️  [Interviewer]:\n{messages[-1].content}\n")
        print("-" * 65)

    # Turn-by-Turn Interactive Conversation Loop
    while state.get("interview_status") != "completed":
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

        print("\n[+] Interviewer is processing your response...")

        # Resume graph on the same thread with the candidate's answer
        state = interview_graph.invoke(
            {"messages": [HumanMessage(content=candidate_answer)]},
            config=config,
        )

        evals = state.get("evaluations", [])
        latest_eval = evals[-1] if evals else None
        is_reask = bool(latest_eval.attempt_number == 1 and not latest_eval.is_passed) if latest_eval else False
        if latest_eval is not None:
            status_label = "PASSED (>= 70%)" if latest_eval.is_passed else "BELOW THRESHOLD (< 70%)"
            action_label = "-> Re-asking question one more time..." if is_reask else "-> Proceeding to next question..."
            print(f"\n📊 [Accuracy Check]: {latest_eval.accuracy_score:.1f}% (Attempt {latest_eval.attempt_number}) | {status_label} {action_label}")
            print(f"   [Relational IDs]: Topic ID: {latest_eval.topic_id} | Question ID: {latest_eval.question_id}")
            if latest_eval.matched_keywords:
                print(f"   ✅ Matched: {', '.join(latest_eval.matched_keywords)}")
            if latest_eval.unmatched_keywords:
                print(f"   ❌ Unmatched: {', '.join(latest_eval.unmatched_keywords)}")

        messages = state.get("messages", [])
        if messages:
            print("-" * 65)
            print(f"\n🎙️  [Interviewer]:\n{messages[-1].content}\n")
            print("-" * 65)

    if state.get("interview_status") == "completed":
        print("\n" + "=" * 65)
        print("🎉 INTERVIEW CONCLUDED SUCCESSFULLY!")
        print(f"Total conversation turns: {len(state.get('messages', []))}")
        print("=" * 65)


if __name__ == "__main__":
    main()
