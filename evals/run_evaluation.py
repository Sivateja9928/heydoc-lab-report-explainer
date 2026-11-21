"""Run offline extraction first, then score against separate evaluation labels."""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
import time
import unicodedata
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lab_extractor_agent.offline_extraction import extract_lab_report_offline
from lab_extractor_agent.pdf_text import extract_pdf_text
from lab_extractor_agent.schemas import ExtractionReport


DEFAULT_CASES = ROOT / "evals" / "cases"
DEFAULT_GROUND_TRUTH = ROOT / "evals" / "ground_truth.json"
DEFAULT_OUTPUT = ROOT / "evals" / "results"


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).replace("Âµ", "µ").replace("Î¼", "µ")
    return " ".join(text.casefold().split())


def load_ground_truth(path: Path) -> dict[str, dict]:
    """Read labels for scoring. Called only after extraction has completed."""
    data = json.loads(path.read_text(encoding="utf-8"))
    return {case["case_id"]: case for case in data["cases"]}


def _grounded(result, page_texts: dict[int, str]) -> bool:
    if not result or not result.source_excerpt or result.source_page not in page_texts:
        return False
    excerpt = _normalize(result.source_excerpt)
    if excerpt not in _normalize(page_texts[result.source_page]):
        return False
    for extracted_field in (result.value_text, result.unit, result.reference_range):
        if extracted_field and _normalize(extracted_field) not in excerpt:
            return False
    return True


def _score_case(case_id: str, prediction: dict, truth: dict) -> dict:
    expected = truth
    report: ExtractionReport | None = prediction["report"]
    failed_fields: list[str] = []
    predicted = None
    if report:
        matching = [item for item in report.results if item.test_id == expected["test_id"]]
        predicted = matching[0] if matching else None

    checks = {
        "test_id": bool(predicted),
        "value_text": predicted is not None and predicted.value_text == expected["value_text"],
        "numeric_value": predicted is not None and predicted.value == expected["value"],
        "unit": predicted is not None and predicted.unit == expected["unit"],
        "reference_range": predicted is not None and predicted.reference_range == expected["reference_range"],
        "flag": predicted is not None and predicted.flag.value == expected["flag"],
    }
    page_texts: dict[int, str] = {}
    if prediction["pdf_bytes"]:
        try:
            page_texts = {page.page_number: page.text for page in extract_pdf_text(prediction["pdf_bytes"])}
        except Exception:
            page_texts = {}
    checks["evidence_grounding"] = _grounded(predicted, page_texts)

    if expected["flag"] == "UNKNOWN":
        checks["unknown_handling"] = predicted is not None and predicted.flag.value == "UNKNOWN"
    else:
        checks["unknown_handling"] = predicted is not None and predicted.flag.value != "UNKNOWN"
    if expected["scenario"].startswith("missing_field"):
        checks["missing_field_handling"] = (
            predicted is not None
            and predicted.flag.value == "UNKNOWN"
            and all(
                getattr(predicted, field) is None
                for field, expected_value in (
                    ("value_text", expected["value_text"]),
                    ("unit", expected["unit"]),
                    ("reference_range", expected["reference_range"]),
                )
                if expected_value is None
            )
        )

    failed_fields = [field for field, passed in checks.items() if not passed]
    predicted_fields = None
    if predicted:
        predicted_fields = {
            "test_id": predicted.test_id,
            "test_name": predicted.test_name,
            "value_text": predicted.value_text,
            "value": predicted.value,
            "unit": predicted.unit,
            "reference_range": predicted.reference_range,
            "flag": predicted.flag.value,
            "source_page": predicted.source_page,
            "source_excerpt": predicted.source_excerpt,
            "issues": predicted.issues,
        }
    return {
        "case_id": case_id,
        "panel": expected["panel"],
        "scenario": expected["scenario"],
        "expected": {key: expected[key] for key in (
            "test_id", "value_text", "value", "unit", "reference_range", "flag",
            "source_page", "source_excerpt",
        )},
        "predicted": predicted_fields,
        "checks": checks,
        "failed_fields": failed_fields,
        "latency_ms": round(prediction["latency_ms"], 3),
        "extraction_error": prediction["error"],
    }


def _metric(case_results: list[dict], metric: str) -> dict:
    denominator = len(case_results)
    numerator = sum(bool(case["checks"].get(metric)) for case in case_results)
    return {
        "correct": numerator,
        "denominator": denominator,
        "accuracy_percent": round(100 * numerator / denominator, 2) if denominator else None,
    }


def build_results(case_results: list[dict], latencies: list[float]) -> dict:
    unknown_cases = [case for case in case_results if case["expected"]["flag"] == "UNKNOWN"]
    known_cases = [case for case in case_results if case["expected"]["flag"] != "UNKNOWN"]
    missing_cases = [case for case in case_results if case["scenario"].startswith("missing_field")]
    metrics = {
        metric: _metric(case_results, metric)
        for metric in (
            "test_id", "value_text", "numeric_value", "unit", "reference_range",
            "flag", "evidence_grounding",
        )
    }
    metrics["unknown_handling"] = {
        "correctly_unknown": sum(bool(case["checks"].get("unknown_handling")) for case in unknown_cases),
        "expected_unknown_cases": len(unknown_cases),
        "accuracy_percent": round(
            100 * sum(bool(case["checks"].get("unknown_handling")) for case in unknown_cases) / len(unknown_cases), 2
        ) if unknown_cases else None,
        "unexpected_unknown_in_classifiable_cases": sum(
            case["predicted"] is not None and case["predicted"]["flag"] == "UNKNOWN"
            for case in known_cases
        ),
        "classifiable_case_denominator": len(known_cases),
    }
    metrics["missing_field_handling"] = {
        "correct": sum(bool(case["checks"].get("missing_field_handling")) for case in missing_cases),
        "denominator": len(missing_cases),
        "accuracy_percent": round(
            100 * sum(bool(case["checks"].get("missing_field_handling")) for case in missing_cases) / len(missing_cases), 2
        ) if missing_cases else None,
    }
    return {
        "evaluation_mode": "offline",
        "case_count": len(case_results),
        "metrics": metrics,
        "latency_ms": {
            "mean": round(statistics.mean(latencies), 3) if latencies else None,
            "median": round(statistics.median(latencies), 3) if latencies else None,
            "p95": round(sorted(latencies)[max(0, math.ceil(0.95 * len(latencies)) - 1)], 3) if latencies else None,
            "denominator_reports": len(latencies),
            "per_report": {case["case_id"]: case["latency_ms"] for case in case_results},
        },
        "failed_cases": [
            {"case_id": case["case_id"], "failed_fields": case["failed_fields"], "extraction_error": case["extraction_error"]}
            for case in case_results if case["failed_fields"] or case["extraction_error"]
        ],
        "cases": case_results,
        "clinical_validity": "Not evaluated; all reports are synthetic software fixtures.",
    }


def render_markdown(results: dict) -> str:
    metrics = results["metrics"]
    lines = [
        "# Offline extraction evaluation",
        "",
        f"Cases: **{results['case_count']}**. Mode: **offline**. No Gemini calls were made for this evaluation.",
        "Synthetic software evaluation only; these results do not establish clinical validity.",
        "",
        "## Metrics",
        "",
        "| Metric | Correct | Denominator | Accuracy |",
        "|---|---:|---:|---:|",
    ]
    display = {
        "test_id": "Test identification",
        "value_text": "Value text extraction",
        "numeric_value": "Numeric value parsing",
        "unit": "Unit extraction",
        "reference_range": "Reference-range extraction",
        "flag": "Flag correctness",
        "evidence_grounding": "Evidence grounding",
    }
    for metric, label in display.items():
        stat = metrics[metric]
        lines.append(f"| {label} | {stat['correct']} | {stat['denominator']} | {stat['accuracy_percent']}% |")
    unknown = metrics["unknown_handling"]
    missing = metrics["missing_field_handling"]
    lines.extend([
        f"| UNKNOWN handling | {unknown['correctly_unknown']} | {unknown['expected_unknown_cases']} expected UNKNOWN | {unknown['accuracy_percent']}% |",
        f"| Missing-field handling | {missing['correct']} | {missing['denominator']} | {missing['accuracy_percent']}% |",
        f"| Unexpected UNKNOWN among classifiable cases | {unknown['unexpected_unknown_in_classifiable_cases']} | {unknown['classifiable_case_denominator']} | — |",
        "",
        "## Per-report results",
        "",
        "| Case | Panel | Scenario | Expected ID | Predicted ID | Failed checks | Latency (ms) |",
        "|---|---|---|---|---|---|---:|",
    ])
    for case in results["cases"]:
        predicted = case["predicted"]
        predicted_id = predicted["test_id"] if predicted else "—"
        failed = ", ".join(case["failed_fields"]) if case["failed_fields"] else "—"
        lines.append(
            f"| {case['case_id']} | {case['panel']} | {case['scenario']} | "
            f"{case['expected']['test_id']} | {predicted_id} | {failed} | {case['latency_ms']:.3f} |"
        )
    lines.extend([
        "",
        "## Failed cases",
        "",
    ])
    if results["failed_cases"]:
        for failed in results["failed_cases"]:
            lines.append(f"- **{failed['case_id']}**: {', '.join(failed['failed_fields']) or failed['extraction_error']}")
    else:
        lines.append("None.")
    latency = results["latency_ms"]
    lines.extend([
        "",
        "## Latency",
        "",
        f"Mean {latency['mean']} ms; median {latency['median']} ms; p95 {latency['p95']} ms; denominator {latency['denominator_reports']} reports.",
        "",
        "Latency is local offline processing time and excludes Gemini/API costs. No project cost total is estimated here.",
        "",
    ])
    return "\n".join(lines)


def run_evaluation(
    cases_dir: Path,
    ground_truth_path: Path,
    output_dir: Path,
    *,
    extractor: Callable[[bytes], ExtractionReport] = extract_lab_report_offline,
    truth_loader: Callable[[Path], dict[str, dict]] = load_ground_truth,
    expected_count: int | None = 30,
) -> dict:
    """Extract every PDF before loading evaluation labels for scoring."""
    pdf_paths = sorted(cases_dir.glob("eval-*.pdf"))
    if expected_count is not None and len(pdf_paths) != expected_count:
        raise ValueError(f"Expected {expected_count} evaluation PDFs, found {len(pdf_paths)}")

    # The extractor receives only PDF bytes. Ground truth is intentionally not
    # loaded until every extraction has returned.
    predictions: list[dict] = []
    for pdf_path in pdf_paths:
        pdf_bytes = pdf_path.read_bytes()
        started = time.perf_counter()
        report = None
        error = None
        try:
            report = extractor(pdf_bytes)
        except Exception as exc:
            error = type(exc).__name__
        latency_ms = (time.perf_counter() - started) * 1000
        predictions.append({
            "case_id": pdf_path.stem.upper(),
            "report": report,
            "pdf_bytes": pdf_bytes,
            "latency_ms": latency_ms,
            "error": error,
        })

    ground_truth = truth_loader(ground_truth_path)
    expected_ids = {item["case_id"] for item in predictions}
    if expected_ids != set(ground_truth):
        raise ValueError("Evaluation PDF IDs do not match the ground-truth case IDs")
    case_results = [
        _score_case(item["case_id"], item, ground_truth[item["case_id"]])
        for item in predictions
    ]
    results = build_results(case_results, [item["latency_ms"] for item in predictions])

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "offline_evaluation.json").write_text(
        json.dumps(results, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (output_dir / "offline_evaluation.md").write_text(render_markdown(results), encoding="utf-8")
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases-dir", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--ground-truth", type=Path, default=DEFAULT_GROUND_TRUTH)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    results = run_evaluation(args.cases_dir, args.ground_truth, args.output_dir)
    print(json.dumps({"case_count": results["case_count"], "metrics": results["metrics"], "failed_cases": results["failed_cases"]}, indent=2))


if __name__ == "__main__":
    main()
