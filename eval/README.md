# Evaluating TrustGuard

Goal: show with evidence whether **Agent 1 + TrustGuard (System B)** is more reliable than **Agent 1 alone (System A)**, and be honest about where TrustGuard fails.

## 1. Live run (main evidence, nothing scripted)

```bash
python eval/run_eval.py --live --runs 1 --delay 6
```

**Stopping and continuing.** Results are saved after every question. You can press Ctrl+C any time,
and if the free-tier daily quota runs out the run stops by itself (after 3 rate-limit errors in a row).
Nothing finished is lost. Continue later (e.g. after 4 pm Singapore time, when the quota resets) with:
```bash
python eval/run_eval.py --resume eval/results/<folder>
```
Questions that errored are retried on resume. Don't edit the CSVs while a run is going (wait until it
finishes; labels typed in between runs are kept).

**Several runs on different days** (e.g. `--runs 1` today, again tomorrow with `--out live_day2`):
combine them into one set of metrics with
```bash
python eval/compute_metrics.py --merge live_all eval/results/<day1> eval/results/<day2>
```
- Agent 1 answers each of the 26 questions in `questions.json` **live**; TrustGuard checks each answer.
- `--runs 3` asks each question 3 times, which gives a more honest estimate of how often Agent 1 gets it wrong (its answers vary between runs).
- `--delay 6` adds seconds between questions for the free tier's per-minute limit. `--only A01,O02` or `--limit 5` for a quick check.
- Output: `eval/results/<timestamp>_live/` with `runs.jsonl`, `claims_to_label.csv`, `answers_to_label.csv`.

## 2. Label (about 1 to 2 hours for 3 people, split by scenario)
Open the two CSVs in Excel or Google Sheets. In Excel, save with **File → Save As → "CSV UTF-8"** so $ and § survive, and close the file before running anything else on that folder. Use the `key_facts` and `expected_evidence` columns and the policy PDFs in `knowledge_base/`. **Decide the gold label from the policy, not from TrustGuard's column**, and cover the `tg_*` columns while labelling if you can.

**claims_to_label.csv**, column `gold_status`, one of:
| Gold label | When |
|---|---|
| `SUPPORTED` | The policy in effect for the question's date states this |
| `CONTRADICTED` | The policy says something different (amount, approver, deadline, required step) |
| `INSUFFICIENT_EVIDENCE` | No policy in the repository covers it |

**answers_to_label.csv**
| Column | Y when | N when |
|---|---|---|
| `gold_answer_ok` | Agent 1's answer is correct **and** complete enough to act on | anything wrong or a required step missing |
| `gold_missing_step` | the answer leaves out something the policy requires for this question | nothing required is missing |
| `gold_correction_ok` | TrustGuard's suggested answer (if any) is correct and complete | it is wrong or incomplete (leave blank if no suggestion) |

Write disagreements or doubts in `notes`. Two people labelling the same 10 rows and comparing is a cheap consistency check worth mentioning.

## 3. Metrics
```bash
python eval/compute_metrics.py eval/results/<timestamp>_live
```
Writes `metrics.md` (tables for the slides), `metrics.json` and `failures.md` (every miss, for the limitations slide).

| Metric | What it measures |
|---|---|
| Claim classification accuracy, Macro F1 | TrustGuard's status vs gold, per claim (3 classes) |
| Critical error recall | gold-CONTRADICTED claims that TrustGuard marked CONTRADICTED (lenient: not SUPPORTED) |
| False positive rate | gold-SUPPORTED claims TrustGuard flagged |
| Citation accuracy (auto) | TrustGuard's cited section is one of the expected sections |
| Incomplete-answer recall | answers with a missing step that TrustGuard flagged as incomplete |
| Correction support rate | suggested corrections that passed all three re-checks (A citation, B rules table, C entailment) |
| Correction accuracy | suggested corrections a person judged correct; also shows whether "re-checked" can be trusted |
| **System A vs B** | wrong answers reaching the employee **with no warning**: A = all of them; B = those TrustGuard marked verified |
| False alarm rate | correct answers TrustGuard flagged anyway (the cost of System B) |
| Verification time | TrustGuard seconds per answer (mean / median / p95), plus Agent 1's |

If corrections were not judged by a person, report **error detection**, not "improved final answers".

## 4. Ablation: is it just the stronger model?
Re-check the **same** Agent 1 answers with TrustGuard on the cheap model:
```bash
python eval/run_eval.py --reuse eval/results/<live folder> --tg-model gemini-3.5-flash-lite
python eval/compute_metrics.py eval/results/<live folder> eval/results/<reuse folder>
```
Answer-level labels are copied automatically, so the answer-level rows of the comparison need no new labelling (claim-level rows would, because claims are re-extracted). If the cheap-model TrustGuard still catches most wrong answers, the value comes from the **process** (version filtering, sibling rules, derivation, completeness), not just the model.

Optional: `--live --agent1-scope approved` runs Agent 1 on current versions only (a well-maintained assistant), so only the model's own mistakes remain.

## 5. Controlled regression set (report separately)
```bash
python eval/run_eval.py --controlled
```
12 **fixed** answers written by the team, with known labels, so metrics come out immediately. Use it to check nothing broke after a prompt change, not as the headline result.

## Changes to the answer key (disclose these)
Expected-evidence lists were widened after the first real runs, only where TrustGuard cited a section
whose text also supports the claim:
- $80,000 withdrawal (A01, G_cash_outdated): added SOP_OPS_021_V3_0 §3.2 (the "Branch Manager only, same day" band).
- Travel claim approval (O01, A_correct, B_incorrect): added TRAVEL_POLICY_V2 §7.1 (manager approval for
  claims up to $2,000, plus Department Head above, so manager approval for every claim).

## Error logging
- `failures.md` in each results folder: misclassified claims, missed wrong answers, false alarms, unconfirmed corrections, runs that errored.
- The app also logs to `logs/` (`verifications`, `failures`, `blocked_inputs`, `feedback` JSONL files). Live demo questions logged there can be labelled later and added to `questions.json`, so the test set grows from real questions.
