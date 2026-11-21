"""Pydantic models used at the extraction and validation boundaries."""

from enum import StrEnum
from typing import Optional

from pydantic import BaseModel, Field


class Flag(StrEnum):
    """A flag calculated by Python from a report's own reference range."""

    NORMAL = "NORMAL"
    LOW = "LOW"
    HIGH = "HIGH"
    UNKNOWN = "UNKNOWN"
    CRITICAL_LOW = "CRITICAL_LOW"
    CRITICAL_HIGH = "CRITICAL_HIGH"


class CriticalStatus(StrEnum):
    """Outcome of an explicitly configured, source-attributed policy."""

    UNCONFIGURED = "UNCONFIGURED"
    NOT_CONFIGURED = "UNCONFIGURED"  # Backwards-compatible enum alias.
    NOT_CRITICAL = "NOT_CRITICAL"
    INDETERMINATE = "INDETERMINATE"
    CRITICAL_LOW = "CRITICAL_LOW"
    CRITICAL_HIGH = "CRITICAL_HIGH"


class CandidateResult(BaseModel):
    """Fields the model may read from a report; no medical interpretation."""

    test_name: str = Field(description="Test label exactly as printed")
    test_id: Optional[str] = Field(
        default=None, description="Canonical test ID when a catalogue alias matches"
    )
    value_text: Optional[str] = Field(
        default=None, description="Result exactly as printed, including qualifiers"
    )
    unit: Optional[str] = Field(default=None, description="Unit exactly as printed")
    reference_range: Optional[str] = Field(
        default=None, description="Reference range exactly as printed"
    )
    source_page: Optional[int] = Field(
        default=None, description="One-based page containing this result"
    )
    source_excerpt: Optional[str] = Field(
        default=None, description="Short verbatim excerpt supporting this result"
    )


class CandidateReport(BaseModel):
    """Structured response requested from Gemini."""

    results: list[CandidateResult] = Field(default_factory=list)


class LabResult(BaseModel):
    """A candidate result checked and flagged by deterministic Python code."""

    test_name: str
    test_id: Optional[str] = None
    value_text: Optional[str] = None
    value: Optional[float] = None
    value_qualifier: Optional[str] = None
    unit: Optional[str] = None
    reference_range: Optional[str] = None
    range_lower: Optional[float] = None
    range_lower_inclusive: Optional[bool] = None
    range_upper: Optional[float] = None
    range_upper_inclusive: Optional[bool] = None
    flag: Flag = Flag.UNKNOWN
    critical_status: CriticalStatus = CriticalStatus.UNCONFIGURED
    ordinary_flag: Optional[Flag] = None
    critical_source_name: Optional[str] = None
    critical_source_url: Optional[str] = None
    critical_age_group: Optional[str] = None
    critical_threshold: Optional[float] = None
    critical_operator: Optional[str] = None
    source_page: Optional[int] = None
    source_excerpt: Optional[str] = None
    issues: list[str] = Field(default_factory=list)


class ExtractionReport(BaseModel):
    """Final output from the initial extraction pipeline."""

    results: list[LabResult] = Field(default_factory=list)
    report_issues: list[str] = Field(default_factory=list)
    extraction_mode: str = "gemini"
