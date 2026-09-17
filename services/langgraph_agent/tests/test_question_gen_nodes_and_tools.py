"""
Comprehensive unit tests for Question Generation Graph nodes and Relational Ingestion Tools.
Verifies:
1. parse_curriculum_node, synthesize_topics_node (tier behavior, limits).
2. admin_review_checkpoint_node (modifications vs pass-through).
3. commit_bank_node (ORM persistence and simulated fallback).
4. Relational fetcher tools (fetch_topics, fetch_questions, fetch_followups, get_user_assigned_questions, fetch_user_model_config).
"""
import pytest
from unittest.mock import MagicMock, patch

from src.agent.graphs.question_gen import (
    parse_curriculum_node,
    synthesize_topics_node,
    admin_review_checkpoint_node,
    commit_bank_node,
    build_question_generation_graph,
)
from src.agent.state import QuestionGenerationState
from src.agent.tools.relational_fetchers import (
    fetch_topics,
    fetch_questions,
    fetch_followups,
    get_user_assigned_questions,
    fetch_user_model_config,
    _get_db_session_if_available,
)


class TestQuestionGenNodes:
    def test_parse_curriculum_node_defaults_and_custom(self):
        state: QuestionGenerationState = {
            "title": "Computer Science MSc",
            "difficulty": "Hard",
            "curriculum_text": "  Advanced Algorithms and Quantum Computing  ",
        }
        res = parse_curriculum_node(state)
        assert res["title"] == "Computer Science MSc"
        assert res["difficulty"] == "Hard"
        assert res["curriculum_text"] == "Advanced Algorithms and Quantum Computing"

    def test_synthesize_topics_node_tiers(self):
        # Medium tier: 45s / 30s
        med_state: QuestionGenerationState = {
            "title": "Data Science",
            "difficulty": "Medium",
            "curriculum_text": "Machine Learning",
        }
        med_res = synthesize_topics_node(med_state)
        topics = med_res["synthesized_topics"]
        assert len(topics) == 3
        assert topics[0]["questions"][0]["expected_time_to_ans"] == 45
        assert topics[0]["questions"][0]["followups"][0]["expected_time_to_ans"] == 30

        # Hard tier: 60s / 45s
        hard_state: QuestionGenerationState = {
            "title": "Data Science",
            "difficulty": "Hard",
            "curriculum_text": "Machine Learning",
        }
        hard_res = synthesize_topics_node(hard_state)
        hard_topics = hard_res["synthesized_topics"]
        assert hard_topics[0]["questions"][0]["expected_time_to_ans"] == 60
        assert hard_topics[0]["questions"][0]["followups"][0]["expected_time_to_ans"] == 45

    def test_admin_review_checkpoint_node(self):
        # Without modifications
        state_no_mod: QuestionGenerationState = {"is_reviewed_by_admin": False}
        res1 = admin_review_checkpoint_node(state_no_mod)
        assert res1["is_reviewed_by_admin"] is True
        assert "synthesized_topics" not in res1

        # With modifications
        custom_topics = [{"name": "Custom Topic", "questions": []}]
        state_mod: QuestionGenerationState = {
            "admin_modifications": custom_topics,
            "is_reviewed_by_admin": False,
        }
        res2 = admin_review_checkpoint_node(state_mod)
        assert res2["is_reviewed_by_admin"] is True
        assert res2["synthesized_topics"] == custom_topics

    def test_commit_bank_node_simulated_fallback(self):
        # When DB cannot be imported / fails, fallback gracefully
        state: QuestionGenerationState = {
            "title": "Simulated Bank",
            "difficulty": "Medium",
            "synthesized_topics": [],
        }
        with patch("src.agent.graphs.question_gen.commit_bank_node", wraps=commit_bank_node):
            res = commit_bank_node(state)
            assert "published_bank_id" in res
            assert isinstance(res["published_bank_id"], str)

    def test_build_question_generation_graph(self):
        graph = build_question_generation_graph()
        assert graph is not None
        initial: QuestionGenerationState = {
            "title": "Graph Compile Test",
            "difficulty": "Easy",
            "curriculum_text": "Robotics",
        }
        output = graph.invoke(initial)
        assert output["is_reviewed_by_admin"] is True
        assert "published_bank_id" in output


class TestRelationalFetchersTools:
    def test_db_session_if_available(self):
        sess = _get_db_session_if_available()
        # Should either return a Session or None without raising
        if sess is not None:
            sess.close()

    def test_fetch_topics_mock_fallback(self):
        with patch("httpx.Client.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = [{"id": "t1", "name": "Topic 1"}]
            mock_get.return_value = mock_resp

            # Force exception in direct ORM to test fallback
            with patch("src.agent.tools.relational_fetchers._qs", None):
                res = fetch_topics.invoke({"bank_id": "test-bank"})
                assert len(res) == 1
                assert res[0]["name"] == "Topic 1"

    def test_fetch_questions_mock_fallback(self):
        with patch("httpx.Client.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = [{"id": "q1", "question_text": "Why?"}]
            mock_get.return_value = mock_resp

            with patch("src.agent.tools.relational_fetchers._qs", None):
                res = fetch_questions.invoke({"topic_id": "t1"})
                assert len(res) == 1
                assert res[0]["question_text"] == "Why?"

    def test_fetch_followups_mock_fallback(self):
        with patch("httpx.Client.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = [{"id": "f1", "followup_text": "Elaborate?"}]
            mock_get.return_value = mock_resp

            with patch("src.agent.tools.relational_fetchers._qs", None):
                res = fetch_followups.invoke({"question_id": "q1"})
                assert len(res) == 1
                assert res[0]["followup_text"] == "Elaborate?"

    def test_get_user_assigned_questions_mock_fallback(self):
        with patch("httpx.Client.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {"bank_id": "b1", "title": "Assigned Bank"}
            mock_get.return_value = mock_resp

            with patch("src.agent.tools.relational_fetchers._qs", None):
                res = get_user_assigned_questions.invoke({"user_id": "u1"})
                assert res["bank_id"] == "b1"

    def test_fetch_user_model_config_defaults(self):
        res = fetch_user_model_config.invoke({"user_id": "test_user_no_custom"})
        assert "thinking" in res
        assert "stt" in res
        assert "tts" in res
        assert res["thinking"]["source"] in ("vault", "env", "student_vault", "admin_provided", "env_fallback")
