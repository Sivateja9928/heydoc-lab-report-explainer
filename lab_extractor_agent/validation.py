"""Verify extracted evidence and calculate range flags without an LLM."""

import re
import unicodedata

from .pdf_text import ExtractedPage
from .schemas import CandidateResult, ExtractionReport, Flag, LabResult


NUMBER = r"\d+(?:\.\d+)?"
VALUE_RE = re.compile(rf"^\s*(<=|>=|<|>)?\s*({NUMBER})\s*$")
RANGE_RE = re.compile(rf"^\s*({NUMBER})?\s*(-|–|to)\s*({NUMBER})?\s*$", re.I)
ONE_SIDED_RE = re.compile(rf"^\s*(<=|>=|<|>)\s*({NUMBER})\s*$")


def _normalize(text: str) -> str:
    """Normalize typography and whitespace for a conservative evidence check."""
    text = unicodedata.normalize("NFKC", text).replace("Âµ", "µ").replace("Î¼", "µ")
    return " ".join(text.casefold().split())


def _parse_range(text: str) -> tuple[float | None, bool | None, float | None, bool | None]:
    one_sided = ONE_SIDED_RE.match(text)
    if one_sided:
        operator, raw_bound = one_sided.groups()
        bound = float(raw_bound)
        if operator in (">", ">="):
            return bound, operator == ">=", None, None
        return None, None, bound, operator == "<="

    match = RANGE_RE.match(text)
    if not match:
        return None, None, None, None
    lower, upper = match.group(1), match.group(3)
    if lower is None and upper is None:
        return None, None, None, None
    return (
        float(lower) if lower else None,
        True if lower else None,
        float(upper) if upper else None,
        True if upper else None,
    )


def _calculate_flag(
    value: float,
    qualifier: str | None,
    lower: float | None,
    upper: float | None,
    lower_inclusive: bool | None,
    upper_inclusive: bool | None,
) -> Flag:
    """Flag only when the full possible value interval fits one category."""
    if lower is None and upper is None:
        return Flag.UNKNOWN

    # The result qualifier defines an interval; a boundary overlap is UNKNOWN.
    if qualifier in ("<", "<="):
        wholly_below = lower is not None and (
            value < lower
            or (value == lower and (qualifier == "<" or lower_inclusive is False))
        )
        if wholly_below:
            return Flag.LOW
        if upper is not None and value > upper:
            return Flag.UNKNOWN
        return Flag.UNKNOWN
    if qualifier in (">", ">="):
        wholly_above = upper is not None and (
            value > upper
            or (value == upper and (qualifier == ">" or upper_inclusive is False))
        )
        if wholly_above:
            return Flag.HIGH
        if lower is not None and value < lower:
            return Flag.UNKNOWN
        return Flag.UNKNOWN

    if lower is not None and (
        value < lower or (value == lower and lower_inclusive is False)
    ):
        return Flag.LOW
    if upper is not None and (
        value > upper or (value == upper and upper_inclusive is False)
    ):
        return Flag.HIGH
    return Flag.NORMAL


def validate_candidates(
    candidates: list[CandidateResult], pages: list[ExtractedPage]
) -> ExtractionReport:
    """Check fields/evidence and assign ordinary printed-range flags in Python."""
    page_text = {page.page_number: _normalize(page.text) for page in pages}
    validated: list[LabResult] = []

    for candidate in candidates:
        issues: list[str] = []
        value: float | None = None
        qualifier: str | None = None
        lower = upper = None
        lower_inclusive = upper_inclusive = None

        if not candidate.value_text:
            issues.append("Missing result value.")
        else:
            match = VALUE_RE.match(candidate.value_text)
            if match:
                qualifier, raw_value = match.groups()
                value = float(raw_value)
            else:
                issues.append("Result value is missing or not a supported number.")

        if not candidate.unit or not candidate.unit.strip():
            issues.append("Missing unit.")
        if not candidate.reference_range or not candidate.reference_range.strip():
            issues.append("Missing reference range.")
        else:
            lower, lower_inclusive, upper, upper_inclusive = _parse_range(
                candidate.reference_range
            )
            if lower is None and upper is None:
                issues.append("Reference range is ambiguous or unsupported.")

        excerpt = candidate.source_excerpt
        source_page_text = page_text.get(candidate.source_page or -1)
        if not excerpt or source_page_text is None:
            issues.append("Source page or evidence excerpt is missing.")
        elif _normalize(excerpt) not in source_page_text:
            issues.append("Evidence excerpt could not be verified on the cited page.")
        else:
            normalized_excerpt = _normalize(excerpt)
            if candidate.value_text and _normalize(candidate.value_text) not in normalized_excerpt:
                issues.append("Evidence excerpt does not contain the extracted value.")
            if candidate.unit and _normalize(candidate.unit) not in normalized_excerpt:
                issues.append("Evidence excerpt does not contain the extracted unit.")

        flag = Flag.UNKNOWN
        if not issues and value is not None:
            flag = _calculate_flag(
                value,
                qualifier,
                lower,
                upper,
                lower_inclusive,
                upper_inclusive,
            )
            if flag == Flag.UNKNOWN:
                issues.append("Value cannot be classified against the printed range.")

        validated.append(
            LabResult(
                test_name=candidate.test_name,
                test_id=candidate.test_id,
                value_text=candidate.value_text,
                value=value,
                value_qualifier=qualifier,
                unit=candidate.unit,
                reference_range=candidate.reference_range,
                range_lower=lower,
                range_lower_inclusive=lower_inclusive,
                range_upper=upper,
                range_upper_inclusive=upper_inclusive,
                flag=flag,
                source_page=candidate.source_page,
                source_excerpt=candidate.source_excerpt,
                issues=issues,
            )
        )

    if not validated:
        return ExtractionReport(report_issues=["No lab results were extracted."])
    return ExtractionReport(results=validated)
