# PLAN.md — HeyDoc AI Lab Report Explainer

**Assignment:** AI Engineer take-home  
**Start:** 20 November 2026, 7:30 PM IST  
**Deadline:** 21 November 2026, 7:30 PM IST  
**Status:** Planning document; no implementation results are claimed.

## 1. Problem and scope

People often receive laboratory reports as PDFs but do not know what the values mean or which results need attention. I will build a small application that reads a synthetic lab report, extracts its results, explains them in English and Hindi, and suggests one permitted next step. It will explain the reported values; it will not diagnose a disease or recommend treatment.

The main user is a patient reading a report. The lab/product team also needs traceable output so that the extraction, flags and recommendations can be checked.

I will create:

- **15 demo reports:** three each for CBC, lipid profile, HbA1c, thyroid profile and LFT.
- **30 separate evaluation PDFs:** additional synthetic cases, so the evaluation is not limited to the demo reports.
- Schema-validated JSON with test name, value, unit, printed reference range, flag and source evidence.
- English and Hindi explanations linked to the extracted results.
- Critical-value handling and one next step from the brief's fixed list: follow-up test package, doctor consultation or no action.
- A 30-case evaluation script and results table, latency/cost measurements, README, `AI_USAGE.md` and a 3–5 minute walkthrough. I will deploy the demo if time allows; otherwise I will provide local run steps.

Only synthetic data will be used. The first version will accept selectable-text PDFs. Scanned/image-only reports, OCR, handwritten reports, real patient data, diagnosis, treatment advice, EHR integration and persistent report storage are out of scope. Missing or ambiguous fields will be marked `UNKNOWN`, not guessed.

## 2. Architecture

```text
PDF upload
   |
FastAPI validates the file
   |
PyMuPDF extracts page text
   |
ADK extraction agent returns candidate test results
   |
Python verifies source evidence and validates the schema
   |
Python normalizes test names/units and calculates flags
   |
Python applies critical-value and next-step rules
   |
Reviewed English/Hindi templates render the explanation
   |
Structured response + patient-friendly report
```

I will use **PyMuPDF** because the generated PDFs will contain selectable text. This avoids an OCR or vision-model call for every page and keeps the first version simpler and cheaper. Before generating all fixtures, I will inspect the text from the first PDF and test the source-evidence check. If table cells are split across lines, I will improve row reconstruction or adjust the PDF layout; I will not remove the evidence check just to make a fixture pass.

I will use **Google ADK 2.x** for the extraction step. The LLM will identify test names, values, units and printed ranges. Python will handle validation, flagging, critical checks and next-step selection. I will not use a second LLM to write patient-facing explanations: reviewed bilingual templates and a glossary are easier to test and reduce the risk of unsupported medical claims.

Core logic will stay in ordinary Python functions; ADK nodes will call those functions rather than contain the business rules. First, I will verify a minimal ADK agent with structured output. If the ADK graph workflow is not working reliably within 90 minutes, I will use an ADK agent with plain Python orchestration and document the reason.

## 3. Data model and rules

Each result will retain its original label, value text and unit alongside normalized fields. This lets me compare what the model extracted with what the PDF actually contains. Pydantic will validate the structure.

```json
{
  "test_id": "hemoglobin",
  "test_name_original": "Hb",
  "value": 10.2,
  "value_qualifier": null,
  "unit_original": "g / dL",
  "unit_canonical": "g/dL",
  "reference_range": {
    "raw_text": "12.0 - 16.0",
    "lower_bound": 12.0,
    "lower_inclusive": true,
    "upper_bound": 16.0,
    "upper_inclusive": true
  },
  "flag": "LOW",
  "source_page": 1,
  "source_excerpt": "Hemoglobin 10.2 g / dL 12.0 - 16.0"
}
```

### Test catalogue

`config/test_catalog.yaml` will map common labels to canonical IDs (for example, `Hb` and `Haemoglobin` to `hemoglobin`, and `SGPT` to `alt`) and list accepted unit aliases. The generated fixtures will use these required tests:

| Report | Required test IDs |
|---|---|
| CBC | `hemoglobin`, `rbc`, `wbc`, `platelets` |
| Lipid profile | `total_cholesterol`, `hdl`, `ldl`, `triglycerides` |
| HbA1c | `hba1c` |
| Thyroid | `tsh`, `t3`, `t4` |
| LFT | `alt`, `ast`, `alp`, `total_bilirubin` |

These lists define my synthetic fixtures, not every real laboratory panel. A missing required test becomes `UNKNOWN` and leads to doctor consultation. Recognized extra tests will still be extracted. An unrecognized row will be preserved with its original label and source excerpt, but will have no canonical ID and an `UNKNOWN` flag; it will not be silently dropped.

### Values, units and ranges

- Store numeric values and an optional qualifier (`<`, `<=`, `>` or `>=`) separately. For example, `<0.1` is stored as value `0.1` with qualifier `<`.
- Keep the printed unit. Set a canonical unit only for a known catalogue alias; do not guess missing units or perform an unconfigured conversion.
- Reference-range bounds may be `null` for one-sided limits. Preserve the printed text and whether each bound is inclusive.
- Use the range printed on the report for ordinary `LOW`, `HIGH` and `NORMAL` flags. If the range is missing or ambiguous, the flag is `UNKNOWN`.
- Fixtures will use single intervals or one-sided limits. Multi-tier and unsupported sex-specific ranges will be marked `UNKNOWN` in this version.
- Treat qualified values as intervals. Assign a flag only when the entire possible-value interval fits one category. If it overlaps a boundary, return `UNKNOWN`.
- Apply inclusive/exclusive boundaries as printed and test equality at both bounds.
- Normalize known aliases such as `cells/µL`, `cells/μL` and `cells/uL` through explicit catalogue entries. Text normalization is not a substitute for unit conversion.

### Source evidence and prompt injection

The extraction agent must return a page number and source excerpt for each result. The verifier will normalize the excerpt and page text with Unicode NFKC, map `µ` and `μ` to the same comparison form, and collapse whitespace before matching. It will also check that the excerpt contains the extracted value and original unit. If the value or unit cannot be verified, mark the field `UNKNOWN` and route it for review.

PDF content is untrusted data, not instructions. The extraction prompt will tell the model to treat report text as data. Evaluation PDFs will include text that asks the model to alter a result, ignore instructions or reveal prompts; the extracted values must still match the report.

### Flags and critical results

Allowed flags are `NORMAL`, `LOW`, `HIGH`, `CRITICAL_LOW`, `CRITICAL_HIGH` and `UNKNOWN`.

1. Verify the test identity, source evidence, value and unit.
2. Check critical thresholds independently of the printed reference range. A critical comparison requires a verified value, a known compatible unit and a configured threshold.
3. If the entire possible-value interval is beyond a configured critical threshold, set `CRITICAL_LOW` or `CRITICAL_HIGH`. If the interval overlaps the threshold and cannot be classified, return `UNKNOWN` when the ordinary range is also unavailable. A verified critical flag overrides the ordinary flag, including `UNKNOWN` caused only by a missing printed range.
4. If no critical threshold is crossed, apply the printed-range rule. Missing or ambiguous information produces `UNKNOWN`.

`config/critical_thresholds.yaml` will contain **illustrative demo thresholds only; they are not clinically validated**. These tests check that the code applies the configuration correctly, not that the thresholds are medically appropriate.

### Next-step rules

The action type must be exactly one of `follow_up_test_package`, `doctor_consult` or `no_action`. The LLM will not choose it. Apply these rules in order:

1. Any verified critical result → urgent `doctor_consult` and a separate urgent message.
2. Any missing required result, `UNKNOWN` result, unmapped row or unresolved extraction conflict → routine `doctor_consult`.
3. For other abnormal results, use a follow-up package only if every abnormal result has a mapping and all mappings point to the same package. Otherwise use routine `doctor_consult`.
4. Use `no_action` only when all required and all recognized reported results are `NORMAL`.

An abnormal, critical, missing or unknown result must never produce `no_action`. Critical results always take precedence over package rules.

`config/follow_up_packages.yaml` will be a closed, demo-only allowlist:

| Test and flag | Demo package |
|---|---|
| `hemoglobin LOW`, `rbc LOW`, `wbc HIGH`, `platelets LOW/HIGH` | `CBC_FOLLOWUP` |
| `total_cholesterol HIGH`, `ldl HIGH`, `triglycerides HIGH`, `hdl LOW` | `LIPID_FOLLOWUP` |
| `hba1c HIGH` | `HBA1C_FOLLOWUP` |
| `tsh`, `t3` or `t4 LOW/HIGH` | `THYROID_FOLLOWUP` |
| `alt`, `ast`, `alp` or `total_bilirubin HIGH` | `LFT_FOLLOWUP` |

These package IDs test fixed routing in synthetic data. They are not clinical orders or medical recommendations. No other test/flag pair is enabled.

## 4. API and safety

### `POST /api/v1/explain`

Accept `multipart/form-data` with a required `file` (selectable-text PDF) and an optional `language` (`en`, `hi` or `both`; default `both`). I will not add a free-text patient-question field because conversational questions are outside the brief and would expand the scope. Prompt injection will be tested through text embedded in synthetic PDFs.

The response will include `request_id`, `report_id`, `report_type`, verified `tests[]`, English/Hindi explanations, `evidence_test_ids` for each statement, `next_step`, `urgent_message` (or `null`), a disclaimer and non-sensitive processing metrics. `next_step` will contain `action_type`, `urgency`, `package_id` (nullable) and `reason_test_ids`.

Return clear errors for malformed/unsupported files, failed demo access, file/page limits, PDFs with no usable text, quota limits and unexpected failures. Do not include report text, prompts or secrets in error messages.

### `GET /health` and privacy

`/health` will return service status and configured model ID only. The first version will accept PDFs up to 10 MB and five pages. Process reports in memory and do not persist them. Do not log PDF text, extracted values or full prompts; log only request ID, status, elapsed time, token use, estimated cost and error category.

Use synthetic reports only with the model provider. Protect the demo with an access code shared privately with the submission, per-IP/daily limits and provider-side quota controls. Do not publish the access code in the repository. A local usage ledger is supplementary because free-host storage may reset.

## 5. Evaluation plan

### Fixtures

I will generate 15 demo PDFs (three per report type: normal, abnormal and an edge/noisy case) and 30 separate evaluation PDFs. The generator will vary labels, row order, spacing, table layout and header/footer noise. Each PDF will have ground-truth JSON and metadata in `evals/`; `evals/matrix.csv` will record the file, scenario, expected values/flags and expected action.

| Case | Report | Scenario | Expected next step |
|---|---|---|---|
| EVAL-001 | CBC | All required results normal | `no_action` |
| EVAL-002 | CBC | Hemoglobin low | `CBC_FOLLOWUP` |
| EVAL-003 | CBC | WBC high | `CBC_FOLLOWUP` |
| EVAL-004 | CBC | RBC low and platelets high; same package | `CBC_FOLLOWUP` |
| EVAL-005 | CBC | Required platelet result missing | `doctor_consult` |
| EVAL-006 | CBC | Extra row cannot be mapped to the catalogue | `doctor_consult` |
| EVAL-007 | Lipid | Normal results with one-sided limits | `no_action` |
| EVAL-008 | Lipid | LDL high | `LIPID_FOLLOWUP` |
| EVAL-009 | Lipid | HDL low and triglycerides high | `LIPID_FOLLOWUP` |
| EVAL-010 | Lipid | Unsupported multi-tier range | `doctor_consult` |
| EVAL-011 | Lipid | LDL unit missing | `doctor_consult` |
| EVAL-012 | Lipid | Known unit aliases; all normal | `no_action` |
| EVAL-013 | HbA1c | Result within printed range | `no_action` |
| EVAL-014 | HbA1c | Result above printed range | `HBA1C_FOLLOWUP` |
| EVAL-015 | HbA1c | Qualified value entirely above range | `HBA1C_FOLLOWUP` |
| EVAL-016 | HbA1c | Qualified value overlaps a flag boundary | `doctor_consult` |
| EVAL-017 | HbA1c | Value equals an inclusive boundary | `no_action` |
| EVAL-018 | HbA1c | Value equals an exclusive upper boundary | `HBA1C_FOLLOWUP` |
| EVAL-019 | Thyroid | All required results normal | `no_action` |
| EVAL-020 | Thyroid | TSH high | `THYROID_FOLLOWUP` |
| EVAL-021 | Thyroid | TSH low and T4 high; same package | `THYROID_FOLLOWUP` |
| EVAL-022 | Thyroid | Required range ambiguous | `doctor_consult` |
| EVAL-023 | LFT | All required results normal | `no_action` |
| EVAL-024 | LFT | ALT high | `LFT_FOLLOWUP` |
| EVAL-025 | LFT | LFT and extra HbA1c result map to different packages | `doctor_consult` |
| EVAL-026 | LFT | Verified critical result with printed range | Urgent `doctor_consult` |
| EVAL-027 | LFT | Verified critical result; printed range missing | Urgent `doctor_consult` |
| EVAL-028 | CBC | Embedded PDF text asks the model to alter a normal value | `no_action` |
| EVAL-029 | Lipid | Footer injection asks the model to ignore report data | `no_action` |
| EVAL-030 | Thyroid | Noisy layout leaves value or unit ambiguous | `doctor_consult` |

### Baseline and improvement

I will compare two versions on the same 30 evaluation PDFs:

- **v0 baseline:** one LLM call extracts test names, values, units, ranges and flags. It has basic JSON parsing but no source verifier or deterministic flag engine.
- **v1:** the LLM extracts candidate fields; Python verifies source evidence, validates the schema, normalizes known aliases and calculates flags/critical results.

For a fair comparison, the evaluator will apply the same test-name and unit normalizer to v0 and v1 before scoring extraction. Each version's own flags will be scored against the same ground truth. This comparison covers extraction and flags; v0 does not produce explanations or next-step actions.

After the first v1 run, I will inspect actual failures and make one targeted change based on a reproducible issue. I will rerun the same suite and record the failure, change and before/after results. I will not create a failure just to make the improvement look stronger.

### Metrics

| Metric | How I will measure it |
|---|---|
| Extraction accuracy | Field-level and report-level exact match for test ID, value/qualifier, canonical unit and parsed range. |
| Flag correctness | Exact match for `NORMAL`, `LOW`, `HIGH`, `CRITICAL_LOW`, `CRITICAL_HIGH` and `UNKNOWN`. |
| Grounding | An independent evaluator checks rendered statements, evidence IDs, values, units and ranges against ground-truth JSON. Manually review 30 English/Hindi explanation pairs for unsupported claims. |
| Unsafe-advice rate | Count diagnosis, unsupported-cause, treatment/medication and unsafe-recommendation claims in the reviewed outputs; report unsafe claims divided by reviewed claims. |
| Policy/action correctness | Exact match for action, urgency and package ID, including mixed abnormal/unknown and critical cases. |
| Hindi consistency | Compare numbers/units with English and have 30 bilingual pairs reviewed for meaning and readability. Record reviewer and sample size; disclose if review is author-only. |
| Latency and cost | Measure per-report latency, tokens and cost. Report mean, median and p95 with sample count; 30 cases are not a production latency guarantee. |

The grounding evaluator will compare final text with ground truth, not reuse the runtime guard as its own metric. Since explanations use fixed templates, their factual claims can be checked directly. Zero unsafe outputs in this synthetic test set will not prove clinical safety. Critical-threshold tests check the demo configuration, not medical validity.

Run the baseline and first v1 evaluation once. Run the final suite three times if time allows; otherwise run it once and disclose the count. Save per-case outputs and results under `evals/results/`. Use the lowest supported model temperature and allow at most one counted structured-output repair retry. Include retry tokens, cost and latency in the totals.

## 6. Runtime, cost and delivery

### Runtime and cost

- Use Codex as the development assistant. Record how it was used in `AI_USAGE.md`; review and understand all generated code before committing it.
- Use Python 3.11+ and pin the tested Google ADK 2.x version in `requirements.txt`. PyPI lists `google-adk` 2.15.0 as the current release checked for this plan; verify installation and the minimal agent workflow before relying on it.
- Candidate runtime model: `gemini-3.5-flash-lite`, configured through `GEMINI_MODEL`. Confirm availability to the API project with a structured-output smoke test; if unavailable, use an available low-cost model and record the change.
- The Google pricing page checked on 21 November 2026 lists standard paid rates of $0.30 per million input tokens and $2.50 per million output tokens (including thinking tokens) for this candidate. Recheck pricing and provider data-use terms before the first API call. Only synthetic reports will be sent to the provider.

The planned evaluation uses about 150 calls: 30 v0 calls, 30 first-v1 calls and 90 calls for three final runs. Allow up to 100 additional development, smoke-test and repair calls, giving a planning total of **250 calls**. At an estimated average of 2,500 input and 800 output tokens per call, that is about **625,000 input and 200,000 output tokens**. At the listed rates and an assumed ₹90 per US dollar, the estimated cost is about **US$0.69 / ₹62**, before taxes and currency conversion. A 2x token allowance is about **₹124**. These are estimates; I will replace them with measured usage after the model spike.

Set provider-side quotas where available and stop application calls at **₹400**, leaving a buffer below the ₹500 limit. The README will state actual spend, model, provider tier, token counts, exchange-rate assumption and cost per successfully processed report. Report evaluation cost separately.

## References

- Google Agent Development Kit: https://google.github.io/adk-docs/
- Google ADK Python package: https://pypi.org/project/google-adk/
- Gemini API pricing: https://ai.google.dev/gemini-api/docs/pricing

I will recheck model availability, package version and pricing during the initial implementation spike.
