"""
Unit tests verifying that the interview session terminates immediately
with dedicated, descriptive messages whenever student data, university data,
or required fields are missing.
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

import unittest
from interview.service import InterviewSession
from interview.state import StudentData, UniversityData
from mock_api import fetch_student_api, fetch_university_api


class TestMissingDataTermination(unittest.TestCase):
    def test_mock_api_returns_none_for_missing_ids(self):
        """Verify mock API returns None (404) for non-existent records."""
        self.assertIsNone(fetch_student_api("NON_EXISTENT_STUDENT"))
        self.assertIsNone(fetch_university_api("NON_EXISTENT_UNIVERSITY"))
        print("✅ Mock API correctly returns None for non-existent IDs.")

    def test_termination_on_missing_student_id(self):
        """Verify termination when student_id does not exist."""
        session = InterviewSession(student_id="INVALID-STUDENT-ID", university_id="UK-HERTS-01")
        result = session.start()

        self.assertEqual(session.latest_state.get("interview_status"), "completed")
        self.assertIn("❌ [DATA VALIDATION FAILED]", result)
        self.assertIn("INVALID-STUDENT-ID", result)
        self.assertEqual(len(session.latest_state.get("questions", [])), 0)
        print(f"✅ Terminated on missing student_id with dedicated message:\n   -> {result}")

    def test_termination_on_missing_university_id(self):
        """Verify termination when university_id does not exist."""
        session = InterviewSession(student_id="UK-CAS-2026-9041", university_id="INVALID-UNIV-ID")
        result = session.start()

        self.assertEqual(session.latest_state.get("interview_status"), "completed")
        self.assertIn("❌ [DATA VALIDATION FAILED]", result)
        self.assertIn("INVALID-UNIV-ID", result)
        self.assertEqual(len(session.latest_state.get("questions", [])), 0)
        print(f"✅ Terminated on missing university_id with dedicated message:\n   -> {result}")

    def test_termination_on_incomplete_student_data(self):
        """Verify termination when student_data is passed but missing target_course."""
        incomplete_student = StudentData(
            student_id="UK-CAS-TEST",
            full_name="Test Student",
            target_university="University of Hertfordshire",
            target_course="",  # Missing required field!
        )
        session = InterviewSession(
            student_data=incomplete_student,
            university_id="UK-HERTS-01",
        )
        result = session.start()

        self.assertEqual(session.latest_state.get("interview_status"), "completed")
        self.assertIn("❌ [DATA VALIDATION FAILED]", result)
        self.assertIn("target_course", result)
        self.assertEqual(len(session.latest_state.get("questions", [])), 0)
        print(f"✅ Terminated on incomplete student_data with dedicated message:\n   -> {result}")

    def test_termination_on_incomplete_university_data(self):
        """Verify termination when university_data is passed but missing official_name."""
        incomplete_univ = UniversityData(
            university_id="UK-TEST-01",
            official_name="",  # Missing required field!
        )
        session = InterviewSession(
            student_id="UK-CAS-2026-9041",
            university_data=incomplete_univ,
        )
        result = session.start()

        self.assertEqual(session.latest_state.get("interview_status"), "completed")
        self.assertIn("❌ [DATA VALIDATION FAILED]", result)
        self.assertIn("official_name", result)
        self.assertEqual(len(session.latest_state.get("questions", [])), 0)
        print(f"✅ Terminated on incomplete university_data with dedicated message:\n   -> {result}")


if __name__ == "__main__":
    unittest.main()
