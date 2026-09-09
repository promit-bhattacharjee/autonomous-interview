"""
Unit tests verifying FastAPI/Pydantic ingress validation:
- Validates data integrity before entering the graph workflow.
- Ensures missing required fields or invalid types trigger Pydantic ValidationError.
- Ensures static model configuration operates directly from environment variables.
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
from pydantic import ValidationError
from interview.state import StudentData, UniversityData
from mock_api import fetch_student_api, fetch_university_api
from interview.helper import get_speech_llm, get_thinking_llm


class TestPydanticIngressValidation(unittest.TestCase):
    def test_mock_api_returns_none_for_missing_ids(self):
        """Verify mock API returns None (404) for non-existent records."""
        self.assertIsNone(fetch_student_api("NON_EXISTENT_STUDENT"))
        self.assertIsNone(fetch_university_api("NON_EXISTENT_UNIVERSITY"))
        print("✅ Mock API correctly returns None for non-existent IDs.")

    def test_pydantic_validation_error_on_missing_student_required_fields(self):
        """Verify Pydantic immediately blocks invalid/empty student payloads at ingress boundary."""
        # Missing required fields: student_id, full_name, target_university, target_course
        with self.assertRaises(ValidationError) as ctx:
            StudentData(
                student_id="",
                full_name="",
                target_university="",
                target_course="",
            )
        errors = ctx.exception.errors()
        self.assertTrue(len(errors) >= 1)
        print("✅ Pydantic correctly blocked incomplete StudentData at ingress.")

        # Completely empty payload
        with self.assertRaises(ValidationError):
            StudentData()

    def test_pydantic_validation_error_on_missing_university_required_fields(self):
        """Verify Pydantic immediately blocks incomplete university payloads at ingress boundary."""
        # Missing official_name
        with self.assertRaises(ValidationError):
            UniversityData(
                university_id="UK-HERTS-01",
                official_name="",
            )
        # Completely empty payload
        with self.assertRaises(ValidationError):
            UniversityData()
        print("✅ Pydantic correctly blocked incomplete UniversityData at ingress.")

    def test_pydantic_validation_error_on_invalid_types(self):
        """Verify Pydantic raises ValidationError on invalid data types (e.g. non-numeric tuition)."""
        with self.assertRaises(ValidationError):
            StudentData(
                student_id="UK-123",
                full_name="Valid Name",
                target_university="Valid Univ",
                target_course="Valid Course",
                tuition_fee_gbp="not_a_valid_number",  # Invalid type
            )
        print("✅ Pydantic correctly rejected invalid type for tuition_fee_gbp.")

    def test_valid_pydantic_ingress_models(self):
        """Verify valid payloads pass Pydantic ingress validation without error."""
        raw_student = fetch_student_api("UK-CAS-2026-9041")
        self.assertIsNotNone(raw_student)
        student = StudentData(**raw_student)
        self.assertEqual(student.student_id, "UK-CAS-2026-9041")
        self.assertEqual(student.tuition_fee_gbp, 16500.0)

        raw_univ = fetch_university_api("UK-HERTS-01")
        self.assertIsNotNone(raw_univ)
        univ = UniversityData(**raw_univ)
        self.assertEqual(univ.university_id, "UK-HERTS-01")
        print("✅ Valid student and university data successfully pass Pydantic validation.")

    def test_static_model_configuration(self):
        """Verify models are initialized statically from .env without dynamic mock APIs."""
        import os
        speech_llm = get_speech_llm()
        self.assertIsNotNone(speech_llm)
        model_name = getattr(speech_llm, "model", getattr(speech_llm, "model_name", None))
        expected_speech = os.getenv("SPEECH_MODEL", "gemini-3.6-flash")
        self.assertEqual(model_name, expected_speech)

        thinking_llm = get_thinking_llm()
        self.assertIsNotNone(thinking_llm)
        thinking_model_name = getattr(thinking_llm, "model_name", getattr(thinking_llm, "model", None))
        expected_thinking = os.getenv("OPENROUTER_MODEL", "deepseek/deepseek-v4-flash-0731")
        self.assertEqual(thinking_model_name, expected_thinking)
        print("✅ Models are configured statically via .env configuration.")


if __name__ == "__main__":
    unittest.main()

