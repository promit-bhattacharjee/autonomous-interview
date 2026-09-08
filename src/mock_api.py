import json
from pathlib import Path
from typing import Any, Dict, Optional

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
STUDENTS_DIR = DATA_DIR / "students"
UNIVERSITIES_DIR = DATA_DIR / "universities"


def fetch_student_api(student_id: str = "UK-CAS-2026-9041") -> Optional[Dict[str, Any]]:
    """
    Simulates a backend API endpoint (e.g. GET /api/v1/students/{student_id}).
    Loads structured JSON from data/students/.
    Returns None if the student ID is not found (404 Not Found).
    """
    if not student_id:
        return None

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

    # 3. If default/sample student requested
    if student_id == "UK-CAS-2026-9041":
        sample_file = STUDENTS_DIR / "sample_student.json"
        if sample_file.exists():
            with open(sample_file, "r", encoding="utf-8") as f:
                return json.load(f)

    # No record found in repository
    return None


def fetch_university_api(
    university_id: str = "UK-HERTS-01",
    course_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Simulates a backend API endpoint (e.g. GET /api/v1/universities/{university_id}).
    Loads structured JSON from data/universities/.
    Returns None if the university ID is not found (404 Not Found).
    """
    if not university_id:
        return None

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

    # 3. If default/sample university requested
    if university_id == "UK-HERTS-01":
        sample_file = UNIVERSITIES_DIR / "sample_university.json"
        if sample_file.exists():
            with open(sample_file, "r", encoding="utf-8") as f:
                return json.load(f)

    # No record found in repository
    return None
