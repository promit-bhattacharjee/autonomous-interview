"""
Comprehensive unit tests for mock_api data loading and model ingestion.
Verifies:
1. Student data loading (exact match, scanning, sample fallback, 404 None).
2. University data loading (exact match, scanning, sample fallback, 404 None).
3. Empty / None identifier handling.
4. Clean parsing of API dictionaries into StudentData and UniversityData models.
5. Ingress validation failure when mock data is missing required fields or malformed.
"""
import sys
from pathlib import Path

src_path = str(Path(__file__).resolve().parent.parent.parent / "src")
if src_path not in sys.path:
    sys.path.insert(0, src_path)

import unittest
from pydantic import ValidationError
from mock_api import fetch_student_api, fetch_university_api
from interview.state import StudentData, UniversityData


class TestMockApi(unittest.TestCase):
    # --------------------------------------------------------------------------
    # 1. Student API Tests
    # --------------------------------------------------------------------------
    def test_fetch_student_default(self):
        """Verify fetching student with default ID 'UK-CAS-2026-9041' loads valid dict."""
        data = fetch_student_api()
        self.assertIsInstance(data, dict)
        self.assertEqual(data.get("student_id"), "UK-CAS-2026-9041")
        self.assertEqual(data.get("full_name"), "Tariqul Islam")

    def test_fetch_student_explicit_valid_id(self):
        """Verify fetching student with explicit valid ID."""
        data = fetch_student_api("UK-CAS-2026-9041")
        self.assertIsNotNone(data)
        self.assertEqual(data["student_id"], "UK-CAS-2026-9041")
        self.assertEqual(data["target_university"], "University of Hertfordshire")
        self.assertIn("tuition_fee_gbp", data)
        self.assertIn("living_cost_gbp", data)

    def test_fetch_student_non_existent(self):
        """Verify non-existent student ID returns None (404 Not Found)."""
        data = fetch_student_api("UNKNOWN-STUDENT-9999")
        self.assertIsNone(data)

    def test_fetch_student_empty_or_none(self):
        """Verify empty string or None returns None immediately."""
        self.assertIsNone(fetch_student_api(""))
        self.assertIsNone(fetch_student_api(None))  # type: ignore

    def test_student_api_to_student_data_model(self):
        """Verify raw API dict parses directly into strict StudentData model."""
        raw_data = fetch_student_api("UK-CAS-2026-9041")
        self.assertIsNotNone(raw_data)
        student = StudentData(**raw_data)
        self.assertEqual(student.student_id, "UK-CAS-2026-9041")
        self.assertEqual(student.full_name, "Tariqul Islam")
        self.assertEqual(student.tuition_fee_gbp, 16500.0)
        self.assertEqual(student.living_cost_gbp, 12500.0)
        self.assertEqual(student.available_funds_gbp, 35000.0)

    # --------------------------------------------------------------------------
    # 2. University API Tests
    # --------------------------------------------------------------------------
    def test_fetch_university_default(self):
        """Verify fetching university with default ID 'UK-HERTS-01' loads valid dict."""
        data = fetch_university_api()
        self.assertIsInstance(data, dict)
        self.assertEqual(data.get("university_id"), "UK-HERTS-01")
        self.assertIn("Hertfordshire", data.get("official_name", ""))

    def test_fetch_university_explicit_valid_id(self):
        """Verify fetching university with explicit valid ID."""
        data = fetch_university_api("UK-HERTS-01")
        self.assertIsNotNone(data)
        self.assertEqual(data["university_id"], "UK-HERTS-01")
        self.assertEqual(data["official_name"], "University of Hertfordshire")
        self.assertEqual(data["tuition_fee_gbp"], 16500.0)
        self.assertIsInstance(data.get("core_modules"), list)
        self.assertGreater(len(data["core_modules"]), 0)

    def test_fetch_university_non_existent(self):
        """Verify non-existent university ID returns None (404 Not Found)."""
        data = fetch_university_api("UNKNOWN-UNIV-9999")
        self.assertIsNone(data)

    def test_fetch_university_empty_or_none(self):
        """Verify empty string or None returns None immediately."""
        self.assertIsNone(fetch_university_api(""))
        self.assertIsNone(fetch_university_api(None))  # type: ignore

    def test_university_api_to_university_data_model(self):
        """Verify raw API dict parses directly into strict UniversityData model."""
        raw_data = fetch_university_api("UK-HERTS-01")
        self.assertIsNotNone(raw_data)
        univ = UniversityData(**raw_data)
        self.assertEqual(univ.university_id, "UK-HERTS-01")
        self.assertEqual(univ.official_name, "University of Hertfordshire")
        self.assertEqual(univ.tuition_fee_gbp, 16500.0)
        self.assertEqual(univ.duration_months, 24)
        self.assertIsInstance(univ.core_modules, list)

    # --------------------------------------------------------------------------
    # 3. Ingress Boundary Validation with Corrupted Data
    # --------------------------------------------------------------------------
    def test_corrupted_student_api_payload_triggers_pydantic_error(self):
        """Verify that if an API payload is missing required fields, StudentData rejects it."""
        corrupted_payload = {
            "student_id": "UK-CORRUPT-01",
            # Missing full_name, target_university, target_course
            "tuition_fee_gbp": 15000.0,
        }
        with self.assertRaises(ValidationError):
            StudentData(**corrupted_payload)

    def test_corrupted_university_api_payload_triggers_pydantic_error(self):
        """Verify that if an API payload is missing required fields, UniversityData rejects it."""
        corrupted_payload = {
            # Missing official_name
            "university_id": "UK-CORRUPT-UNIV",
            "tuition_fee_gbp": 14000.0,
        }
        with self.assertRaises(ValidationError):
            UniversityData(**corrupted_payload)


if __name__ == "__main__":
    unittest.main()
