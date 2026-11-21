"""Generate and verify the deterministic selectable-text HeyDoc fixture set."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pymupdf


ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "config" / "test_catalog.json"
DATASET_DIR = ROOT / "synthetic_dataset"
REPORT_DIR = DATASET_DIR / "reports"


def _number(value: float | int | str | None) -> str:
    if value is None:
        return "[not printed]"
    return str(value)


def _bounds(range_text: str) -> tuple[float | None, bool | None, float | None, bool | None] | None:
    text = range_text.strip()
    one_sided = re.fullmatch(r"(<=|>=|<|>)\s*(\d+(?:\.\d+)?)", text)
    if one_sided:
        operator, raw_bound = one_sided.groups()
        bound = float(raw_bound)
        if operator.startswith(">"):
            return bound, operator == ">=", None, None
        return None, None, bound, operator == "<="
    interval = re.fullmatch(r"(\d+(?:\.\d+)?)\s*(-|–|to)\s*(\d+(?:\.\d+)?)", text, re.I)
    if interval:
        lower, _, upper = interval.groups()
        return float(lower), True, float(upper), True
    return None


def _flag(value_text: str | None, range_text: str | None) -> str:
    if value_text is None or range_text is None:
        return "UNKNOWN"
    value_match = re.fullmatch(r"\s*(<=|>=|<|>)?\s*(\d+(?:\.\d+)?)\s*", value_text)
    bounds = _bounds(range_text)
    if not value_match or bounds is None:
        return "UNKNOWN"
    qualifier, raw_value = value_match.groups()
    value = float(raw_value)
    lower, lower_inclusive, upper, upper_inclusive = bounds
    if qualifier:
        if qualifier in ("<", "<=") and lower is not None:
            entirely_low = value < lower or (
                value == lower and (qualifier == "<" or lower_inclusive is False)
            )
            if entirely_low:
                return "LOW"
        if qualifier in (">", ">=") and upper is not None:
            entirely_high = value > upper or (
                value == upper and (qualifier == ">" or upper_inclusive is False)
            )
            if entirely_high:
                return "HIGH"
        return "UNKNOWN"
    if lower is not None and (value < lower or (value == lower and lower_inclusive is False)):
        return "LOW"
    if upper is not None and (value > upper or (value == upper and upper_inclusive is False)):
        return "HIGH"
    return "NORMAL"


def _case_specs(catalog: dict) -> list[dict]:
    """Return 15 cases, exactly normal/abnormal/noisy for each panel."""
    ranges = {
        test_id: entry["illustrative_reference_range"]
        for test_id, entry in catalog["tests"].items()
    }
    return [
        {"id": "DEMO-CBC-01", "panel": "cbc", "scenario": "normal", "overrides": {}, "missing_tests": [], "format": "standard"},
        {"id": "DEMO-CBC-02", "panel": "cbc", "scenario": "abnormal", "overrides": {"hemoglobin": {"value": 11.0}}, "missing_tests": [], "format": "standard"},
        {"id": "DEMO-CBC-03", "panel": "cbc", "scenario": "noisy_missing_unit_and_test", "overrides": {"wbc": {"unit": None}}, "missing_tests": ["rbc"], "format": "noisy"},
        {"id": "DEMO-LIPID-01", "panel": "lipid_profile", "scenario": "normal", "overrides": {}, "missing_tests": [], "format": "standard"},
        {"id": "DEMO-LIPID-02", "panel": "lipid_profile", "scenario": "abnormal", "overrides": {"ldl": {"value": 130}, "hdl": {"value": 44}}, "missing_tests": [], "format": "standard"},
        {"id": "DEMO-LIPID-03", "panel": "lipid_profile", "scenario": "noisy_ambiguous_range_and_missing_test", "overrides": {"total_cholesterol": {"range": "goal varies by risk"}}, "missing_tests": ["hdl"], "format": "noisy"},
        {"id": "DEMO-HBA1C-01", "panel": "hba1c", "scenario": "normal", "overrides": {}, "missing_tests": [], "format": "standard"},
        {"id": "DEMO-HBA1C-02", "panel": "hba1c", "scenario": "abnormal", "overrides": {"hba1c": {"value": 5.9}}, "missing_tests": [], "format": "standard"},
        {"id": "DEMO-HBA1C-03", "panel": "hba1c", "scenario": "noisy_qualified_value", "overrides": {"hba1c": {"value_text": "<5.7"}}, "missing_tests": [], "format": "noisy"},
        {"id": "DEMO-THYROID-01", "panel": "thyroid_profile", "scenario": "normal", "overrides": {}, "missing_tests": [], "format": "standard"},
        {"id": "DEMO-THYROID-02", "panel": "thyroid_profile", "scenario": "abnormal", "overrides": {"tsh": {"value": 6.0}}, "missing_tests": [], "format": "standard"},
        {"id": "DEMO-THYROID-03", "panel": "thyroid_profile", "scenario": "noisy_missing_unit_and_ambiguous_range", "overrides": {"free_t4": {"unit": None}, "t3": {"range": "age-specific; not stated"}}, "missing_tests": [], "format": "noisy"},
        {"id": "DEMO-LFT-01", "panel": "liver_function", "scenario": "normal", "overrides": {}, "missing_tests": [], "format": "standard"},
        {"id": "DEMO-LFT-02", "panel": "liver_function", "scenario": "abnormal", "overrides": {"alt": {"value": 50}}, "missing_tests": [], "format": "standard"},
        {"id": "DEMO-LFT-03", "panel": "liver_function", "scenario": "noisy_missing_value", "overrides": {"ast": {"value": None}}, "missing_tests": [], "format": "noisy"}
    ]


def _base_value(test_id: str) -> float:
    values = {
        "hemoglobin": 14.0, "rbc": 4.8, "wbc": 7000, "platelets": 250,
        "total_cholesterol": 180, "hdl": 55, "ldl": 90, "triglycerides": 120,
        "hba1c": 5.2, "tsh": 2.0, "t3": 110, "free_t4": 1.2,
        "alt": 20, "ast": 20, "alp": 80, "total_bilirubin": 0.7
    }
    return values[test_id]


def _choose_alias(entry: dict, noisy: bool, index: int) -> str:
    choices = entry["aliases"] if noisy else [entry["canonical_name"]]
    return choices[index % len(choices)]


def _choose_unit(entry: dict, noisy: bool, index: int) -> str:
    choices = entry["unit_aliases"] if noisy else [entry["canonical_unit"]]
    return choices[index % len(choices)]


def _render_line(label: str, value_text: str | None, unit: str | None, range_text: str | None, noisy: bool) -> str:
    result = _number(value_text)
    unit_cell = unit if unit else "[unit not printed]"
    range_cell = range_text if range_text else "[range not printed]"
    if noisy:
        return f"Test: {label} || Result: {result} || Unit: {unit_cell} || Ref: {range_cell}"
    return f"{label} | {result} | {unit_cell} | {range_cell}"


def _create_pdf(case: dict, result_lines: list[str], output_path: Path) -> None:
    document = pymupdf.open()
    page = document.new_page(width=612, height=792)
    page.insert_text((48, 48), "HEYDOC SYNTHETIC LAB REPORT - NOT FOR CLINICAL USE", fontsize=12)
    page.insert_text((48, 70), f"Panel: {case['panel']} | Scenario: {case['scenario']}", fontsize=10)
    page.insert_text((48, 90), "All patient and result data on this page are fictional.", fontsize=9)
    y = 130
    for line in result_lines:
        page.insert_text((48, y), line, fontsize=9)
        y += 27 if case["format"] == "noisy" else 22
    output_path.parent.mkdir(parents=True, exist_ok=True)
    document.save(output_path)
    document.close()


def generate() -> tuple[list[dict], list[dict]]:
    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    ground_truth: dict[str, dict] = {}
    manifest: list[dict] = []
    for case_index, case in enumerate(_case_specs(catalog)):
        test_ids = catalog["panels"][case["panel"]]
        overrides = case["overrides"]
        rendered: dict[str, dict] = {}
        lines: list[str] = []
        for test_index, test_id in enumerate(test_ids):
            if test_id in case["missing_tests"]:
                rendered[test_id] = {"present": False, "value_text": None, "unit": None, "range": None, "line": None}
                continue

            entry = catalog["tests"][test_id]
            override = overrides.get(test_id, {})
            noisy = case["format"] == "noisy"
            label = _choose_alias(entry, noisy, case_index + test_index)
            unit = override.get("unit", _choose_unit(entry, noisy, case_index + test_index))
            range_text = override.get("range", entry["illustrative_reference_range"])
            numeric_value = override.get("value", _base_value(test_id))
            if "value_text" in override:
                value_text = override["value_text"]
            else:
                value_text = None if numeric_value is None else str(numeric_value)
            line = _render_line(label, value_text, unit, range_text, noisy)
            lines.append(line)
            rendered[test_id] = {
                "present": True, "label": label, "value_text": value_text,
                "unit": unit, "range": range_text, "numeric_value": numeric_value,
                "line": line
            }

        file_name = f"{case['id'].lower().replace('-', '_')}.pdf"
        relative_pdf = Path("reports") / file_name
        _create_pdf(case, lines, DATASET_DIR / relative_pdf)

        document = pymupdf.open(DATASET_DIR / relative_pdf)
        extracted_pages = [page.get_text("text") for page in document]
        document.close()
        expected_results = {}
        for test_id in test_ids:
            observed = rendered[test_id]
            entry = catalog["tests"][test_id]
            if not observed["present"]:
                expected_results[test_id] = {
                    "present": False, "test_name_original": None, "value_text": None,
                    "value": None, "value_qualifier": None, "unit_original": None,
                    "unit_canonical": None, "reference_range_raw": None,
                    "range_lower": None, "range_lower_inclusive": None,
                    "range_upper": None, "range_upper_inclusive": None,
                    "flag": "UNKNOWN", "source_page": None, "source_excerpt": None,
                    "issues": ["Required test row missing."]
                }
                continue

            # Use the PDF's extracted line as the verbatim evidence excerpt.
            extracted_line = next(
                (line.strip() for line in extracted_pages[0].splitlines() if line.strip() == observed["line"]),
                None,
            )
            if extracted_line is None:
                raise AssertionError(f"Could not find generated evidence line for {case['id']} {test_id}")

            bounds = _bounds(observed["range"])
            value_match = re.fullmatch(r"\s*(<=|>=|<|>)?\s*(\d+(?:\.\d+)?)\s*", observed["value_text"] or "")
            parsed_value = float(value_match.group(2)) if value_match else None
            qualifier = value_match.group(1) if value_match else None
            flag = _flag(observed["value_text"], observed["range"])
            issues = []
            if parsed_value is None:
                issues.append("Missing or unsupported result value.")
            if not observed["unit"]:
                issues.append("Missing unit.")
            if bounds is None:
                issues.append("Reference range is ambiguous or unsupported.")
            expected_results[test_id] = {
                "present": True,
                "test_name_original": observed["label"],
                "value_text": observed["value_text"],
                "value": parsed_value,
                "value_qualifier": qualifier,
                "unit_original": observed["unit"],
                "unit_canonical": entry["canonical_unit"] if observed["unit"] in entry["unit_aliases"] else None,
                "reference_range_raw": observed["range"],
                "range_lower": bounds[0] if bounds else None,
                "range_lower_inclusive": bounds[1] if bounds else None,
                "range_upper": bounds[2] if bounds else None,
                "range_upper_inclusive": bounds[3] if bounds else None,
                "flag": flag if observed["unit"] else "UNKNOWN",
                "source_page": 1,
                "source_excerpt": extracted_line,
                "issues": issues
            }

        ground_truth[case["id"]] = {
            "report_id": case["id"], "panel": case["panel"], "scenario": case["scenario"],
            "pdf": relative_pdf.as_posix(), "results": expected_results,
            "critical_status": "NOT_CONFIGURED"
        }
        manifest.append({
            "report_id": case["id"], "panel": case["panel"], "scenario": case["scenario"],
            "pdf": relative_pdf.as_posix(), "ground_truth_ref": f"ground_truth.json#/{case['id']}"
        })

    return list(ground_truth.values()), manifest


def verify(ground_truth_records: list[dict], manifest: list[dict]) -> dict:
    """Reopen all files and verify their evidence and ground-truth links."""
    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    truth_by_id = {record["report_id"]: record for record in ground_truth_records}
    assert len(manifest) == 15, f"Expected 15 manifest records, found {len(manifest)}"
    assert len(truth_by_id) == 15, f"Expected 15 ground-truth records, found {len(truth_by_id)}"
    checked_rows = 0
    for item in manifest:
        report_id = item["report_id"]
        truth = truth_by_id[report_id]
        pdf_path = DATASET_DIR / item["pdf"]
        assert pdf_path.is_file(), f"PDF missing: {pdf_path}"
        document = pymupdf.open(pdf_path)
        assert document.page_count == 1, f"Unexpected page count for {report_id}"
        page_text = document[0].get_text("text")
        document.close()
        assert page_text.strip(), f"No selectable text in {report_id}"
        assert item["ground_truth_ref"].endswith(f"#/{report_id}")
        assert item["pdf"] == truth["pdf"]
        for test_id, result in truth["results"].items():
            if result["present"]:
                excerpt = result["source_excerpt"]
                assert excerpt and excerpt in page_text, f"Evidence mismatch {report_id}/{test_id}"
                assert result["source_page"] == 1
                assert result["reference_range_raw"] in excerpt
                if result["value_text"]:
                    assert result["value_text"] in excerpt
                if result["unit_original"]:
                    assert result["unit_original"] in excerpt
                checked_rows += 1
            else:
                assert result["source_excerpt"] is None
                assert result["source_page"] is None
                possible_labels = [
                    catalog["tests"][test_id]["canonical_name"],
                    *catalog["tests"][test_id]["aliases"],
                ]
                assert not any(label.casefold() in page_text.casefold() for label in possible_labels)
    return {"pdf_count": len(manifest), "ground_truth_count": len(truth_by_id), "verified_result_rows": checked_rows}


def main() -> None:
    ground_truth, manifest = generate()
    DATASET_DIR.mkdir(parents=True, exist_ok=True)
    (DATASET_DIR / "ground_truth.json").write_text(
        json.dumps({record["report_id"]: record for record in ground_truth}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (DATASET_DIR / "manifest.json").write_text(
        json.dumps({"reports": manifest}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    summary = verify(ground_truth, manifest)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
