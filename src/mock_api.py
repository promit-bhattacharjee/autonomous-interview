import json
from pathlib import Path
from typing import Any, Dict, Optional

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
STUDENTS_DIR = DATA_DIR / "students"
UNIVERSITIES_DIR = DATA_DIR / "universities"


def fetch_student_api(student_id: str = "UK-CAS-2026-9041") -> Dict[str, Any]:
    """
    Simulates a backend API endpoint (e.g. GET /api/v1/students/{student_id}).
    Loads structured JSON from data/students/.
    Matches future FastAPI endpoint response structure.
    """
    # 1. Attempt exact match by filename: e.g. UK-CAS-2026-9041.json
    specific_file = STUDENTS_DIR / f"{student_id}.json"
    if specific_file.exists():
        with open(specific_file, "r", encoding="utf-8") as f:
            return json.load(f)

    # 2. Check all json files in students dir to match student_id field
    if STUDENTS_DIR.exists():
        for file in STUDENTS_DIR.glob("*.json"):
            try:
                with open(file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if data.get("student_id") == student_id:
                        return data
            except Exception:
                continue

    # 3. Fallback to sample_student.json
    sample_file = STUDENTS_DIR / "sample_student.json"
    if sample_file.exists():
        with open(sample_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            data["student_id"] = student_id
            return data

    # Default baseline if file not found
    return {
        "student_id": student_id,
        "full_name": "Tariqul Islam",
        "target_country": "United Kingdom",
        "target_university": "University of Hertfordshire",
        "target_course": "MSc Artificial Intelligence with Advanced Research",
        "academic_background": "BSc in Software Engineering, CGPA 3.65 out of 4.0",
        "english_proficiency": "IELTS Overall 7.5 (Listening 8.0, Reading 7.5, Writing 7.0, Speaking 7.5)",
        "tuition_fee_gbp": 16500.0,
        "living_cost_gbp": 12500.0,
        "available_funds_gbp": 35000.0,
        "sponsor_details": "Father and personal savings meeting UKVI 28-day rule",
        "post_study_plan": "Return to home country to work as an AI Solutions Architect",
    }


def fetch_university_api(
    university_id: str = "UK-HERTS-01",
    course_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Simulates a backend API endpoint (e.g. GET /api/v1/universities/{university_id}).
    Loads structured JSON from data/universities/.
    Matches future FastAPI endpoint response structure.
    """
    # 1. Attempt exact match by filename
    specific_file = UNIVERSITIES_DIR / f"{university_id}.json"
    if specific_file.exists():
        with open(specific_file, "r", encoding="utf-8") as f:
            return json.load(f)

    # 2. Check all json files in universities dir to match university_id field
    if UNIVERSITIES_DIR.exists():
        for file in UNIVERSITIES_DIR.glob("*.json"):
            try:
                with open(file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if data.get("university_id") == university_id:
                        return data
            except Exception:
                continue

    # 3. Fallback to sample_university.json
    sample_file = UNIVERSITIES_DIR / "sample_university.json"
    if sample_file.exists():
        with open(sample_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            data["university_id"] = university_id
            return data

    # Default baseline if file not found
    return {
        "university_id": university_id,
        "official_name": "University of Hertfordshire",
        "campus_location": "Hatfield, Hertfordshire (Outside London)",
        "tuition_fee_gbp": 16500.0,
        "living_cost_guideline_gbp": 12500.0,
        "target_course": "MSc Artificial Intelligence with Advanced Research",
        "degree_level": "Postgraduate (Level 7)",
        "duration_months": 24,
        "core_modules": [
            {"module_code": "7COM1076", "title": "Machine Learning & Neural Networks"},
            {"module_code": "7COM1077", "title": "Robotics & Autonomous Systems"},
        ],
        "campus_facilities": ["Robotics and Autonomous Systems Laboratory"],
        "competitor_differentiators": ["Affordable tuition fee compared to London"],
        "compliance_rubrics": ["Know tuition and living maintenance amounts"],
    }
