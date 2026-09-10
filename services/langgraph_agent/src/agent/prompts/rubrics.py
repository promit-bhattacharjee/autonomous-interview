from typing import Tuple


def evaluate_response_keywords(transcript: str, expected_keywords: list[str]) -> Tuple[float, list[str], list[str]]:
    """
    Evaluates candidate transcript against explicit UKVI expected keywords.
    Returns (score_percentage, hits, missed).
    """
    if not expected_keywords:
        return 100.0, [], []

    text = transcript.lower()
    hits = [kw for kw in expected_keywords if kw.lower() in text]
    missed = [kw for kw in expected_keywords if kw.lower() not in text]

    score = round((len(hits) / len(expected_keywords)) * 100.0, 1)
    return score, hits, missed


def compute_ukvi_recommendation(overall_score: float) -> str:
    """Computes UKVI credibility category based on weighted overall performance."""
    if overall_score >= 70.0:
        return "Genuine"
    elif overall_score >= 50.0:
        return "Inconclusive"
    else:
        return "Not Genuine"
