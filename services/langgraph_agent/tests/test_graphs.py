import pytest
from src.agent.graphs.interview_exec import build_interview_execution_graph
from src.agent.graphs.question_gen import build_question_generation_graph
from src.agent.prompts.rubrics import compute_ukvi_recommendation, evaluate_response_keywords
from src.agent.state import InterviewExecutionState, QuestionGenerationState


class TestRubricScoring:
    def test_keyword_evaluation_perfect(self):
        transcript = "I chose this curriculum because of the excellent faculty and high ranking."
        expected = ["curriculum", "ranking", "faculty"]
        score, hits, missed = evaluate_response_keywords(transcript, expected)
        assert score == 100.0
        assert len(hits) == 3
        assert len(missed) == 0

    def test_keyword_evaluation_partial(self):
        transcript = "I really like the university ranking."
        expected = ["curriculum", "ranking", "faculty"]
        score, hits, missed = evaluate_response_keywords(transcript, expected)
        assert score == 33.3
        assert "ranking" in hits
        assert "curriculum" in missed

    def test_ukvi_recommendations(self):
        assert compute_ukvi_recommendation(85.0) == "Genuine"
        assert compute_ukvi_recommendation(65.0) == "Inconclusive"
        assert compute_ukvi_recommendation(45.0) == "Not Genuine"


class TestQuestionGenerationGraph:
    def test_generation_graph_execution_and_checkpoint(self):
        graph = build_question_generation_graph()
        initial_state: QuestionGenerationState = {
            "title": "MSc Artificial Intelligence",
            "difficulty": "Medium",
            "curriculum_text": "Modules include Deep Learning, Natural Language Processing, and Robotics.",
        }

        output = graph.invoke(initial_state)
        assert "synthesized_topics" in output
        topics = output["synthesized_topics"]
        assert len(topics) == 3  # Academic, Financial, Post-study
        assert output["is_reviewed_by_admin"] is True


class TestInterviewExecutionGraph:
    def test_interview_turn_loop_and_reask(self):
        graph = build_interview_execution_graph()

        sample_topics = [
            {
                "name": "Academic",
                "questions": [
                    {
                        "question_text": "Why this course?",
                        "expected_time_to_ans": 45,
                        "expected_answer_keywords": ["curriculum", "ranking"],
                        "followups": [
                            {
                                "followup_text": "Which module?",
                                "expected_time_to_ans": 30,
                                "expected_answer_keywords": ["robotics"],
                            }
                        ],
                    }
                ],
            }
        ]

        state: InterviewExecutionState = {
            "user_id": "student-123",
            "bank_id": "bank-abc",
            "bank_title": "UKVI Standard Bank",
            "difficulty": "Medium",
            "topics": sample_topics,
            "current_topic_index": 0,
            "current_question_index": 0,
            "current_followup_index": 0,
            "attempt_count": 1,
            "is_reask_active": False,
            "turns": [],
            "latest_transcript": "I like the high ranking.",  # Only 1 of 2 keywords -> 50% (< 70% threshold)
            "is_interview_concluded": False,
        }

        # Step 1: Execute evaluate and process -> Should trigger re-ask
        result = graph.invoke(state)

        # Confirm turn record was saved
        assert len(result["turns"]) >= 1
        first_turn = result["turns"][0]
        assert first_turn["score"] == 50.0
        assert "ranking" in first_turn["rubric_hits"]
        assert "curriculum" in first_turn["missed_keywords"]
