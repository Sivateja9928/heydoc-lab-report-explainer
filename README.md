# HeyDoc Lab Report Explainer

HeyDoc is an educational assignment that extracts values from synthetic laboratory PDF reports, checks them against the ranges printed in each report, and renders deterministic English and Hindi explanations with a conservative next step. It is a software demonstration, not a diagnostic product.

## Architecture

`PDF bytes → PyMuPDF selectable-text extraction → Gemini ADK candidate extraction or explicitly selected offline parser → Pydantic/evidence and printed-range validation in Python → source-attributed critical policy → deterministic bilingual explanations → next-step recommendation`

Gemini supplies candidate fields only. Python checks evidence and ordinary flags. The critical policy is a separate, limited Labcorp-specific configuration; it requires a matching test ID, written unit, and caller-supplied age category. An ordinary `HIGH` or `LOW` flag never implies a critical result. The available actions are `follow_up_test_package`, `doctor_consult`, and `no_action`.

## Windows PowerShell setup

From the project root, create a virtual environment and install the pinned project dependencies:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

The checked-in `.env.example` contains placeholders only. The application reads environment variables directly; it does not automatically load `.env` files. For Gemini, set `GOOGLE_API_KEY` in Windows **Edit environment variables for your account** and open a new PowerShell window. For a temporary current-window setting without echoing the key or placing it in command history:

```powershell
$secureKey = Read-Host "Enter GOOGLE_API_KEY" -AsSecureString
$credential = [pscredential]::new("GOOGLE_API_KEY", $secureKey)
$env:GOOGLE_API_KEY = $credential.GetNetworkCredential().Password
Remove-Variable secureKey, credential
```

Never put a real key in `.env.example`, source code, or a committed file. `GEMINI_MODEL` is optional; the current agent default is `gemini-3.5-flash`.

## Run extraction

To open the ADK development UI from the project root:

```powershell
.\.venv\Scripts\adk.exe web lab_extractor_agent
```

The UI runs locally for development. The PDF pipeline's Python entry point accepts PDF bytes and defaults to Gemini. Set the mode explicitly before invoking it:

```powershell
$env:HEYDOC_EXTRACTION_MODE = "gemini"  # Requires GOOGLE_API_KEY.
```

To select the deterministic offline parser instead:

```powershell
$env:HEYDOC_EXTRACTION_MODE = "offline"
```

Both modes use `extract_lab_report(pdf_bytes)` from `lab_extractor_agent.extraction`. Gemini errors do not trigger an automatic fallback; offline results are labeled `extraction_mode: "offline"`. The offline parser supports the project's selectable-text synthetic layouts and does not use evaluation labels.

With either mode selected above, run the PDF pipeline on a bundled synthetic report:

```powershell
@'
import asyncio
from pathlib import Path
from lab_extractor_agent.extraction import extract_lab_report

pdf = Path("synthetic_dataset/reports/demo_cbc_01.pdf")
report = asyncio.run(extract_lab_report(pdf.read_bytes()))
print(report.model_dump_json(indent=2))
'@ | .\.venv\Scripts\python.exe -
```

The Gemini mode requires a configured API key. The offline mode above uses no Gemini request.

## Tests and offline evaluation

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe evals\run_evaluation.py
```

The evaluation reads the 30 PDFs, completes extraction, and only then loads the separate ground-truth labels for scoring. The latest measured run produced:

| Measure | Result |
|---|---:|
| Evaluation cases | 30 reports |
| Test identification | 30/30 (100%) |
| Value text and numeric value | 30/30 each (100%) |
| Unit, printed range, flag, evidence grounding | 30/30 each (100%) |
| Expected UNKNOWN handling | 20/20 (100%); unexpected UNKNOWN among classifiable cases: 0/10 |
| Missing-field handling | 5/5 (100%) |
| Failed cases | 0/30 |
| Offline latency | Mean 2.016 ms, median 1.373 ms, p95 6.418 ms; 30 reports |

The full case table and per-report latency are in [the offline evaluation report](evals/results/offline_evaluation.md). These measurements are local offline processing only. Gemini/API spend and total project cost were not measured or verified; no total project cost is claimed.

## Limitations

- All evaluation reports are synthetic. No real patient data was used, and the project has no clinical validation.
- Offline parsing is limited to supported selectable-text layouts. Scanned PDFs, OCR, and arbitrary laboratory tables are unsupported.
- Printed ranges are report-specific; the illustrative catalogue ranges are not universal standards.
- Critical limits are a demonstration subset of one laboratory's policy, not universal clinical guidance. The source-specific age groups are not present in the synthetic reports, so those cases remain `UNCONFIGURED`. Unit mismatches and unsupported tests also remain `UNCONFIGURED`; no unit conversions are performed.
- Gemini requests returned `503 UNAVAILABLE` during development. Successful live Gemini extraction has not been verified. The reproducible demonstrated path is offline extraction.
- Evaluation accuracy is for these synthetic software fixtures only and does not establish medical or clinical performance.
