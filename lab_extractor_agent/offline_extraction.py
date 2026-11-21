"""Deterministic parser for the synthetic report text layouts."""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

from .pdf_text import ExtractedPage, extract_pdf_text
from .schemas import CandidateResult, ExtractionReport, Flag
from .validation import validate_candidates


CATALOG_PATH = Path(__file__).resolve().parents[1] / "config" / "test_catalog.json"
STANDARD_ROW = re.compile(r"^\s*(.*?)\s*\|\s*(.*?)\s*\|\s*(.*?)\s*\|\s*(.*?)\s*$")
NAMED_ROW = re.compile(
    r"^\s*Test:\s*(.*?)\s*\|\|\s*Result:\s*(.*?)\s*\|\|\s*"
    r"Unit:\s*(.*?)\s*\|\|\s*Ref:\s*(.*?)\s*$",
    re.IGNORECASE,
)
PANEL_LINE = re.compile(r"^\s*Panel:\s*([^|]+)", re.IGNORECASE)
MISSING_MARKERS = {
    "", "-", "--", "—", "[not printed]", "[unit not printed]",
    "[range not printed]", "n/a", "na", "none",
}


def _normalize(value: str) -> str:
    """Normalize label/unit spelling without converting units."""
    value = unicodedata.normalize("NFKC", value)
    value = value.replace("Âµ", "µ").replace("Î¼", "µ").replace("μ", "µ")
    return " ".join(value.casefold().split())


def _load_catalog() -> dict:
    with CATALOG_PATH.open(encoding="utf-8") as catalog_file:
        return json.load(catalog_file)


def _alias_index(catalog: dict) -> dict[str, str]:
    index: dict[str, str] = {}
    for test_id, definition in catalog["tests"].items():
        labels = [definition["canonical_name"], *definition["aliases"], test_id]
        for label in labels:
            index[_normalize(label)] = test_id
    return index


def _unit_is_known(test_id: str | None, unit: str | None, catalog: dict) -> bool:
    if not test_id or not unit:
        return False
    aliases = catalog["tests"][test_id]["unit_aliases"]
    normalized_unit = _normalize(unit)
    return any(_normalize(alias) == normalized_unit for alias in aliases)


def _field_or_none(value: str | None) -> str | None:
    if value is None or value.strip().casefold() in MISSING_MARKERS:
        return None
    return value.strip()


def _match_test(label: str, alias_index: dict[str, str]) -> str | None:
    normalized = _normalize(label)
    if normalized in alias_index:
        return alias_index[normalized]
    for alias, test_id in sorted(alias_index.items(), key=lambda pair: len(pair[0]), reverse=True):
        if normalized.startswith(alias + " ") or normalized.startswith(alias + ":"):
            return test_id
    return None


def _parse_row(line: str) -> tuple[str, str | None, str | None, str | None] | None:
    """Read either fixture row layout while preserving each cell's text."""
    match = NAMED_ROW.match(line)
    if match:
        label, value, unit, reference_range = match.groups()
        return (
            label.strip(), _field_or_none(value), _field_or_none(unit),
            _field_or_none(reference_range),
        )

    if line.count("|") == 3 and "||" not in line:
        match = STANDARD_ROW.match(line)
        if match:
            label, value, unit, reference_range = match.groups()
            if label.strip():
                return (
                    label.strip(), _field_or_none(value), _field_or_none(unit),
                    _field_or_none(reference_range),
                )
    return None


def _malformed_known_label(line: str, alias_index: dict[str, str]) -> str | None:
    """Find a known test label in a malformed row without guessing its fields."""
    normalized = _normalize(line)
    for alias, test_id in sorted(alias_index.items(), key=lambda pair: len(pair[0]), reverse=True):
        if re.search(rf"(?<!\w){re.escape(alias)}(?!\w)", normalized):
            return test_id
    return None


def _panel_from_pages(pages: list[ExtractedPage], catalog: dict) -> str | None:
    synonyms = {"lft": "liver_function", "liver_function_test": "liver_function"}
    for page in pages:
        for line in page.text.splitlines():
            match = PANEL_LINE.match(line)
            if match:
                label = _normalize(match.group(1)).replace(" ", "_")
                if label in catalog["panels"]:
                    return label
                return synonyms.get(label)
    return None


def parse_report_pages(
    pages: list[ExtractedPage], catalog: dict | None = None
) -> list[CandidateResult]:
    """Parse supported synthetic rows; unknown or malformed fields stay unknown."""
    catalog = catalog or _load_catalog()
    alias_index = _alias_index(catalog)
    candidates: list[CandidateResult] = []
    found_ids: set[str] = set()

    for page in pages:
        for line in page.text.splitlines():
            if PANEL_LINE.match(line):
                continue
            parsed = _parse_row(line)
            if parsed:
                label, value_text, unit, reference_range = parsed
                test_id = _match_test(label, alias_index)
                if test_id:
                    found_ids.add(test_id)
                candidates.append(
                    CandidateResult(
                        test_name=label,
                        test_id=test_id,
                        value_text=value_text,
                        unit=unit,
                        reference_range=reference_range,
                        source_page=page.page_number,
                        source_excerpt=line.strip(),
                    )
                )
                continue

            malformed_id = _malformed_known_label(line, alias_index)
            if malformed_id:
                found_ids.add(malformed_id)
                candidates.append(
                    CandidateResult(
                        test_name=line.strip(),
                        test_id=malformed_id,
                        source_page=page.page_number,
                        source_excerpt=line.strip(),
                    )
                )

    panel = _panel_from_pages(pages, catalog)
    if panel:
        for test_id in catalog["panels"][panel]:
            if test_id not in found_ids:
                # The panel identifies a required row that is absent; no values
                # or evidence are inferred for it.
                candidates.append(
                    CandidateResult(
                        test_name=catalog["tests"][test_id]["canonical_name"],
                        test_id=test_id,
                    )
                )
    return candidates


def extract_lab_report_offline(pdf_bytes: bytes) -> ExtractionReport:
    """Run PDF text extraction and deterministic parsing, without Gemini."""
    pages = extract_pdf_text(pdf_bytes)
    catalog = _load_catalog()
    candidates = parse_report_pages(pages, catalog)
    report = validate_candidates(candidates, pages)
    report.extraction_mode = "offline"
    if not candidates:
        report.report_issues.append(
            "Offline parser found no supported result rows; review the report format."
        )

    for result in report.results:
        if result.test_id and result.unit and not _unit_is_known(result.test_id, result.unit, catalog):
            result.flag = Flag.UNKNOWN
            result.issues.append("Unit is not a configured alias for this test.")
    return report
