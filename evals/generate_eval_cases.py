"""Create the separate, fixed 30-report evaluation PDF set.

This generator writes PDFs only. It does not read or create evaluation labels.
The independently prepared labels live in evals/ground_truth.json.
"""

from pathlib import Path

import pymupdf


ROOT = Path(__file__).resolve().parents[1]
CASES_DIR = ROOT / "evals" / "cases"

# Only report text is kept here. Scoring labels are maintained separately.
ROWS = [
    ("EVAL-001", "Hb | 14.0 | g/dL | 12.0 - 16.0"),
    ("EVAL-002", "WBC | 12000 | cells/uL | 4500 - 11000"),
    ("EVAL-003", "Hemoglobin | 14.0 | [unit not printed] | 12.0 - 16.0"),
    ("EVAL-004", "RBC result twelve million/uL range 4.2 - 5.4"),
    ("EVAL-005", "PLT | 250 | bananas/L | 150 - 400"),
    ("EVAL-006", "Hb | 14.0 | g/dL | 12.0 - 16.0 or 13.0 - 17.0"),
    ("EVAL-007", "TG | 120 | mg/dL | < 150"),
    ("EVAL-008", "LDL-C | 130 | mg / dL | < 100"),
    ("EVAL-009", "HDL | 44 | mg/dL | [range not printed]"),
    ("EVAL-010", "TC - not-a-number mg/dL"),
    ("EVAL-011", "LDL | 90 | mmol/dL | < 100"),
    ("EVAL-012", "TG | 120 | mg/dL | <150 if fasting; <=200 otherwise"),
    ("EVAL-013", "A1C | 5.2 | % | 4.0 - 5.6"),
    ("EVAL-014", "HbA1c | 5.9 | percent | 4.0 - 5.6"),
    ("EVAL-015", "HbA1c | [not printed] | % | 4.0 - 5.6"),
    ("EVAL-016", "Glycated Hemoglobin: five point two percent"),
    ("EVAL-017", "A1C | 5.2 | fraction | 4.0 - 5.6"),
    ("EVAL-018", "HbA1c | 5.2 | % | 4.0 - 5.6 (method-specific)"),
    ("EVAL-019", "TSH | 2.0 | uIU/mL | 0.4 - 4.8"),
    ("EVAL-020", "Free T4 | 2.0 | ng/dL | 0.9 - 1.7"),
    ("EVAL-021", "T3 | 110 | [unit not printed] | 78 - 158"),
    ("EVAL-022", "Thyrotropin approx two"),
    ("EVAL-023", "TSH | 2.0 | ug/dL | 0.4 - 4.8"),
    ("EVAL-024", "FT4 | 1.1 | ng/dL | age-specific range; see note"),
    ("EVAL-025", "ALT | 20 | U/L | 4 - 36"),
    ("EVAL-026", "SGPT | 50 | IU/L | 4 - 36"),
    ("EVAL-027", "AST | [not printed] | U/L | 8 - 33"),
    ("EVAL-028", "Alk Phos maybe eighty"),
    ("EVAL-029", "TBIL | 0.7 | mmol/L | 0.1 - 1.2"),
    ("EVAL-030", "AST | 25 | U/L | 8 - 33 or 10 - 40 depending method"),
]


def generate() -> int:
    CASES_DIR.mkdir(parents=True, exist_ok=True)
    for case_id, row in ROWS:
        document = pymupdf.open()
        page = document.new_page(width=612, height=792)
        page.insert_text((48, 48), "HEYDOC SYNTHETIC EVALUATION REPORT", fontsize=12)
        page.insert_text((48, 72), "Fictional data for software testing only.", fontsize=9)
        page.insert_text((48, 125), row, fontsize=10)
        document.save(CASES_DIR / f"{case_id.lower()}.pdf")
        document.close()
    return len(ROWS)


if __name__ == "__main__":
    print(f"Generated {generate()} evaluation PDFs in {CASES_DIR}")
