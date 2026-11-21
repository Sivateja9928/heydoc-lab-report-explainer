# Offline extraction evaluation

Cases: **30**. Mode: **offline**. No Gemini calls were made for this evaluation.
Synthetic software evaluation only; these results do not establish clinical validity.

## Metrics

| Metric | Correct | Denominator | Accuracy |
|---|---:|---:|---:|
| Test identification | 30 | 30 | 100.0% |
| Value text extraction | 30 | 30 | 100.0% |
| Numeric value parsing | 30 | 30 | 100.0% |
| Unit extraction | 30 | 30 | 100.0% |
| Reference-range extraction | 30 | 30 | 100.0% |
| Flag correctness | 30 | 30 | 100.0% |
| Evidence grounding | 30 | 30 | 100.0% |
| UNKNOWN handling | 20 | 20 expected UNKNOWN | 100.0% |
| Missing-field handling | 5 | 5 | 100.0% |
| Unexpected UNKNOWN among classifiable cases | 0 | 10 | — |

## Per-report results

| Case | Panel | Scenario | Expected ID | Predicted ID | Failed checks | Latency (ms) |
|---|---|---|---|---|---|---:|
| EVAL-001 | cbc | normal | hemoglobin | hemoglobin | — | 6.418 |
| EVAL-002 | cbc | abnormal | wbc | wbc | — | 1.893 |
| EVAL-003 | cbc | missing_field_unit | hemoglobin | hemoglobin | — | 1.287 |
| EVAL-004 | cbc | malformed_row | rbc | rbc | — | 1.208 |
| EVAL-005 | cbc | unsupported_unit | platelets | platelets | — | 1.148 |
| EVAL-006 | cbc | ambiguous_range | hemoglobin | hemoglobin | — | 1.112 |
| EVAL-007 | lipid_profile | normal_one_sided_range | triglycerides | triglycerides | — | 1.125 |
| EVAL-008 | lipid_profile | abnormal | ldl | ldl | — | 1.157 |
| EVAL-009 | lipid_profile | missing_field_range | hdl | hdl | — | 1.228 |
| EVAL-010 | lipid_profile | malformed_row | total_cholesterol | total_cholesterol | — | 1.378 |
| EVAL-011 | lipid_profile | unsupported_unit | ldl | ldl | — | 1.516 |
| EVAL-012 | lipid_profile | ambiguous_range | triglycerides | triglycerides | — | 1.641 |
| EVAL-013 | hba1c | normal | hba1c | hba1c | — | 3.729 |
| EVAL-014 | hba1c | abnormal | hba1c | hba1c | — | 5.533 |
| EVAL-015 | hba1c | missing_field_value | hba1c | hba1c | — | 6.966 |
| EVAL-016 | hba1c | malformed_row | hba1c | hba1c | — | 3.087 |
| EVAL-017 | hba1c | unsupported_unit | hba1c | hba1c | — | 1.920 |
| EVAL-018 | hba1c | ambiguous_range | hba1c | hba1c | — | 1.904 |
| EVAL-019 | thyroid_profile | normal | tsh | tsh | — | 1.352 |
| EVAL-020 | thyroid_profile | abnormal | free_t4 | free_t4 | — | 1.431 |
| EVAL-021 | thyroid_profile | missing_field_unit | t3 | t3 | — | 1.411 |
| EVAL-022 | thyroid_profile | malformed_row | tsh | tsh | — | 1.291 |
| EVAL-023 | thyroid_profile | unsupported_unit | tsh | tsh | — | 1.194 |
| EVAL-024 | thyroid_profile | ambiguous_range | free_t4 | free_t4 | — | 1.369 |
| EVAL-025 | liver_function | normal | alt | alt | — | 2.484 |
| EVAL-026 | liver_function | abnormal | alt | alt | — | 1.444 |
| EVAL-027 | liver_function | missing_field_value | ast | ast | — | 1.002 |
| EVAL-028 | liver_function | malformed_row | alp | alp | — | 1.044 |
| EVAL-029 | liver_function | unsupported_unit | total_bilirubin | total_bilirubin | — | 1.057 |
| EVAL-030 | liver_function | ambiguous_range | ast | ast | — | 1.159 |

## Failed cases

None.

## Latency

Mean 2.016 ms; median 1.373 ms; p95 6.418 ms; denominator 30 reports.

Latency is local offline processing time and excludes Gemini/API costs. No project cost total is estimated here.
