"""
End-to-end integration test for the full interview lifecycle:
1. Dynamic question generation from mock API JSON (OpenRouter DeepSeek V3)
2. Interactive turn evaluation (OpenRouter DeepSeek V3)
3. Conversational interviewer speech phrasing (Google Gemini)
4. Comprehensive post-interview final evaluation synthesis (OpenRouter DeepSeek V3)
"""
import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from pathlib import Path
src_path = str(Path(__file__).resolve().parent.parent / "src")
if src_path not in sys.path:
    sys.path.insert(0, src_path)

import os
import unittest
from interview.service import InterviewSession
from interview.state import QuestionState, TopicState


@unittest.skipUnless(
    bool(os.getenv("GOOGLE_API_KEY")),
    "Requires live GOOGLE_API_KEY in environment (.env is sanitized per zero-key policy)",
)
class TestFullInterviewAndFinalEvaluation(unittest.TestCase):
    def test_e2e_interview_with_mock_flow(self):
        """
        Runs a focused 2-question interview simulation to thoroughly test:
        - Per-turn answer accuracy evaluation
        - Relational sequencing
        - Concluding remarks
        - Automated Final Evaluation synthesis
        """
        print("\n" + "=" * 75)
        print("Running End-to-End Interview & Final Evaluation Pipeline Test")
        print("=" * 75)

        # 1. Setup compact 2-question nested tree plan (Pattern A)
        topics = [
            TopicState(
                id=1,
                name="Academic Fit & Course Selection",
                expected_time_to_ans=45,
                questions=[
                    QuestionState(
                        question="Why did you choose the MSc in AI at Hertfordshire, and how do the core modules link to your background?",
                        difficulty="Medium",
                        expected_time_to_ans=45,
                        expected_answer_keywords=["Machine Learning", "7COM1076", "Robotics", "PyTorch"],
                        followups=[],
                    )
                ],
            ),
            TopicState(
                id=2,
                name="Financial Capability & UKVI Compliance",
                expected_time_to_ans=45,
                questions=[
                    QuestionState(
                        question="Can you detail your tuition fees, living costs, and how your funds comply with the UKVI 28-day rule?",
                        difficulty="Medium",
                        expected_time_to_ans=45,
                        expected_answer_keywords=["16500", "12500", "28-day rule", "35000", "Father"],
                        followups=[],
                    )
                ],
            ),
        ]

        session = InterviewSession(
            topics=topics,
            student_id="UK-CAS-2026-9041",
            university_id="UK-HERTS-01",
        )

        # 2. Start session -> Turn 1 question formulated
        first_q = session.start()
        self.assertTrue(len(first_q) > 0)
        print(f"\n[Turn 1 Asked]: {first_q[:120]}...")

        # 3. Candidate answers Turn 1
        answer_1 = (
            "I chose Hertfordshire because of its strong AI curriculum, specifically module 7COM1076 "
            "Machine Learning and Neural Networks using PyTorch, and Robotics systems. My BSc in Software "
            "Engineering included machine learning projects that directly prepare me for this degree."
        )
        print(f"\n[Candidate Response 1]: {answer_1}")
        next_q, is_done_1, eval_1 = session.submit_candidate_answer(answer_1)

        self.assertFalse(is_done_1)
        self.assertIn("accuracy_score", eval_1)
        print(f"  -> Accuracy Score: {eval_1.get('accuracy_score')}%, Passed: {eval_1.get('is_passed')}")
        print(f"  -> Matched Keywords: {eval_1.get('matched_keywords')}")

        # 4. Candidate answers Turn 2 (Final Question)
        print(f"\n[Turn 2 Asked]: {next_q[:120]}...")
        answer_2 = (
            "My annual tuition fee is 16500 pounds and living costs are 12500 pounds as per UKVI outside London requirements. "
            "My father is sponsoring me with personal savings of 35000 pounds which has been maintained in Standard Chartered "
            "for over 35 consecutive days, well satisfying the UKVI 28-day rule."
        )
        print(f"\n[Candidate Response 2]: {answer_2}")
        conclusion, is_done_2, eval_2 = session.submit_candidate_answer(answer_2)

        self.assertTrue(is_done_2)
        print(f"\n[Interviewer Concluding Utterance]: {conclusion}")

        # 5. Verify Final Evaluation Report
        final_eval = session.get_final_evaluation()
        self.assertIsNotNone(final_eval)
        print("\n" + "=" * 75)
        print("🎉 FINAL EVALUATION REPORT GENERATED:")
        print(f" • Overall Score   : {final_eval.get('overall_score')}%")
        print(f" • Overall Status  : {final_eval.get('overall_status')}")
        print(f" • Topic Breakdown : {len(final_eval.get('topic_breakdown', []))} topics evaluated")
        print(f" • Strengths       : {final_eval.get('strengths')}")
        print(f" • Improvement     : {final_eval.get('areas_for_improvement')}")
        print(f" • Recommendation  : {final_eval.get('recommendation')}")
        print("=" * 75)

        self.assertIn("overall_score", final_eval)
        self.assertIn("overall_status", final_eval)
        self.assertIn("recommendation", final_eval)


if __name__ == "__main__":
    unittest.main()
