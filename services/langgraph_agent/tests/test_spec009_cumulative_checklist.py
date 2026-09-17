"""
Unit tests for SPEC-009:
- Relational Deduplicated Keyword Ledger
- Cumulative Multi-Turn Keyword Scoring
- Re-Ask Probing targeting remaining unaddressed keywords
- Clean Question Progression & State Isolation
"""
from src.agent.keyword_ledger import RelationalKeywordLedger
from src.agent.graphs.interview_exec import (
    evaluate_answer_node,
    process_answer_node,
    ask_question_node,
    build_interview_execution_graph,
)
from src.agent.state import InterviewExecutionState


class TestRelationalKeywordLedger:
    def test_deduplication_and_order(self):
        """Verify that appending A, then B, then A only keeps [A, B] without duplication."""
        ledger = RelationalKeywordLedger()
        q_id = "test-q1"

        # Turn 1: matches A and B
        hits_turn1 = ledger.append_matches(q_id, ["curriculum", "ranking"])
        assert hits_turn1 == ["curriculum", "ranking"]

        # Turn 2: candidate repeats A and adds C
        hits_turn2 = ledger.append_matches(q_id, ["curriculum", "faculty"])
        assert hits_turn2 == ["curriculum", "ranking", "faculty"]

        # Turn 3: candidate repeats B and C
        hits_turn3 = ledger.append_matches(q_id, ["ranking", "faculty"])
        assert hits_turn3 == ["curriculum", "ranking", "faculty"]
        assert len(hits_turn3) == 3

    def test_missing_keywords_and_scoring(self):
        ledger = RelationalKeywordLedger()
        q_id = "test-q2"
        expected = ["tuition", "living_costs", "sponsor", "bank_statement"]

        ledger.append_matches(q_id, ["tuition", "sponsor"])
        missing = ledger.get_missing(q_id, expected)
        assert missing == ["living_costs", "bank_statement"]
        assert ledger.calculate_score(q_id, expected) == 50.0

        ledger.append_matches(q_id, ["living_costs", "bank_statement"])
        assert ledger.get_missing(q_id, expected) == []
        assert ledger.calculate_score(q_id, expected) == 100.0


class TestCumulativeMultiTurnScoring:
    def test_cumulative_checklist_scoring_progression(self):
        """
        Simulate a multi-turn scenario where a question has 10 keywords.
        Turn 1: Candidate covers 3 keywords (30%) -> triggers re-ask probe.
        Re-ask probe targets the 7 missing keywords.
        Turn 2: Candidate covers the remaining 7 keywords -> cumulative score reaches 100%.
        """
        ten_keywords = [
            "curriculum", "faculty", "ranking", "modules", "campus",
            "laboratory", "career", "alumni", "location", "reputation"
        ]
        q_id = "q-academic-01"

        initial_state: InterviewExecutionState = {
            "user_id": "test-student",
            "bank_id": "bank-1",
            "bank_title": "UKVI Test Bank",
            "difficulty": "Medium",
            "topics": [
                {
                    "name": "Academic",
                    "questions": [
                        {
                            "question_id": q_id,
                            "question_text": "Why did you choose this university?",
                            "expected_time_to_ans": 45,
                            "expected_answer_keywords": ten_keywords,
                            "followups": [],
                        }
                    ],
                }
            ],
            "current_topic_index": 0,
            "current_question_index": 0,
            "current_followup_index": 0,
            "attempt_count": 1,
            "is_reask_active": False,
            "current_prompt": "Why did you choose this university?",
            "expected_time_to_ans": 45,
            "expected_keywords": ten_keywords,
            "total_question_keywords": ten_keywords,
            "active_question_id": q_id,
            "active_question_hits": [],
            "keyword_ledger": {},
            "latest_transcript": "I selected this university because of its high ranking, world-class faculty, and innovative curriculum.",
            "latest_score": 0.0,
            "turns": [],
            "is_interview_concluded": False,
            "overall_score": 0.0,
            "ukvi_recommendation": "",
            "final_report_json": "{}",
        }

        # Step 1: Evaluate Turn 1 (Attempt 1)
        eval_turn1 = evaluate_answer_node(initial_state)
        initial_state.update(eval_turn1)

        assert initial_state["latest_score"] == 30.0
        assert len(initial_state["active_question_hits"]) == 3
        assert set(initial_state["active_question_hits"]) == {"curriculum", "faculty", "ranking"}

        # Step 2: Progression check -> Score < 70% on attempt 1 triggers re-ask
        progression1 = process_answer_node(initial_state)
        assert progression1["is_reask_active"] is True
        assert progression1["attempt_count"] == 2
        initial_state.update(progression1)

        # Step 3: Ask question node formulates re-ask probing missing keywords
        reask_prompt = ask_question_node(initial_state)
        initial_state.update(reask_prompt)
        assert "elaborate further regarding" in initial_state["current_prompt"]
        # Expected keywords on reask must be the 7 remaining missing keywords
        assert len(initial_state["expected_keywords"]) == 7
        assert "curriculum" not in initial_state["expected_keywords"]
        assert "modules" in initial_state["expected_keywords"]

        # Step 4: Evaluate Turn 2 (Attempt 2 - Candidate answers remaining points)
        initial_state["latest_transcript"] = (
            "Regarding the other aspects, the modules include robotics, the campus and laboratory facilities "
            "are cutting-edge, and the career support with alumni network enhances its great reputation in the location."
        )
        eval_turn2 = evaluate_answer_node(initial_state)
        initial_state.update(eval_turn2)

        # Cumulative hits must now be 10/10 -> 100%
        assert initial_state["latest_score"] == 100.0
        assert len(initial_state["active_question_hits"]) == 10
        assert set(initial_state["active_question_hits"]) == set(ten_keywords)

        # Step 5: Progression check -> 100% on attempt 2 advances past question
        progression2 = process_answer_node(initial_state)
        assert progression2["is_reask_active"] is False
        assert progression2["active_question_hits"] == []
        assert progression2["total_question_keywords"] == []
        assert progression2["is_interview_concluded"] is True
