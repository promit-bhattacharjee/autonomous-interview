import sys
import json

# Ensure Windows terminal outputs UTF-8 cleanly
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from interview.graph import interview_graph


def main():
    print("=" * 60)
    print("AI INTERVIEW QUESTION GENERATOR -- LIVE RUNNER")
    print("=" * 60)

    # 1. Provide your candidate profile, resume, or interview notes
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
    }

    print("\n[+] Invoking LangGraph workflow with Gemini...")
    result = interview_graph.invoke(sample_candidate_data)

    print("\n[SUCCESS] Generated Interview Plan!\n")
    print(f"Summary: {len(result.get('topics', []))} Topics | {len(result.get('questions', []))} Questions | {len(result.get('suggested_followups', []))} Follow-ups")
    print(f"Total Estimated Time: {result.get('expected_total_time_to_ans', 0)} seconds")
    print(f"Total Word Target: {result.get('expected_total_words_to_ans', 0)} words\n")

    # 2. Display Topics
    print("-" * 60)
    print("TOPICS:")
    for topic in result.get("topics", []):
        t_name = topic.name if hasattr(topic, "name") else topic.get("name")
        t_id = topic.id if hasattr(topic, "id") else topic.get("id")
        print(f"  * Topic {t_id}: {t_name}")

    # 3. Display Questions & Follow-ups
    print("\n" + "-" * 60)
    print("QUESTIONS & PROBING FOLLOW-UPS:")
    questions = result.get("questions", [])
    followups = result.get("suggested_followups", [])

    for i, q in enumerate(questions, 1):
        q_text = q.question if hasattr(q, "question") else q.get("question")
        q_ans = q.expected_answer if hasattr(q, "expected_answer") else q.get("expected_answer")
        q_diff = q.difficulty if hasattr(q, "difficulty") else q.get("difficulty")
        q_id = q.question_id if hasattr(q, "question_id") else q.get("question_id")

        print(f"\n[Question {i}] (Difficulty: {q_diff})")
        print(f"  Q: {q_text}")
        print(f"  Expected Answer: {q_ans}")

        # Find matching follow-ups for this question
        matching_f = [
            f for f in followups 
            if (f.question_id if hasattr(f, "question_id") else f.get("question_id")) == q_id
        ]
        for f in matching_f:
            f_text = f.followup if hasattr(f, "followup") else f.get("followup")
            print(f"  -> Suggested Follow-up: {f_text}")

    print("\n" + "=" * 60)
    print("Run completed successfully!")
    print("=" * 60)


if __name__ == "__main__":
    main()
