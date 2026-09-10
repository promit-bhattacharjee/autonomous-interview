"""
Comprehensive unit tests for UniversityData model.
Verifies:
1. Complete valid university payload instantiation.
2. Minimal required fields instantiation (university_id, official_name).
3. Unrequired fields defaults (degree_level='Postgraduate', duration_months=12, list factories).
4. Missing required fields validation failure.
5. Empty strings validation failure (min_length=1).
6. Complex nested structures (core_modules dicts, string arrays).
7. Extra unmodeled fields handling.
8. Serialization / deserialization round-trip.
"""
import sys
from pathlib import Path

src_path = str(Path(__file__).resolve().parent.parent.parent / "src")
if src_path not in sys.path:
    sys.path.insert(0, src_path)

import unittest
from pydantic import ValidationError
from interview.state import UniversityData


class TestUniversityState(unittest.TestCase):
    def test_complete_valid_university(self):
        """Verify complete university specifications parse cleanly."""
        modules = [
            {"code": "7COM1076", "title": "Advanced Artificial Intelligence"},
            {"code": "7COM1077", "title": "Applied Data Science and Analytics"},
        ]
        facilities = ["Hertfordshire High-Performance Computing (HPC) Cluster", "Robotics Laboratory"]
        differentiators = ["1-year placement option", "Close proximity to London tech cluster"]
        rubrics = ["Academic progression justification", "Course module specificity"]

        univ = UniversityData(
            university_id="UK-HERTS-01",
            official_name="University of Hertfordshire",
            campus_location="College Lane, Hatfield",
            tuition_fee_gbp=16500.0,
            living_cost_guideline_gbp=12500.0,
            target_course="MSc Artificial Intelligence",
            degree_level="Postgraduate / Level 7",
            duration_months=24,
            core_modules=modules,
            campus_facilities=facilities,
            competitor_differentiators=differentiators,
            compliance_rubrics=rubrics,
        )
        self.assertEqual(univ.university_id, "UK-HERTS-01")
        self.assertEqual(univ.official_name, "University of Hertfordshire")
        self.assertEqual(univ.tuition_fee_gbp, 16500.0)
        self.assertEqual(univ.duration_months, 24)
        self.assertEqual(len(univ.core_modules), 2)
        self.assertEqual(len(univ.campus_facilities), 2)

    def test_minimal_required_fields(self):
        """Verify instantiation with only the 2 required fields."""
        univ = UniversityData(
            university_id="UK-CAM-01",
            official_name="University of Cambridge",
        )
        self.assertEqual(univ.university_id, "UK-CAM-01")
        self.assertEqual(univ.official_name, "University of Cambridge")

    def test_unrequired_fields_defaults(self):
        """Verify default values for unrequired fields."""
        univ = UniversityData(
            university_id="UK-OX-01",
            official_name="University of Oxford",
        )
        self.assertEqual(univ.campus_location, "")
        self.assertEqual(univ.tuition_fee_gbp, 0.0)
        self.assertEqual(univ.living_cost_guideline_gbp, 0.0)
        self.assertEqual(univ.target_course, "")
        self.assertEqual(univ.degree_level, "Postgraduate")
        self.assertEqual(univ.duration_months, 12)
        self.assertEqual(univ.core_modules, [])
        self.assertEqual(univ.campus_facilities, [])
        self.assertEqual(univ.competitor_differentiators, [])
        self.assertEqual(univ.compliance_rubrics, [])

    def test_missing_required_fields_raises_validation_error(self):
        """Verify omitting university_id or official_name triggers ValidationError."""
        # Missing university_id
        with self.assertRaises(ValidationError):
            UniversityData(official_name="Imperial College London")

        # Missing official_name
        with self.assertRaises(ValidationError):
            UniversityData(university_id="UK-IMP-01")

        # Completely empty
        with self.assertRaises(ValidationError):
            UniversityData()

    def test_empty_string_violates_min_length(self):
        """Verify empty strings fail min_length=1 check."""
        with self.assertRaises(ValidationError):
            UniversityData(university_id="", official_name="Valid Name")

        with self.assertRaises(ValidationError):
            UniversityData(university_id="UK-01", official_name="")

    def test_extra_unmodeled_fields_ignored_safely(self):
        """Verify extra unmodeled fields do not cause validation failure."""
        payload = {
            "university_id": "UK-UCL-01",
            "official_name": "University College London",
            "non_existent_key": "ignore_me",
            "ranking_times_higher_ed": 8,
        }
        univ = UniversityData(**payload)
        self.assertEqual(univ.university_id, "UK-UCL-01")
        self.assertFalse(hasattr(univ, "non_existent_key"))

    def test_default_lists_independence(self):
        """Verify list factories produce distinct instances across objects."""
        u1 = UniversityData(university_id="U1", official_name="Univ 1")
        u2 = UniversityData(university_id="U2", official_name="Univ 2")
        u1.core_modules.append({"code": "M1", "title": "Module 1"})
        self.assertEqual(len(u1.core_modules), 1)
        self.assertEqual(len(u2.core_modules), 0)

    def test_json_roundtrip(self):
        """Verify model_dump_json and model_validate_json preserve fidelity."""
        orig = UniversityData(
            university_id="UK-MAN-01",
            official_name="University of Manchester",
            tuition_fee_gbp=27000.0,
            campus_facilities=["Alan Turing Building"],
        )
        json_str = orig.model_dump_json()
        restored = UniversityData.model_validate_json(json_str)
        self.assertEqual(orig, restored)


if __name__ == "__main__":
    unittest.main()
