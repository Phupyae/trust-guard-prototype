"""Compute evaluation metrics from labelled result folders.

    python eval/compute_metrics.py eval/results/<folder>
    python eval/compute_metrics.py eval/results/<main> eval/results/<ablation>   # side-by-side
    python eval/compute_metrics.py --merge live_all eval/results/<day1> eval/results/<day2>   # one combined set

Reads claims_to_label.csv and answers_to_label.csv (gold columns filled in by a person, or
pre-filled for controlled cases) and writes, into each folder:
    metrics.json   every number below
    metrics.md     the tables for the slides / report
    failures.md    every case TrustGuard got wrong, for the limitations section

Metric definitions (also in eval/README.md):
  Claim classification accuracy / macro F1   TrustGuard status vs gold status, per claim
  Critical error recall      share of gold-CONTRADICTED claims TrustGuard marked CONTRADICTED
                             (lenient: marked anything other than SUPPORTED)
  False positive rate        share of gold-SUPPORTED claims TrustGuard did NOT mark SUPPORTED
  Citation accuracy (auto)   share of TrustGuard's cited sections that are in the case's expected evidence
  Incomplete-answer recall   share of answers with a gold missing step that TrustGuard flagged as incomplete
  Correction support rate    share of suggested corrections that passed all three re-checks (A+B+C)
  Correction accuracy        share of suggested corrections a person judged correct (if labelled)
  System A vs B              wrong answers that reach the employee with no warning:
                               A (Agent 1 only) = every wrong answer
                               B (Agent 1 + TrustGuard) = wrong answers TrustGuard marked "verified"
  Verification time          TrustGuard seconds per answer (mean / median / 95th percentile)
"""
import csv
import json
import statistics
import sys
from datetime import datetime
from pathlib import Path

STATUSES = ["SUPPORTED", "CONTRADICTED", "INSUFFICIENT_EVIDENCE"]


def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def yn(v) -> str:
    v = (v or "").strip().upper()
    return {"YES": "Y", "NO": "N", "TRUE": "Y", "FALSE": "N", "1": "Y", "0": "N"}.get(v, v[:1] if v else "")


def ratio(num: int, den: int):
    return {"value": round(num / den, 3) if den else None, "num": num, "den": den}


def pct(r: dict) -> str:
    return "n/a (no labelled cases)" if r["value"] is None else f"{r['value']:.0%} ({r['num']}/{r['den']})"


def claim_metrics(rows: list[dict]) -> dict:
    lab = [r for r in rows if (r.get("gold_status") or "").strip().upper() in STATUSES]
    for r in lab:
        r["gold_status"] = r["gold_status"].strip().upper()
    out = {"claims_total": len(rows), "claims_labelled": len(lab)}
    out["accuracy"] = ratio(sum(r["gold_status"] == r["tg_status"] for r in lab), len(lab))
    per_class, f1s = {}, []
    for s in STATUSES:
        tp = sum(r["gold_status"] == s and r["tg_status"] == s for r in lab)
        fp = sum(r["gold_status"] != s and r["tg_status"] == s for r in lab)
        fn = sum(r["gold_status"] == s and r["tg_status"] != s for r in lab)
        p = tp / (tp + fp) if tp + fp else None
        rc = tp / (tp + fn) if tp + fn else None
        f1 = 2 * p * rc / (p + rc) if p and rc else (0.0 if (tp + fp) and (tp + fn) else None)
        per_class[s] = {"precision": None if p is None else round(p, 3), "recall": None if rc is None else round(rc, 3),
                        "f1": None if f1 is None else round(f1, 3), "support": tp + fn}
        if f1 is not None and tp + fn:
            f1s.append(f1)
    out["per_class"] = per_class
    out["macro_f1"] = round(sum(f1s) / len(f1s), 3) if f1s else None
    out["confusion"] = {g: {t: sum(r["gold_status"] == g and r["tg_status"] == t for r in lab) for t in STATUSES}
                        for g in STATUSES}
    gold_c = [r for r in lab if r["gold_status"] == "CONTRADICTED"]
    out["critical_error_recall"] = ratio(sum(r["tg_status"] == "CONTRADICTED" for r in gold_c), len(gold_c))
    out["critical_error_recall_lenient"] = ratio(sum(r["tg_status"] != "SUPPORTED" for r in gold_c), len(gold_c))
    gold_s = [r for r in lab if r["gold_status"] == "SUPPORTED"]
    out["false_positive_rate"] = ratio(sum(r["tg_status"] != "SUPPORTED" for r in gold_s), len(gold_s))
    cited = [r for r in rows if r.get("citation_in_expected") in ("Y", "N")]
    out["citation_accuracy_auto"] = ratio(sum(r["citation_in_expected"] == "Y" for r in cited), len(cited))
    out["failures"] = [r for r in lab if r["gold_status"] != r["tg_status"]]
    return out


def answer_metrics(rows: list[dict]) -> dict:
    out = {"answers_total": len(rows)}
    lab = [r for r in rows if yn(r.get("gold_answer_ok")) in ("Y", "N")]
    flagged = lambda r: r["tg_overall"] != "success"  # noqa: E731
    wrong = [r for r in lab if yn(r["gold_answer_ok"]) == "N"]
    right = [r for r in lab if yn(r["gold_answer_ok"]) == "Y"]
    missed = [r for r in wrong if not flagged(r)]
    out["answers_labelled"] = len(lab)
    out["agent1_wrong_rate"] = ratio(len(wrong), len(lab))
    out["system_a_unflagged_wrong"] = ratio(len(wrong), len(lab))
    out["system_b_unflagged_wrong"] = ratio(len(missed), len(lab))
    out["wrong_answer_detection_rate"] = ratio(len(wrong) - len(missed), len(wrong))
    out["false_alarm_rate"] = ratio(sum(flagged(r) for r in right), len(right))
    ms = [r for r in rows if yn(r.get("gold_missing_step")) in ("Y", "N")]
    gold_missing = [r for r in ms if yn(r["gold_missing_step"]) == "Y"]
    gold_complete = [r for r in ms if yn(r["gold_missing_step"]) == "N"]
    out["incomplete_answer_recall"] = ratio(sum(bool(r["tg_missing"]) for r in gold_missing), len(gold_missing))
    out["incomplete_false_flag_rate"] = ratio(sum(bool(r["tg_missing"]) for r in gold_complete), len(gold_complete))
    out["missed_missing"] = [r for r in gold_missing if not r["tg_missing"]]
    sug = [r for r in rows if r["correction_status"] == "suggested"]
    out["corrections_suggested"] = len(sug)
    out["correction_support_rate"] = ratio(sum(r["reverification"] == "confirmed" for r in sug), len(sug))
    out["correction_support_rate_incl_partial"] = ratio(
        sum(r["reverification"] in ("confirmed", "partially_confirmed") for r in sug), len(sug))
    judged = [r for r in sug if yn(r.get("gold_correction_ok")) in ("Y", "N")]
    out["correction_accuracy"] = ratio(sum(yn(r["gold_correction_ok"]) == "Y" for r in judged), len(judged))
    conf = [r for r in judged if r["reverification"] == "confirmed"]
    out["reverification_precision"] = ratio(sum(yn(r["gold_correction_ok"]) == "Y" for r in conf), len(conf))
    fixed = [r for r in wrong if flagged(r) and r["correction_status"] == "suggested"
             and yn(r.get("gold_correction_ok")) == "Y"]
    out["wrong_answers_fixed_by_correction"] = ratio(len(fixed), len(wrong)) if judged else ratio(0, 0)
    tg = [float(r["trustguard_s"]) for r in rows if r.get("trustguard_s") not in ("", None)]
    a1 = [float(r["agent1_s"]) for r in rows if r.get("agent1_s") not in ("", None)]
    out["trustguard_seconds"] = ({"mean": round(statistics.mean(tg), 2), "median": round(statistics.median(tg), 2),
                                  "p95": round(sorted(tg)[max(0, int(round(0.95 * len(tg))) - 1)], 2), "n": len(tg)}
                                 if tg else None)
    out["agent1_seconds_mean"] = round(statistics.mean(a1), 2) if a1 else None
    out["by_scenario"] = {}
    for sc in sorted({r["scenario"] for r in rows}):
        sr = [r for r in rows if r["scenario"] == sc]
        sl = [r for r in sr if yn(r.get("gold_answer_ok")) in ("Y", "N")]
        sw = [r for r in sl if yn(r["gold_answer_ok"]) == "N"]
        out["by_scenario"][sc] = {"answers": len(sr), "flagged": sum(flagged(r) for r in sr),
                                  "labelled": len(sl), "agent1_wrong": len(sw),
                                  "wrong_caught": sum(flagged(r) for r in sw)}
    out["missed_wrong"] = missed
    out["false_alarms"] = [r for r in right if flagged(r)]
    out["not_confirmed"] = [r for r in sug if r["reverification"] == "not_confirmed"]
    return out


def to_markdown(name: str, info: dict, c: dict, a: dict) -> str:
    L = [f"# TrustGuard evaluation: {name}", "",
         f"- Kind: **{info.get('kind')}** · TrustGuard model: `{info.get('trustguard_model')}` · Agent 1 model: "
         f"`{info.get('agent1_model') or 'n/a'}` (scope `{info.get('agent1_scope')}`) · retriever: {info.get('retriever')} "
         f"· NLI: {info.get('nli')}",
         f"- Answers: {a['answers_total']} ({a['answers_labelled']} labelled) · claims: {c['claims_total']} "
         f"({c['claims_labelled']} labelled)", ""]
    if info.get("kind") == "controlled":
        L += ["> Controlled cases use FIXED answers written by the team. They test TrustGuard on known errors only. "
              "Report them separately from the live results.", ""]
    L += ["## System A (Agent 1 only) vs System B (Agent 1 + TrustGuard)", "",
          "| | Value |", "|---|---|",
          f"| Agent 1 answers that were wrong or incomplete | {pct(a['agent1_wrong_rate'])} |",
          f"| **System A**: wrong answers reaching the employee with no warning | {pct(a['system_a_unflagged_wrong'])} |",
          f"| **System B**: wrong answers TrustGuard still marked verified | {pct(a['system_b_unflagged_wrong'])} |",
          f"| Wrong answers TrustGuard flagged | {pct(a['wrong_answer_detection_rate'])} |",
          f"| Correct answers TrustGuard flagged anyway (false alarms) | {pct(a['false_alarm_rate'])} |",
          f"| Wrong answers fixed by a correct suggested answer | {pct(a['wrong_answers_fixed_by_correction'])} |", "",
          "## Claim-level verification", "", "| Metric | Value |", "|---|---|",
          f"| Claim classification accuracy | {pct(c['accuracy'])} |",
          f"| Macro F1 (3 classes) | {c['macro_f1'] if c['macro_f1'] is not None else 'n/a'} |",
          f"| Critical error recall (marked CONTRADICTED) | {pct(c['critical_error_recall'])} |",
          f"| Critical error recall, lenient (not marked SUPPORTED) | {pct(c['critical_error_recall_lenient'])} |",
          f"| False positive rate (correct claims flagged) | {pct(c['false_positive_rate'])} |",
          f"| Citation accuracy (auto: cited section is an expected one) | {pct(c['citation_accuracy_auto'])} |", "",
          "| Gold \\ TrustGuard | " + " | ".join(STATUSES) + " |", "|---|" + "---|" * len(STATUSES)]
    for g in STATUSES:
        L.append(f"| {g} | " + " | ".join(str(c["confusion"][g][t]) for t in STATUSES) + " |")
    L += ["", "| Class | Precision | Recall | F1 | Support |", "|---|---|---|---|---|"]
    for s, m in c["per_class"].items():
        L.append(f"| {s} | {m['precision']} | {m['recall']} | {m['f1']} | {m['support']} |")
    ts = a["trustguard_seconds"]
    L += ["", "## Completeness, correction and time", "", "| Metric | Value |", "|---|---|",
          f"| Incomplete answers detected | {pct(a['incomplete_answer_recall'])} |",
          f"| Complete answers wrongly flagged as incomplete | {pct(a['incomplete_false_flag_rate'])} |",
          f"| Corrections suggested | {a['corrections_suggested']} |",
          f"| Correction support rate (passed A+B+C) | {pct(a['correction_support_rate'])} |",
          f"| Correction support rate incl. partly confirmed | {pct(a['correction_support_rate_incl_partial'])} |",
          f"| Corrections judged correct by a person | {pct(a['correction_accuracy'])} |",
          f"| Of corrections marked re-checked, share judged correct | {pct(a['reverification_precision'])} |",
          f"| TrustGuard time per answer (mean / median / p95) | "
          + (f"{ts['mean']} s / {ts['median']} s / {ts['p95']} s" if ts else "n/a") + " |",
          f"| Agent 1 time per answer (mean) | {a['agent1_seconds_mean']} s |", "",
          "## By scenario", "", "| Scenario | Answers | Flagged by TrustGuard | Labelled | Agent 1 wrong | Wrong caught |",
          "|---|---|---|---|---|---|"]
    for sc, m in a["by_scenario"].items():
        L.append(f"| {sc} | {m['answers']} | {m['flagged']} | {m['labelled']} | {m['agent1_wrong']} | {m['wrong_caught']} |")
    L += ["", "_Report detection performance, not improved final-answer accuracy, unless corrections were judged by a "
              "person (gold_correction_ok)._"]
    return "\n".join(L) + "\n"


def unresolved_errors(errors: list, answer_rows: list[dict]) -> list:
    """errors.json keeps every failed attempt. A run that errored and then finished on
    --resume has a row in answers_to_label.csv, so its old error is no longer a failure."""
    finished = {r.get("run_id") for r in answer_rows}
    return [e for e in errors if e.get("run_id") not in finished]


def failures_md(name: str, c: dict, a: dict, errors: list) -> str:
    L = [f"# Failures and limitations: {name}", ""]
    L += ["## Claims TrustGuard classified differently from the gold label", ""]
    for r in c["failures"] or []:
        L.append(f"- **{r['run_id']}** gold {r['gold_status']}, TrustGuard {r['tg_status']}: “{r['claim']}” "
                 f"(cited {r['tg_source']} §{r['tg_section']}) {r.get('notes', '')}")
    if not c["failures"]:
        L.append("- none" if c.get("claims_labelled") else "- none yet (no claims labelled)")
    L += ["", "## Wrong answers TrustGuard marked verified (missed)", ""]
    L += [f"- **{r['run_id']}**: {r['agent1_answer']} {r.get('notes', '')}" for r in a["missed_wrong"]] or ["- none"]
    L += ["", "## Missing steps TrustGuard didn't report", ""]
    L += [f"- **{r['run_id']}**: {r['agent1_answer']} (TrustGuard: {r['tg_overall']}; "
          f"{'the answer was still flagged' if r['tg_overall'] in ('error', 'warning') else 'the answer was NOT flagged'}) "
          f"{r.get('notes', '')}" for r in a.get("missed_missing", [])] or ["- none"]
    L += ["", "## Correct answers TrustGuard flagged (false alarms)", ""]
    L += [f"- **{r['run_id']}** ({r['tg_overall']}): {r['tg_message']} | answer: {r['agent1_answer']}"
          for r in a["false_alarms"]] or ["- none"]
    L += ["", "## Suggested corrections that failed re-verification", ""]
    L += [f"- **{r['run_id']}**: {r['correction_text']}" for r in a["not_confirmed"]] or ["- none"]
    L += ["", "## Runs that errored", ""]
    L += [f"- **{e['run_id']}**: {e['error']}" for e in errors] or ["- none"]
    return "\n".join(L) + "\n"


def compute_and_write(folders: list[Path]) -> list[dict]:
    summaries = []
    for folder in map(Path, folders):
        info = json.loads((folder / "run_info.json").read_text(encoding="utf-8")) if (folder / "run_info.json").exists() else {}
        c = claim_metrics(read_csv(folder / "claims_to_label.csv"))
        answer_rows = read_csv(folder / "answers_to_label.csv")
        errors = json.loads((folder / "errors.json").read_text(encoding="utf-8")) if (folder / "errors.json").exists() else []
        errors = unresolved_errors(errors, answer_rows)
        a = answer_metrics(answer_rows)
        strip = lambda d: {k: v for k, v in d.items() if k not in ("failures", "missed_wrong", "false_alarms", "not_confirmed", "missed_missing")}  # noqa: E731
        (folder / "metrics.json").write_text(json.dumps({"run_info": info, "claims": strip(c), "answers": strip(a),
                                                         "errors": len(errors)}, indent=2), encoding="utf-8")
        (folder / "metrics.md").write_text(to_markdown(folder.name, info, c, a), encoding="utf-8")
        (folder / "failures.md").write_text(failures_md(folder.name, c, a, errors), encoding="utf-8")
        print(f"\n== {folder.name} ==")
        print(f"claims labelled {c['claims_labelled']}/{c['claims_total']} · accuracy {pct(c['accuracy'])} · "
              f"macro F1 {c['macro_f1']} · critical recall {pct(c['critical_error_recall'])} · "
              f"FPR {pct(c['false_positive_rate'])} · citation {pct(c['citation_accuracy_auto'])}")
        print(f"answers labelled {a['answers_labelled']}/{a['answers_total']} · System A unflagged wrong "
              f"{pct(a['system_a_unflagged_wrong'])} · System B {pct(a['system_b_unflagged_wrong'])} · "
              f"correction support {pct(a['correction_support_rate'])}")
        print(f"wrote {folder / 'metrics.md'} and failures.md")
        summaries.append({"name": folder.name, "info": info, "claims": c, "answers": a})
    if len(summaries) > 1:
        rows = [("TrustGuard model", lambda s: s["info"].get("trustguard_model", "")),
                ("Claim accuracy", lambda s: pct(s["claims"]["accuracy"])),
                ("Macro F1", lambda s: s["claims"]["macro_f1"]),
                ("Critical error recall", lambda s: pct(s["claims"]["critical_error_recall"])),
                ("False positive rate", lambda s: pct(s["claims"]["false_positive_rate"])),
                ("Wrong answers flagged", lambda s: pct(s["answers"]["wrong_answer_detection_rate"])),
                ("False alarms", lambda s: pct(s["answers"]["false_alarm_rate"])),
                ("Incomplete answers detected", lambda s: pct(s["answers"]["incomplete_answer_recall"])),
                ("Correction support rate", lambda s: pct(s["answers"]["correction_support_rate"])),
                ("TrustGuard mean seconds", lambda s: (s["answers"]["trustguard_seconds"] or {}).get("mean"))]
        L = ["# Side-by-side comparison", "", "| Metric | " + " | ".join(s["name"] for s in summaries) + " |",
             "|---|" + "---|" * len(summaries)]
        L += [f"| {label} | " + " | ".join(str(f(s)) for s in summaries) + " |" for label, f in rows]
        path = Path(folders[0]).parent / f"comparison_{datetime.now():%Y%m%d_%H%M%S}.md"
        path.write_text("\n".join(L) + "\n", encoding="utf-8")
        print(f"\nwrote {path}")
    return summaries


def merge(name: str, folders: list[Path]) -> Path:
    """Combine several result folders (e.g. a run split over two days) into one folder.
    run_ids get the source folder's name in front, so 'A01-r1' from two days stays distinct."""
    folders = [Path(f) for f in folders]
    out = folders[0].parent / name
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f"{out} already exists; choose another name.")
    out.mkdir(parents=True, exist_ok=True)
    claims, answers, errors, infos = [], [], [], []
    for f in folders:
        info = json.loads((f / "run_info.json").read_text(encoding="utf-8")) if (f / "run_info.json").exists() else {}
        infos.append(info)
        for r in read_csv(f / "claims_to_label.csv"):
            claims.append({**r, "run_id": f"{f.name}:{r['run_id']}"})
        answer_rows = read_csv(f / "answers_to_label.csv")
        for r in answer_rows:
            answers.append({**r, "run_id": f"{f.name}:{r['run_id']}"})
        if (f / "errors.json").exists():
            errs = unresolved_errors(json.loads((f / "errors.json").read_text(encoding="utf-8")), answer_rows)
            errors += [{**e, "run_id": f"{f.name}:{e['run_id']}"} for e in errs]
    kinds = {i.get("kind") for i in infos}
    models = {i.get("trustguard_model") for i in infos}
    if len(kinds) > 1 or len(models) > 1:
        print(f"WARNING: merging different kinds/models {kinds} {models}. Usually you only merge runs with the same settings.")
    merged_info = {**(infos[0] if infos else {}), "merged_from": [f.name for f in folders],
                   "runs": sum(int(i.get("runs", 1) or 1) for i in infos)}
    (out / "run_info.json").write_text(json.dumps(merged_info, indent=2), encoding="utf-8")
    for fname, rows in (("claims_to_label.csv", claims), ("answers_to_label.csv", answers)):
        if rows:
            with open(out / fname, "w", newline="", encoding="utf-8-sig") as fh:
                w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
                w.writeheader()
                w.writerows(rows)
    if errors:
        (out / "errors.json").write_text(json.dumps(errors, indent=2), encoding="utf-8")
    print(f"merged {len(answers)} answers and {len(claims)} claims from {len(folders)} folders into {out}")
    return out


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(1)
    if args[0] == "--merge":
        if len(args) < 4:
            print("usage: python eval/compute_metrics.py --merge NEW_NAME FOLDER1 FOLDER2 [...]")
            sys.exit(1)
        compute_and_write([merge(args[1], [Path(p) for p in args[2:]])])
    else:
        compute_and_write([Path(p) for p in args])
