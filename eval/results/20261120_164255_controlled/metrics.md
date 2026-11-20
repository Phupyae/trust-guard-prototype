# TrustGuard evaluation: 20261120_164255_controlled

- Kind: **controlled** · TrustGuard model: `gemini-3.5-flash-lite` · Agent 1 model: `n/a` (scope `all`) · retriever: sentence-transformers/all-MiniLM-L6-v2 · NLI: cross-encoder/nli-deberta-v3-xsmall
- Answers: 12 (12 labelled) · claims: 20 (20 labelled)

> Controlled cases use FIXED answers written by the team. They test TrustGuard on known errors only. Report them separately from the live results.

## System A (Agent 1 only) vs System B (Agent 1 + TrustGuard)

| | Value |
|---|---|
| Agent 1 answers that were wrong or incomplete | 67% (8/12) |
| **System A**: wrong answers reaching the employee with no warning | 67% (8/12) |
| **System B**: wrong answers TrustGuard still marked verified | 0% (0/12) |
| Wrong answers TrustGuard flagged | 100% (8/8) |
| Correct answers TrustGuard flagged anyway (false alarms) | 0% (0/4) |
| Wrong answers fixed by a correct suggested answer | n/a (no labelled cases) |

## Claim-level verification

| Metric | Value |
|---|---|
| Claim classification accuracy | 100% (20/20) |
| Macro F1 (3 classes) | 1.0 |
| Critical error recall (marked CONTRADICTED) | 100% (8/8) |
| Critical error recall, lenient (not marked SUPPORTED) | 100% (8/8) |
| False positive rate (correct claims flagged) | 0% (0/10) |
| Citation accuracy (auto: cited section is an expected one) | 100% (18/18) |

| Gold \ TrustGuard | SUPPORTED | CONTRADICTED | INSUFFICIENT_EVIDENCE |
|---|---|---|---|
| SUPPORTED | 10 | 0 | 0 |
| CONTRADICTED | 0 | 8 | 0 |
| INSUFFICIENT_EVIDENCE | 0 | 0 | 2 |

| Class | Precision | Recall | F1 | Support |
|---|---|---|---|---|
| SUPPORTED | 1.0 | 1.0 | 1.0 | 10 |
| CONTRADICTED | 1.0 | 1.0 | 1.0 | 8 |
| INSUFFICIENT_EVIDENCE | 1.0 | 1.0 | 1.0 | 2 |

## Completeness, correction and time

| Metric | Value |
|---|---|
| Incomplete answers detected | 67% (2/3) |
| Complete answers wrongly flagged as incomplete | 0% (0/9) |
| Corrections suggested | 6 |
| Correction support rate (passed A+B+C) | 100% (6/6) |
| Correction support rate incl. partly confirmed | 100% (6/6) |
| Corrections judged correct by a person | n/a (no labelled cases) |
| Of corrections marked re-checked, share judged correct | n/a (no labelled cases) |
| TrustGuard time per answer (mean / median / p95) | 7.6 s / 6.13 s / 15.88 s |
| Agent 1 time per answer (mean) | None s |

## By scenario

| Scenario | Answers | Flagged by TrustGuard | Labelled | Agent 1 wrong | Wrong caught |
|---|---|---|---|---|---|
| approval | 3 | 3 | 3 | 3 | 3 |
| correct | 3 | 0 | 3 | 0 | 0 |
| missing_evidence | 2 | 2 | 2 | 2 | 2 |
| missing_step | 1 | 1 | 1 | 1 | 1 |
| outdated | 3 | 2 | 3 | 2 | 2 |

_Report detection performance, not improved final-answer accuracy, unless corrections were judged by a person (gold_correction_ok)._
