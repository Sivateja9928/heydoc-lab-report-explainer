"""Tests that the evaluation harness scores only after extraction."""

import json
import tempfile
import unittest
from pathlib import Path

import pymupdf

from evals.run_evaluation import run_evaluation
from lab_extractor_agent.schemas import ExtractionReport, Flag, LabResult


class EvaluationRunnerTests(unittest.TestCase):
    def test_runner_extracts_before_loading_labels_and_writes_outputs(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cases_dir = root / "cases"
            output_dir = root / "results"
            cases_dir.mkdir()
            row = "Hb | 14.0 | g/dL | 12.0 - 16.0"
            document = pymupdf.open()
            page = document.new_page()
            page.insert_text((40, 50), row)
            document.save(cases_dir / "eval-001.pdf")
            document.close()

            event_order = []

            def fake_extractor(pdf_bytes):
                event_order.append("extract")
                return ExtractionReport(
                    extraction_mode="offline",
                    results=[LabResult(
                        test_name="Hb",
                        test_id="hemoglobin",
                        value_text="14.0",
                        value=14.0,
                        unit="g/dL",
                        reference_range="12.0 - 16.0",
                        flag=Flag.NORMAL,
                        source_page=1,
                        source_excerpt=row,
                    )],
                )

            def fake_truth_loader(_path):
                event_order.append("labels")
                self.assertEqual(event_order, ["extract", "labels"])
                return {
                    "EVAL-001": {
                        "case_id": "EVAL-001",
                        "panel": "cbc",
                        "scenario": "normal",
                        "test_id": "hemoglobin",
                        "value_text": "14.0",
                        "value": 14.0,
                        "unit": "g/dL",
                        "reference_range": "12.0 - 16.0",
                        "flag": "NORMAL",
                        "source_page": 1,
                        "source_excerpt": row,
                    }
                }

            result = run_evaluation(
                cases_dir,
                root / "labels-not-read-by-extractor.json",
                output_dir,
                extractor=fake_extractor,
                truth_loader=fake_truth_loader,
                expected_count=1,
            )

            self.assertEqual(event_order, ["extract", "labels"])
            self.assertEqual(result["metrics"]["test_id"]["correct"], 1)
            self.assertEqual(result["metrics"]["evidence_grounding"]["denominator"], 1)
            self.assertEqual(result["failed_cases"], [])
            self.assertTrue((output_dir / "offline_evaluation.md").is_file())
            parsed_json = json.loads((output_dir / "offline_evaluation.json").read_text())
            self.assertEqual(parsed_json["case_count"], 1)


if __name__ == "__main__":
    unittest.main()
