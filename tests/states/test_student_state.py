"""
Comprehensive unit tests for StudentData model.
Verifies:
1. Complete valid student record instantiation.
2. Minimal required fields instantiation (student_id, full_name, target_university, target_course).
3. Unrequired fields defaults (target_country, tuition_fee_gbp, etc.).
4. Missing required fields validation errors.
5. Empty strings validation failure (min_length=1).
6. Handling of extra unmodeled fields (safe ingress boundary behavior).
7. Numeric type coercion and validation.
8. Serialization / deserialization round-trip.
"""
import sys
from pathlib import Path

src_path = str(Path(__file__).resolve().parent.parent.parent / "src")
if src_path not in sys.path:
    sys.path.insert(0, src_path)

import unittest
from pydantic import ValidationError
from interview.state import StudentData


class TestStudentState(unittest.TestCase):
    def test_complete_valid_student(self):
        """Verify full student model parses and validates cleanly."""
        student = StudentData(
            student_id="UK-CAS-2026-9041",
            full_name="Tariqul Islam",
            target_country="United Kingdom",
            target_university="University of Hertfordshire",
            target_course="MSc Artificial Intelligence with Advanced Research",
            academic_background="BSc in Software Engineering, CGPA 3.65 out of 4.0",
            english_proficiency="IELTS Overall 7.5",
            tuition_fee_gbp=16500.0,
            living_cost_gbp=12500.0,
            available_funds_gbp=35000.0,
            sponsor_details="Personal savings meeting 28-day rule",
            post_study_plan="Return to Bangladesh as AI Architect",
        )
        self.assertEqual(student.student_id, "UK-CAS-2026-9041")
        self.assertEqual(student.full_name, "Tariqul Islam")
        self.assertEqual(student.tuition_fee_gbp, 16500.0)
        self.assertEqual(student.living_cost_gbp, 12500.0)
        self.assertEqual(student.available_funds_gbp, 35000.0)

    def test_minimal_required_fields(self):
        """Verify instantiation with only the 4 required fields."""
        student = StudentData(
            student_id="STU-001",
            full_name="Jane Doe",
            target_university="University of Oxford",
            target_course="MSc Computer Science",
        )
        self.assertEqual(student.student_id, "STU-001")
        self.assertEqual(student.full_name, "Jane Doe")
        self.assertEqual(student.target_university, "University of Oxford")
        self.assertEqual(student.target_course, "MSc Computer Science")

    def test_unrequired_fields_defaults(self):
        """Verify default values for all unrequired candidate fields."""
        student = StudentData(
            student_id="STU-002",
            full_name="John Smith",
            target_university="University of Cambridge",
            target_course="MPhil in Machine Learning",
        )
        self.assertEqual(student.target_country, "United Kingdom")
        self.assertEqual(student.academic_background, "")
        self.assertEqual(student.english_proficiency, "")
        self.assertEqual(student.tuition_fee_gbp, 0.0)
        self.assertEqual(student.living_cost_gbp, 0.0)
        self.assertEqual(student.available_funds_gbp, 0.0)
        self.assertEqual(student.sponsor_details, "")
        self.assertEqual(student.post_study_plan, "")

    def test_missing_required_fields_raises_validation_error(self):
        """Verify omitting any of the 4 required fields triggers ValidationError."""
        valid_args = {
            "student_id": "STU-003",
            "full_name": "Alice Wonderland",
            "target_university": "UCL",
            "target_course=" : "MSc Data Science",
        }
        # Missing student_id
        with self.assertRaises(ValidationError):
            StudentData(full_name="Alice", target_university="UCL", target_course="MSc DS")

        # Missing full_name
        with self.assertRaises(ValidationError):
            StudentData(student_id="S1", target_university="UCL", target_course="MSc DS")

        # Missing target_university
        with self.assertRaises(ValidationError):
            StudentData(student_id="S1", full_name="Alice", target_course="MSc DS")

        # Missing target_course
        with self.assertRaises(ValidationError):
            StudentData(student_id="S1", full_name="Alice", target_university="UCL")

    def test_empty_string_violates_min_length(self):
        """Verify empty strings for required fields fail min_length=1 validation."""
        with self.assertRaises(ValidationError):
            StudentData(
                student_id="",
                full_name="Valid Name",
                target_university="Valid Univ",
                target_course="Valid Course",
            )
        with self.assertRaises(ValidationError):
            StudentData(
                student_id="Valid ID",
                full_name="",
                target_university="Valid Univ",
                target_course="Valid Course",
            )

    def test_handling_additional_unmodeled_fields(self):
        """Verify extra unmodeled fields (e.g. from upstream JSON) are safely ignored without error."""
        payload = {
            "student_id": "STU-EXTRA",
            "full_name": "Bob Marley",
            "target_university": "Kingston University",
            "target_course": "Music Technology",
            "unmodeled_field_1": "some_value",
            "internal_tracking_id": 9999,
        }
        # In Pydantic V2, extra fields default to ignore
        student = StudentData(**payload)
        self.assertEqual(student.student_id, "STU-EXTRA")
        self.assertFalse(hasattr(student, "unmodeled_field_1"))

    def test_numeric_coercion_and_validation(self):
        """Verify integer and string numbers are coerced to float, but invalid strings are rejected."""
        student = StudentData(
            student_id="S-NUM",
            full_name="Num Tester",
            target_university="Bristol",
            target_course="MSc Robotics",
            tuition_fee_gbp=20000,          # int coerced to float
            living_cost_gbp="12000.50",     # string coerced to float
        )
        self.assertEqual(student.tuition_fee_gbp, 20000.0)
        self.assertEqual(student.living_cost_gbp, 12000.50)

        with self.assertRaises(ValidationError):
            StudentData(
                student_id="S-NUM",
                full_name="Num Tester",
                target_university="Bristol",
                target_course="MSc Robotics",
                tuition_fee_gbp="twenty thousand",
            )

    def test_json_roundtrip(self):
        """Verify model_dump_json and model_validate_json preserve fidelity."""
        orig = StudentData(
            student_id="S-ROUND",
            full_name="Round Trip",
            target_university="Manchester",
            target_course="MSc AI",
            tuition_fee_gbp=25000.0,
        )
        json_data = orig.model_dump_json()
        restored = StudentData.model_validate_json(json_data)
        self.assertEqual(orig, restored)


if __name__ == "__main__":
    unittest.main()
