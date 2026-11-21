"""Offline extraction tests; all PDFs are created in memory from synthetic text."""

import unittest
import asyncio
from unittest.mock import patch

import pymupdf

from lab_extractor_agent.offline_extraction import extract_lab_report_offline
from lab_extractor_agent.extraction import extract_lab_report
from lab_extractor_agent.schemas import Flag


def make_pdf(*lines: str) -> bytes:
    document = pymupdf.open()
    page = document.new_page()
    y = 50
    for line in lines:
        page.insert_text((40, y), line, fontsize=10)
        y += 22
    result = document.tobytes()
    document.close()
    return result


class OfflineExtractionTests(unittest.TestCase):
    def test_normal_row_maps_alias_and_keeps_evidence(self):
        pdf = make_pdf(
            "Panel: hba1c | Scenario: normal",
            "HbA1c | 5.2 | % | 4.0 - 5.6",
        )

        with patch.dict("os.environ", {"HEYDOC_EXTRACTION_MODE": "offline"}):
            report = asyncio.run(extract_lab_report(pdf))

        self.assertEqual(len(report.results), 1)
        result = report.results[0]
        self.assertEqual(report.extraction_mode, "offline")
        self.assertEqual(result.test_id, "hba1c")
        self.assertEqual(result.flag, Flag.NORMAL)
        self.assertEqual(result.source_page, 1)
        self.assertIn("4.0 - 5.6", result.source_excerpt)

    def test_abnormal_alias_gets_deterministic_high_flag(self):
        pdf = make_pdf("SGPT | 50 | IU/L | 4 - 36")

        report = extract_lab_report_offline(pdf)

        result = report.results[0]
        self.assertEqual(result.test_id, "alt")
        self.assertEqual(result.flag, Flag.HIGH)
        self.assertEqual(result.unit, "IU/L")

    def test_missing_unit_and_required_panel_rows_remain_unknown(self):
        pdf = make_pdf(
            "Panel: cbc | Scenario: test",
            "Hb | 11.0 | [unit not printed] | 12.0 - 16.0",
        )

        report = extract_lab_report_offline(pdf)
        by_id = {result.test_id: result for result in report.results}

        self.assertEqual(by_id["hemoglobin"].flag, Flag.UNKNOWN)
        self.assertIsNone(by_id["hemoglobin"].unit)
        self.assertEqual(by_id["rbc"].flag, Flag.UNKNOWN)
        self.assertIsNone(by_id["rbc"].source_excerpt)
        self.assertEqual(by_id["wbc"].flag, Flag.UNKNOWN)
        self.assertEqual(by_id["platelets"].flag, Flag.UNKNOWN)
        self.assertEqual(len(report.results), 4)

    def test_malformed_known_row_is_preserved_without_guessing(self):
        source_line = "Hemoglobin result approx fourteen g/dL"
        report = extract_lab_report_offline(make_pdf(source_line))

        result = report.results[0]
        self.assertEqual(result.test_id, "hemoglobin")
        self.assertEqual(result.flag, Flag.UNKNOWN)
        self.assertIsNone(result.value)
        self.assertEqual(result.source_page, 1)
        self.assertEqual(result.source_excerpt, source_line)
        self.assertTrue(result.issues)


if __name__ == "__main__":
    unittest.main()
