"""Tests for deterministic bilingual explanations and next-step rules."""

import unittest

from lab_extractor_agent.explanation import (
    ActionType,
    generate_explanations,
    recommend_next_step,
)
from lab_extractor_agent.schemas import ExtractionReport, Flag, LabResult


def result(test_id, name, value, unit, reference_range, flag):
    value_text = str(value) if value is not None else None
    row = f"{name} | {value_text or '[not printed]'} | {unit or '[unit not printed]'} | {reference_range or '[range not printed]'}"
    return LabResult(
        test_name=name,
        test_id=test_id,
        value_text=value_text,
        value=float(value) if value is not None else None,
        unit=unit,
        reference_range=reference_range,
        flag=flag,
        source_page=1,
        source_excerpt=row,
    )


def cbc_report(hemoglobin_flag=Flag.NORMAL, *, missing_platelets=False, missing_hgb_value=False):
    rows = [
        result("hemoglobin", "Hb", None if missing_hgb_value else "14.0", "g/dL", "12.0 - 16.0", Flag.UNKNOWN if missing_hgb_value else hemoglobin_flag),
        result("rbc", "RBC", "4.8", "million/uL", "4.2 - 5.4", Flag.NORMAL),
        result("wbc", "WBC", "7000", "cells/uL", "4500 - 11000", Flag.NORMAL),
    ]
    if not missing_platelets:
        rows.append(result("platelets", "PLT", "250", "10^9/L", "150 - 400", Flag.NORMAL))
    return ExtractionReport(results=rows, extraction_mode="offline")


class ExplanationTests(unittest.TestCase):
    def test_complete_normal_cbc_has_english_hindi_and_no_action(self):
        bundle = generate_explanations(cbc_report(), "cbc")

        self.assertEqual(len(bundle.tests), 4)
        self.assertEqual(bundle.next_step.action_type, ActionType.NO_ACTION)
        self.assertEqual(bundle.next_step.package_id, None)
        hgb = next(item for item in bundle.tests if item.test_id == "hemoglobin")
        self.assertIn("14.0", hgb.english)
        self.assertIn("g/dL", hgb.english)
        self.assertIn("12.0 - 16.0", hgb.english)
        self.assertIn("NORMAL", hgb.english)
        self.assertIn("14.0", hgb.hindi)
        self.assertIn("12.0 - 16.0", hgb.hindi)
        self.assertIn("NORMAL", hgb.hindi)
        self.assertTrue(bundle.critical_detection_configured)
        self.assertIn("limited Labcorp-specific", bundle.critical_detection_notice_en)

    def test_abnormal_mapped_result_selects_follow_up_package(self):
        bundle = generate_explanations(cbc_report(Flag.LOW), "cbc")

        self.assertEqual(bundle.next_step.action_type, ActionType.FOLLOW_UP_TEST_PACKAGE)
        self.assertEqual(bundle.next_step.package_id, "CBC_FOLLOWUP")
        self.assertEqual(bundle.next_step.reason_test_ids, ["hemoglobin"])

    def test_unknown_flag_is_explicit_and_never_normal(self):
        report = cbc_report(missing_hgb_value=True)
        bundle = generate_explanations(report, "cbc")
        hgb = next(item for item in bundle.tests if item.test_id == "hemoglobin")

        self.assertEqual(hgb.flag, Flag.UNKNOWN)
        self.assertIn("unavailable in the report", hgb.english)
        self.assertIn("not considered normal", hgb.english)
        self.assertIn("रिपोर्ट में उपलब्ध नहीं", hgb.hindi)
        self.assertIn("UNKNOWN", hgb.hindi)
        self.assertEqual(bundle.next_step.action_type, ActionType.DOCTOR_CONSULT)

    def test_missing_required_test_is_shown_unknown_and_requires_consult(self):
        report = cbc_report(missing_platelets=True)
        bundle = generate_explanations(report, "cbc")
        platelets = next(item for item in bundle.tests if item.test_id == "platelets")

        self.assertEqual(platelets.flag, Flag.UNKNOWN)
        self.assertIn("unavailable in the report", platelets.english)
        self.assertEqual(bundle.next_step.action_type, ActionType.DOCTOR_CONSULT)
        self.assertIn("platelets", bundle.next_step.reason_test_ids)

    def test_unmapped_abnormal_and_mixed_packages_require_consult(self):
        unmapped = ExtractionReport(results=[
            result("hemoglobin", "Hb", "19", "g/dL", "12 - 16", Flag.HIGH),
            result("rbc", "RBC", "4.8", "million/uL", "4.2 - 5.4", Flag.NORMAL),
            result("wbc", "WBC", "7000", "cells/uL", "4500 - 11000", Flag.NORMAL),
            result("platelets", "PLT", "250", "10^9/L", "150 - 400", Flag.NORMAL),
        ])
        self.assertEqual(recommend_next_step(unmapped, "cbc").action_type, ActionType.DOCTOR_CONSULT)

        mixed = ExtractionReport(results=[
            result("ldl", "LDL", "130", "mg/dL", "< 100", Flag.HIGH),
            result("hba1c", "HbA1c", "6.0", "%", "4.0 - 5.6", Flag.HIGH),
            result("hdl", "HDL", "55", "mg/dL", ">= 50", Flag.NORMAL),
            result("total_cholesterol", "TC", "180", "mg/dL", "< 200", Flag.NORMAL),
            result("triglycerides", "TG", "120", "mg/dL", "< 150", Flag.NORMAL),
        ])
        self.assertEqual(recommend_next_step(mixed, "lipid_profile").action_type, ActionType.DOCTOR_CONSULT)

    def test_only_three_action_values_are_exposed(self):
        self.assertEqual(
            {item.value for item in ActionType},
            {"follow_up_test_package", "doctor_consult", "no_action"},
        )


if __name__ == "__main__":
    unittest.main()
