"""
Relational Deduplicated Keyword Ledger (SPEC-009).

Maintains a relational, deduplicated keyword ledger across viva examination questions and turns.
Guarantees idempotency: appending a keyword multiple times (e.g. A, then B, then A)
retains only single occurrences [A, B] without duplication, matching hash-map / set uniqueness.
"""
from typing import Any


class RelationalKeywordLedger:
    """
    Relational keyword tracker keyed by question/topic reference ID.
    Guarantees unique deduplicated keyword collection per question.
    """

    def __init__(self, raw_ledger: dict[str, list[str]] | None = None):
        # Maps question_id -> dict of {keyword: True} for O(1) deduplicated ordered storage
        self._entries: dict[str, dict[str, bool]] = {}
        if raw_ledger:
            for q_id, kws in raw_ledger.items():
                self._entries[q_id] = {k: True for k in kws}

    def append_matches(self, question_id: str, new_keywords: list[str]) -> list[str]:
        """
        Appends matched keywords to the specified question.
        Automatically skips any duplicates, maintaining first-seen order.
        Returns the full deduplicated list of matched keywords for the question.
        """
        if question_id not in self._entries:
            self._entries[question_id] = {}
        for kw in new_keywords:
            self._entries[question_id][kw] = True
        return list(self._entries[question_id].keys())

    def get_hits(self, question_id: str) -> list[str]:
        """Returns all deduplicated matched keywords for the given question."""
        return list(self._entries.get(question_id, {}).keys())

    def get_missing(self, question_id: str, expected_keywords: list[str]) -> list[str]:
        """Returns the list of expected keywords that have not yet been matched."""
        hits = set(self.get_hits(question_id))
        return [k for k in expected_keywords if k not in hits]

    def calculate_score(self, question_id: str, expected_keywords: list[str]) -> float:
        """Calculates cumulative percentage score [0.0 - 100.0] for the question."""
        if not expected_keywords:
            return 100.0
        hits = self.get_hits(question_id)
        return round((len(hits) / len(expected_keywords)) * 100.0, 1)

    def to_dict(self) -> dict[str, list[str]]:
        """Exports the ledger as a serializable dict[str, list[str]]."""
        return {q_id: list(kws.keys()) for q_id, kws in self._entries.items()}
