import sys
import uuid
from langchain_core.messages import HumanMessage

# Ensure Windows terminal outputs UTF-8 cleanly
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from interview.graph import interview_graph


def main():
    print("=" * 65)
    print("      AI TECHNICAL INTERVIEWER -- LIVE TURN-BY-TURN RUNNER      ")
    print("=" * 65)

    # 1. Candidate Profile / Material
    sample_candidate_data = {
        "extraced_text": (
            "Candidate applying for Master's in Computer Science at University of Southern California (USC), USA. "
            "Background: BSc in Software Engineering with 3.7 GPA, IELTS 7.5. "
            "Sponsor: Self and parents with savings of $70,000. "
            "Career Goal: Return to home country as an AI/ML Engineer."
        ),
        "difficulty": "Medium",
        "expected_time_to_ans": 30,
        "expected_words_to_ans": 1000,
        "iterations": 1,
        "conofidance": 1.0,
        "expected_answer_keywords": ["Machine Learning", "Software Architecture", "USC", "Goals"],
    }

    session_id = f"interview-{uuid.uuid4().hex[:8]}"
    config = {"configurable": {"thread_id": session_id}}

    print("\n[+] Initializing interview and generating customized question plan...")
    print(f"[+] Session Thread ID: {session_id}")

    # Turn 1: Process document, generate question rubric, formulate and ask Question 1
    state = interview_graph.invoke(sample_candidate_data, config=config)

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

        acc = state.get("last_accuracy")
        passed = state.get("is_passed")
        is_reask = state.get("is_reask")
        if acc is not None:
            status_label = "PASSED (>= 70%)" if passed else "BELOW THRESHOLD (< 70%)"
            action_label = "-> Re-asking question one more time..." if is_reask else "-> Proceeding..."
            print(f"\n📊 [Accuracy Check]: {acc:.1f}% | {status_label} {action_label}")

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
