"""Deterministic bilingual result explanations and conservative next steps."""

from __future__ import annotations

import json
import unicodedata
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field

from .critical_policy import apply_critical_policy
from .schemas import CriticalStatus, ExtractionReport, Flag, LabResult


ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "config" / "test_catalog.json"
GLOSSARY_PATH = ROOT / "config" / "explanation_glossary.json"
PACKAGE_PATH = ROOT / "config" / "follow_up_packages.json"


class ActionType(StrEnum):
    FOLLOW_UP_TEST_PACKAGE = "follow_up_test_package"
    DOCTOR_CONSULT = "doctor_consult"
    NO_ACTION = "no_action"


class NextStep(BaseModel):
    action_type: ActionType
    package_id: str | None = None
    reason_test_ids: list[str] = Field(default_factory=list)
    reason_en: str
    reason_hi: str
    urgency: str = "routine"
    urgent_message_en: str | None = None
    urgent_message_hi: str | None = None


class TestExplanation(BaseModel):
    test_id: str | None = None
    test_name_original: str
    value_text: str | None = None
    unit: str | None = None
    reference_range: str | None = None
    flag: Flag
    critical_status: CriticalStatus
    critical_source_name: str | None = None
    critical_source_url: str | None = None
    critical_age_group: str | None = None
    source_page: int | None = None
    source_excerpt: str | None = None
    glossary_source: str | None = None
    english: str
    hindi: str


class ExplanationBundle(BaseModel):
    panel: str
    tests: list[TestExplanation]
    next_step: NextStep
    critical_detection_configured: bool = True
    critical_detection_notice_en: str = (
        "A limited Labcorp-specific demonstration policy is configured for selected tests, exact units, and age groups. Other results remain UNCONFIGURED; this is not universal clinical guidance."
    )
    critical_detection_notice_hi: str = (
        "केवल कुछ चुने हुए परीक्षणों, सटीक इकाइयों और आयु-समूहों के लिए सीमित Labcorp-आधारित प्रदर्शन नीति है। अन्य परिणाम UNCONFIGURED रहते हैं; यह सार्वभौमिक चिकित्सकीय मार्गदर्शन नहीं है।"
    )
    disclaimer_en: str = "This explanation reports extracted values and printed ranges; it is not a diagnosis or treatment advice."
    disclaimer_hi: str = "यह विवरण निकाले गए मान और रिपोर्ट में छपी सीमाएँ बताता है; यह निदान या उपचार-सलाह नहीं है।"


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _normalize(value: str) -> str:
    value = unicodedata.normalize("NFKC", value)
    value = value.replace("Âµ", "µ").replace("Î¼", "µ").replace("μ", "µ")
    return " ".join(value.casefold().split())


def _panel_key(panel: str, catalog: dict) -> str:
    normalized = _normalize(panel).replace(" ", "_")
    synonyms = {
        "lipid": "lipid_profile",
        "lipid_panel": "lipid_profile",
        "thyroid": "thyroid_profile",
        "lft": "liver_function",
        "liver_function_test": "liver_function",
    }
    key = synonyms.get(normalized, normalized)
    if key not in catalog["panels"]:
        raise ValueError(f"Unsupported report panel: {panel}")
    return key


def _resolve_test_id(result: LabResult, catalog: dict) -> str | None:
    if result.test_id in catalog["tests"]:
        return result.test_id
    label = _normalize(result.test_name)
    for test_id, definition in catalog["tests"].items():
        aliases = [test_id, definition["canonical_name"], *definition["aliases"]]
        if label in {_normalize(alias) for alias in aliases}:
            return test_id
    return None


def _display(value: str | None, missing_en: str, missing_hi: str) -> tuple[str, str]:
    if value is None or not value.strip():
        return missing_en, missing_hi
    return value, value


def _flag_text(flag: Flag) -> tuple[str, str]:
    descriptions = {
        Flag.NORMAL: ("within the printed reference range", "रिपोर्ट में छपी संदर्भ सीमा के भीतर"),
        Flag.LOW: ("below the printed reference range", "रिपोर्ट में छपी संदर्भ सीमा से कम"),
        Flag.HIGH: ("above the printed reference range", "रिपोर्ट में छपी संदर्भ सीमा से अधिक"),
        Flag.UNKNOWN: (
            "unavailable or not interpretable from the available fields; it is not considered normal",
            "उपलब्ध फ़ील्ड से अनुपलब्ध या व्याख्या योग्य नहीं; इसे सामान्य नहीं माना गया है",
        ),
        Flag.CRITICAL_LOW: ("below a configured source-attributed critical limit", "स्रोत-आधारित कॉन्फ़िगर की गई गंभीर सीमा से कम"),
        Flag.CRITICAL_HIGH: ("above a configured source-attributed critical limit", "स्रोत-आधारित कॉन्फ़िगर की गई गंभीर सीमा से अधिक"),
    }
    return descriptions[flag]


def _make_test_explanation(
    result: LabResult,
    test_id: str | None,
    glossary: dict,
) -> TestExplanation:
    entry = glossary["tests"].get(test_id) if test_id else None
    if entry:
        name_en = entry["name_en"]
        name_hi = entry["name_hi"]
        measure_en = entry["measure_en"]
        measure_hi = entry["measure_hi"]
        source = entry.get("source")
    else:
        name_en = result.test_name
        name_hi = result.test_name
        measure_en = "the measurement described by this unrecognized report label"
        measure_hi = "इस अपरिचित रिपोर्ट लेबल में वर्णित माप"
        source = None

    value_text = result.value_text
    if value_text is None and result.value is not None:
        qualifier = result.value_qualifier or ""
        value_text = f"{qualifier}{result.value:g}"
    value_en, value_hi = _display(
        value_text,
        "unavailable in the report",
        "रिपोर्ट में उपलब्ध नहीं",
    )
    unit_en, unit_hi = _display(
        result.unit,
        "not provided in the report",
        "रिपोर्ट में उपलब्ध नहीं",
    )
    range_en, range_hi = _display(
        result.reference_range,
        "not provided in the report",
        "रिपोर्ट में उपलब्ध नहीं",
    )
    flag_description_en, flag_description_hi = _flag_text(result.flag)
    flag_label_hi = {
        Flag.NORMAL: "सामान्य",
        Flag.LOW: "कम",
        Flag.HIGH: "अधिक",
        Flag.UNKNOWN: "अनुपलब्ध/अव्याख्येय",
        Flag.CRITICAL_LOW: "गंभीर रूप से कम",
        Flag.CRITICAL_HIGH: "गंभीर रूप से अधिक",
    }[result.flag]

    english = (
        f"{name_en} measures {measure_en}. Reported value: {value_en}; unit: {unit_en}; "
        f"reference range printed on this report: {range_en}; validated flag: {result.flag.value} "
        f"({flag_description_en}). Critical status: {result.critical_status.value}."
    )
    hindi = (
        f"{name_hi}: {measure_hi}। रिपोर्ट में दर्ज मान: {value_hi}; इकाई: {unit_hi}; "
        f"रिपोर्ट में छपी संदर्भ सीमा: {range_hi}; सत्यापित फ़्लैग: {result.flag.value} "
        f"({flag_label_hi}; {flag_description_hi})। गंभीर स्थिति: {result.critical_status.value}।"
    )
    return TestExplanation(
        test_id=test_id,
        test_name_original=result.test_name,
        value_text=result.value_text,
        unit=result.unit,
        reference_range=result.reference_range,
        flag=result.flag,
        critical_status=result.critical_status,
        critical_source_name=result.critical_source_name,
        critical_source_url=result.critical_source_url,
        critical_age_group=result.critical_age_group,
        source_page=result.source_page,
        source_excerpt=result.source_excerpt,
        glossary_source=source,
        english=english,
        hindi=hindi,
    )


def _package_mapping(package_config: dict) -> dict[tuple[str, str], str]:
    mapping: dict[tuple[str, str], str] = {}
    for item in package_config["mappings"]:
        for flag in item["flags"]:
            mapping[(item["test_id"], flag)] = item["package_id"]
    return mapping


def recommend_next_step(
    report: ExtractionReport, panel: str, *, age_group: str | None = None
) -> NextStep:
    """Choose one of exactly three demo actions using conservative Python rules."""
    report = apply_critical_policy(report, age_group=age_group)
    catalog = _read_json(CATALOG_PATH)
    package_config = _read_json(PACKAGE_PATH)
    panel_key = _panel_key(panel, catalog)
    required_ids = catalog["panels"][panel_key]
    mapping = _package_mapping(package_config)

    resolved: list[tuple[LabResult, str | None]] = [
        (result, _resolve_test_id(result, catalog)) for result in report.results
    ]
    critical_results = [
        (result, test_id) for result, test_id in resolved
        if result.critical_status in (CriticalStatus.CRITICAL_LOW, CriticalStatus.CRITICAL_HIGH)
    ]
    if critical_results:
        critical_ids = [test_id or result.test_name for result, test_id in critical_results]
        critical_details = "; ".join(
            f"{result.test_name} {result.value_text} {result.unit} crossed "
            f"{result.critical_operator}{result.critical_threshold} {result.unit} "
            f"({result.critical_source_name}; age group: {result.critical_age_group})"
            for result, _ in critical_results
        )
        return NextStep(
            action_type=ActionType.DOCTOR_CONSULT,
            reason_test_ids=critical_ids,
            reason_en=f"A verified result crosses a configured, source-attributed critical limit: {critical_details}. Seek urgent medical review now; this demonstration rule does not replace local laboratory instructions or emergency services.",
            reason_hi=f"स्रोत-आधारित कॉन्फ़िगर की गई गंभीर सीमा पार हुई है: {critical_details}। अभी तुरंत चिकित्सकीय समीक्षा लें; यह प्रदर्शन नियम स्थानीय प्रयोगशाला निर्देशों या आपातकालीन सेवाओं का विकल्प नहीं है।",
            urgency="urgent",
            urgent_message_en=f"URGENT: {critical_details}. Contact a doctor or the responsible care team immediately.",
            urgent_message_hi=f"तत्काल: {critical_details}। तुरंत डॉक्टर या देखभाल टीम से संपर्क करें।",
        )
    by_id: dict[str, list[LabResult]] = {}
    for result, test_id in resolved:
        if test_id:
            by_id.setdefault(test_id, []).append(result)

    missing_ids = [test_id for test_id in required_ids if test_id not in by_id]
    duplicate_ids = [test_id for test_id, values in by_id.items() if len(values) > 1]
    unknown_rows = [
        result.test_id or result.test_name
        for result, test_id in resolved
        if test_id is None
    ]
    problematic_ids: list[str] = list(missing_ids)
    problematic_ids.extend(duplicate_ids)
    problematic_ids.extend(unknown_rows)

    has_report_issues = bool(report.report_issues)
    for result, test_id in resolved:
        if result.flag == Flag.UNKNOWN:
            problematic_ids.append(test_id or result.test_id or result.test_name)
        else:
            # Any non-UNKNOWN classification is only actionable as known when
            # its value, unit, range, and source evidence are all present.
            if not all((result.value_text, result.value is not None, result.unit, result.reference_range,
                        result.source_page is not None, result.source_excerpt)) or result.issues:
                problematic_ids.append(test_id or result.test_name)

    if problematic_ids or has_report_issues:
        reasons = list(dict.fromkeys(problematic_ids))
        return NextStep(
            action_type=ActionType.DOCTOR_CONSULT,
            reason_test_ids=reasons,
            reason_en="One or more required results are missing, uninterpretable, unrecognized, duplicated, or otherwise unresolved. Consult a doctor to review the report.",
            reason_hi="एक या अधिक आवश्यक परिणाम अनुपलब्ध, अव्याख्येय, अपरिचित, दोहराए गए या अनसुलझे हैं। रिपोर्ट की समीक्षा के लिए डॉक्टर से परामर्श करें।",
        )

    abnormal_results = [
        (result, test_id)
        for result, test_id in resolved
        if result.flag in (Flag.LOW, Flag.HIGH)
    ]
    if abnormal_results:
        package_ids = {
            mapping.get((test_id, result.flag.value))
            for result, test_id in abnormal_results
        }
        if None in package_ids or len(package_ids) != 1:
            reasons = [test_id or result.test_name for result, test_id in abnormal_results]
            return NextStep(
                action_type=ActionType.DOCTOR_CONSULT,
                reason_test_ids=reasons,
                reason_en="An abnormal result has no configured demo package, or the abnormal results map to different packages. Consult a doctor to review them.",
                reason_hi="किसी असामान्य परिणाम के लिए डेमो पैकेज कॉन्फ़िगर नहीं है, या असामान्य परिणाम अलग-अलग पैकेजों में जाते हैं। समीक्षा के लिए डॉक्टर से परामर्श करें।",
            )
        package_id = next(iter(package_ids))
        return NextStep(
            action_type=ActionType.FOLLOW_UP_TEST_PACKAGE,
            package_id=package_id,
            reason_test_ids=[test_id for _, test_id in abnormal_results if test_id],
            reason_en="The abnormal result flags map to one configured demo follow-up package. This package ID is a software routing label, not a clinical order.",
            reason_hi="असामान्य परिणामों के फ़्लैग एक कॉन्फ़िगर किए गए डेमो फ़ॉलो-अप पैकेज से मेल खाते हैं। यह पैकेज आईडी केवल सॉफ़्टवेयर रूटिंग लेबल है, चिकित्सकीय आदेश नहीं।",
        )

    # The earlier checks ensure every required result and every reported row
    # is recognized, evidence-backed, and fully known before no_action is used.
    return NextStep(
        action_type=ActionType.NO_ACTION,
        reason_en="All required and recognized reported results are present, supported, and NORMAL against the ranges printed on this report. No demo package is selected.",
        reason_hi="सभी आवश्यक और पहचाने गए रिपोर्ट परिणाम उपलब्ध, स्रोत से समर्थित और रिपोर्ट में छपी सीमाओं के अनुसार सामान्य हैं। कोई डेमो पैकेज नहीं चुना गया है।",
    )


def generate_explanations(
    report: ExtractionReport, panel: str, *, age_group: str | None = None
) -> ExplanationBundle:
    """Render the validated extraction output in English and Hindi."""
    catalog = _read_json(CATALOG_PATH)
    glossary = _read_json(GLOSSARY_PATH)
    panel_key = _panel_key(panel, catalog)
    report = apply_critical_policy(report, age_group=age_group)

    results: list[tuple[LabResult, str | None]] = []
    seen_required: set[str] = set()
    for result in report.results:
        test_id = _resolve_test_id(result, catalog)
        results.append((result, test_id))
        if test_id in catalog["panels"][panel_key]:
            seen_required.add(test_id)

    for test_id in catalog["panels"][panel_key]:
        if test_id not in seen_required:
            results.append((
                LabResult(
                    test_name=catalog["tests"][test_id]["canonical_name"],
                    test_id=test_id,
                    flag=Flag.UNKNOWN,
                    issues=["Required result missing from extraction."],
                ),
                test_id,
            ))

    next_step = recommend_next_step(report, panel_key, age_group=age_group)
    test_explanations = [
        _make_test_explanation(result, test_id, glossary)
        for result, test_id in results
    ]
    return ExplanationBundle(
        panel=panel_key,
        tests=test_explanations,
        next_step=next_step,
        critical_detection_configured=True,
    )
