import json
import os
from pathlib import Path
from typing import Any, Dict, Optional


def load_question_file(file_path: str) -> str:
    """Reads the admin-uploaded question file (text, rubric, markdown)."""
    p = Path(file_path)
    if not p.exists():
        raise FileNotFoundError(f"Question file not found at: {file_path}")
    return p.read_text(encoding="utf-8").strip()


def load_student_profile(profile_path: str) -> Dict[str, Any]:
    """Reads student CAS & interview profile from a JSON file."""
    p = Path(profile_path)
    if not p.exists():
        raise FileNotFoundError(f"Student profile not found at: {profile_path}")
    return json.loads(p.read_text(encoding="utf-8"))


def build_initial_interview_payload(
    student_data: Dict[str, Any],
    question_content: str,
    difficulty: str = "Medium",
    expected_time_to_ans: int = 45,
) -> Dict[str, Any]:
    """
    Synthesizes the Admin Question File and Student Profile into
    the initial text payload required by the LangGraph interview brain.
    """
    # Format student profile into readable text context
    student_summary = (
        f"STUDENT PROFILE & VISA CONTEXT:\n"
        f"- Full Name: {student_data.get('full_name', 'Applicant')}\n"
        f"- Target UK Institution: {student_data.get('target_university', 'UK University')}\n"
        f"- Target Course: {student_data.get('target_course', 'N/A')}\n"
        f"- Academic Background: {student_data.get('academic_background', 'N/A')}\n"
        f"- English Proficiency: {student_data.get('english_proficiency', 'N/A')}\n"
        f"- Tuition & Living Expenses: {student_data.get('tuition_fee_gbp', '')} + {student_data.get('living_cost_gbp', '')}\n"
        f"- Sponsor / Funding: {student_data.get('sponsor_details', '')}\n"
        f"- Career & Post-Study Plan: {student_data.get('post_study_plan', '')}\n"
    )

    combined_text = (
        f"{student_summary}\n"
        f"ADMIN QUESTION RUBRIC & CRITERIA:\n"
        f"{question_content}"
    )

    return {
        "extraced_text": combined_text,
        "difficulty": difficulty,
        "expected_time_to_ans": expected_time_to_ans,
        "expected_total_time_to_ans": expected_time_to_ans,
        "iterations": 1,
        "conofidance": 1.0,
        "expected_answer_keywords": [
            student_data.get("target_university", "University"),
            "tuition",
            "sponsor",
            "career",
        ],
    }
