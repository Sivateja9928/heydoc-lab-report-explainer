"""Tests for exact-unit, age-scoped critical policy comparisons."""

import unittest

from lab_extractor_agent.critical_policy import apply_critical_policy
from lab_extractor_agent.explanation import ActionType, recommend_next_step
from lab_extractor_agent.schemas import CriticalStatus, ExtractionReport, Flag, LabResult


ADULT_MALE = ">15 years Male"


def hemoglobin(value: float, unit: str = "g/dL") -> LabResult:
    return LabResult(
        test_name="Hemoglobin", test_id="hemoglobin", value_text=str(value),
        value=value, unit=unit, reference_range="12.0 - 16.0",
        flag=Flag.HIGH if value > 16 else Flag.LOW if value < 12 else Flag.NORMAL,
        source_page=1, source_excerpt=f"Hemoglobin | {value} | {unit} | 12.0 - 16.0",
    )


class CriticalPolicyTests(unittest.TestCase):
    def classify(self, result, age_group=ADULT_MALE):
        return apply_critical_policy(ExtractionReport(results=[result]), age_group=age_group).results[0]

    def test_critical_high_overrides_ordinary_flag_and_routes_urgent_consult(self):
        result = self.classify(hemoglobin(22.0))
        self.assertEqual(result.ordinary_flag, Flag.HIGH)
        self.assertEqual(result.flag, Flag.CRITICAL_HIGH)
        self.assertEqual(result.critical_status, CriticalStatus.CRITICAL_HIGH)
        self.assertIn("Labcorp", result.critical_source_name)
        self.assertEqual(result.critical_threshold, 21.4)
        step = recommend_next_step(ExtractionReport(results=[hemoglobin(22.0)]), "cbc", age_group=ADULT_MALE)
        self.assertEqual(step.action_type, ActionType.DOCTOR_CONSULT)
        self.assertEqual(step.urgency, "urgent")
        self.assertIn("URGENT", step.urgent_message_en)

    def test_critical_low(self):
        result = self.classify(hemoglobin(6.0))
        self.assertEqual(result.flag, Flag.CRITICAL_LOW)
        self.assertEqual(result.critical_status, CriticalStatus.CRITICAL_LOW)
        self.assertEqual(result.critical_threshold, 6.1)

    def test_strict_boundary_values_are_not_critical(self):
        low = self.classify(hemoglobin(6.1))
        high = self.classify(hemoglobin(21.4))
        self.assertEqual(low.critical_status, CriticalStatus.NOT_CRITICAL)
        self.assertEqual(high.critical_status, CriticalStatus.NOT_CRITICAL)
        self.assertEqual(low.flag, low.ordinary_flag)
        self.assertEqual(high.flag, high.ordinary_flag)

    def test_unit_mismatch_stays_unconfigured_without_conversion(self):
        result = self.classify(hemoglobin(30.0, "g/L"))
        self.assertEqual(result.critical_status, CriticalStatus.UNCONFIGURED)
        self.assertEqual(result.flag, Flag.HIGH)

    def test_unsupported_test_stays_unconfigured_even_if_ordinary_high(self):
        result = LabResult(
            test_name="White blood cell count", test_id="wbc", value_text="50000",
            value=50000, unit="cells/uL", reference_range="4500 - 11000",
            flag=Flag.HIGH, source_page=1,
            source_excerpt="WBC | 50000 | cells/uL | 4500 - 11000",
        )
        classified = self.classify(result)
        self.assertEqual(classified.critical_status, CriticalStatus.UNCONFIGURED)
        self.assertEqual(classified.flag, Flag.HIGH)

    def test_missing_or_wrong_age_group_stays_unconfigured(self):
        self.assertEqual(self.classify(hemoglobin(30), None).critical_status, CriticalStatus.UNCONFIGURED)
        self.assertEqual(self.classify(hemoglobin(30), "adult").critical_status, CriticalStatus.UNCONFIGURED)

    def test_missing_evidence_is_indeterminate_and_not_critical(self):
        row = hemoglobin(30).model_copy(update={"source_excerpt": None})
        classified = self.classify(row)
        self.assertEqual(classified.critical_status, CriticalStatus.INDETERMINATE)
        self.assertEqual(classified.flag, Flag.HIGH)

    def test_validator_evidence_failure_blocks_critical_classification(self):
        row = hemoglobin(30).model_copy(update={
            "issues": ["Evidence excerpt could not be verified on the cited page."]
        })
        classified = self.classify(row)
        self.assertEqual(classified.critical_status, CriticalStatus.INDETERMINATE)

    def test_bilirubin_adult_high_limit_matches_exact_unit_and_age(self):
        result = LabResult(
            test_name="Total bilirubin", test_id="total_bilirubin", value_text="18.0",
            value=18.0, unit="mg/dL", reference_range="0.1 - 1.2", flag=Flag.HIGH,
            source_page=1, source_excerpt="Total bilirubin | 18.0 | mg/dL | 0.1 - 1.2",
        )
        classified = self.classify(result, "1 month and older to adults")
        self.assertEqual(classified.flag, Flag.CRITICAL_HIGH)
        self.assertEqual(classified.critical_threshold, 17.0)


if __name__ == "__main__":
    unittest.main()
