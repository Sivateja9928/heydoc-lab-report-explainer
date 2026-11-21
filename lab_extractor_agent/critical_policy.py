"""Apply explicitly configured critical limits without inferring from range flags."""

from __future__ import annotations

import json
import unicodedata
from pathlib import Path

from .schemas import CriticalStatus, ExtractionReport, Flag, LabResult


POLICY_PATH = Path(__file__).resolve().parents[1] / "config" / "critical_thresholds.json"
CATALOG_PATH = POLICY_PATH.parent / "test_catalog.json"
VALID_OPERATORS = {"<", "<=", ">", ">="}


def _read_policy() -> dict:
    return json.loads(POLICY_PATH.read_text(encoding="utf-8"))


def _same_unit(first: str | None, second: str | None) -> bool:
    """Compare written unit spellings; do not convert or equate unit scales."""
    if not first or not second:
        return False
    normalize = lambda value: unicodedata.normalize("NFKC", value).casefold().strip()
    return normalize(first) == normalize(second)


def _matches(value: float, threshold: float | None, operator: str | None) -> bool:
    if threshold is None or operator not in VALID_OPERATORS:
        return False
    return {
        "<": value < threshold,
        "<=": value <= threshold,
        ">": value > threshold,
        ">=": value >= threshold,
    }[operator]


def _evidence_supports_value(result: LabResult) -> bool:
    """Require the critical-comparison inputs to be present in cited evidence."""
    if result.value is None or not result.value_text or not result.unit:
        return False
    # A qualified value such as "< 7" does not identify an exact measurement.
    if result.value_qualifier is not None:
        return False
    if result.source_page is None or not result.source_excerpt:
        return False
    if any(
        "evidence" in issue.casefold() or "source page" in issue.casefold()
        for issue in result.issues
    ):
        return False
    normalize = lambda value: " ".join(unicodedata.normalize("NFKC", value).casefold().split())
    excerpt = normalize(result.source_excerpt)
    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    definition = catalog["tests"].get(result.test_id or "")
    if definition is None:
        return False
    labels = [result.test_id, definition["canonical_name"], *definition["aliases"]]
    return (
        normalize(result.value_text) in excerpt
        and normalize(result.unit) in excerpt
        and any(normalize(label) in excerpt for label in labels)
    )


def apply_critical_policy(
    report: ExtractionReport, *, age_group: str | None = None
) -> ExtractionReport:
    """Return a copy with source-matched critical status; unmatched rows stay UNCONFIGURED.

    `age_group` must exactly match a category recorded from the source table. No age
    is inferred from report contents, and ordinary HIGH/LOW flags are never used.
    """
    policy = _read_policy()
    updated: list[LabResult] = []
    for result in report.results:
        ordinary_flag = result.ordinary_flag or result.flag
        updated_result = result.model_copy(update={
            "flag": ordinary_flag,
            "ordinary_flag": ordinary_flag,
            "critical_status": CriticalStatus.UNCONFIGURED,
            "critical_source_name": None,
            "critical_source_url": None,
            "critical_age_group": None,
            "critical_threshold": None,
            "critical_operator": None,
        })

        matched = next((item for item in policy["thresholds"]
                        if item["test_id"] == result.test_id
                        and _same_unit(item["unit"], result.unit)
                        and age_group == item["age_group"]), None)
        if matched is None:
            updated.append(updated_result)
            continue

        base_metadata = {
            "critical_source_name": policy["source_name"],
            "critical_source_url": policy["source_url"],
            "critical_age_group": matched["age_group"],
        }
        # Missing or ambiguous comparison evidence cannot establish criticality.
        if not _evidence_supports_value(result):
            updated.append(updated_result.model_copy(update={
                **base_metadata, "critical_status": CriticalStatus.INDETERMINATE,
            }))
            continue

        critical_low = _matches(result.value, matched["low_threshold"], matched["low_operator"])
        critical_high = _matches(result.value, matched["high_threshold"], matched["high_operator"])
        if critical_low:
            status, flag = CriticalStatus.CRITICAL_LOW, Flag.CRITICAL_LOW
            threshold, operator = matched["low_threshold"], matched["low_operator"]
        elif critical_high:
            status, flag = CriticalStatus.CRITICAL_HIGH, Flag.CRITICAL_HIGH
            threshold, operator = matched["high_threshold"], matched["high_operator"]
        else:
            status, flag = CriticalStatus.NOT_CRITICAL, ordinary_flag
            threshold, operator = None, None

        updated.append(updated_result.model_copy(update={
            **base_metadata,
            "critical_status": status,
            "flag": flag,
            "critical_threshold": threshold,
            "critical_operator": operator,
        }))

    return report.model_copy(update={"results": updated})
