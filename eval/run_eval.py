"""Run the evaluation and produce files to label and metrics.

LIVE (main evidence; nothing scripted):
    python eval/run_eval.py --live --runs 1
  Agent 1 answers every question in eval/questions.json live; TrustGuard checks each live
  answer. Writes eval/results/<timestamp>_live/ with:
    runs.jsonl              full TrustGuard report for every run
    claims_to_label.csv     one row per claim -> fill gold_status
    answers_to_label.csv    one row per answer -> fill gold_answer_ok, gold_missing_step, gold_correction_ok
  Then label the CSVs (see eval/README.md) and run:
    python eval/compute_metrics.py eval/results/<that folder>

CONTROLLED (regression check; fixed answers written by the team, labels already known):
    python eval/run_eval.py --controlled
  Metrics are computed straight away.

ABLATION ("is it just the stronger model?") — same Agent 1 answers, TrustGuard on the cheap model:
    python eval/run_eval.py --reuse eval/results/<live folder> --tg-model gemini-3.5-flash-lite
  Answer-level labels are copied from the reused folder, so no re-labelling is needed for the
  answer-level comparison.

STOP AND CONTINUE: results are saved after every question. Press Ctrl+C any time (or let the
laptop lose connection); if the daily quota runs out, the run stops by itself. Continue with:
    python eval/run_eval.py --resume eval/results/<folder>

Useful flags: --limit 5 (first 5 questions), --only A01,O02, --delay 6 (seconds between questions,
for free-tier rate limits), --mock (offline plumbing check), --tfidf (keyword search).
"""
import argparse
import csv
import json
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import config  # noqa: E402
from modules.banking_assistant import BankingAssistant, build_agent1_retriever  # noqa: E402
from modules.document_loader import load_knowledge_base  # noqa: E402
from modules.evidence_retriever import EvidenceRetriever, make_embedder  # noqa: E402
from modules.llm_client import LLMError, get_client  # noqa: E402
from modules.nli import NLIChecker  # noqa: E402
from modules.pipeline import run_pipeline, run_two_agent  # noqa: E402
from modules.schemas import AgentHandoff  # noqa: E402

EVAL_DIR = Path(__file__).resolve().parent
CLAIM_FIELDS = ["run_id", "case_id", "scenario", "question", "agent1_answer", "claim_id", "claim", "tg_status",
                "tg_source", "tg_section", "tg_version", "citation_in_expected", "root_cause", "needs_review",
                "expected_evidence", "key_facts", "gold_status", "notes"]
ANSWER_FIELDS = ["run_id", "case_id", "scenario", "question", "agent1_answer", "agent1_model", "agent1_sources",
                 "tg_model", "tg_overall", "tg_message", "tg_missing", "correction_status", "correction_text",
                 "reverification", "agent1_s", "trustguard_s", "key_facts", "expected_result",
                 "gold_answer_ok", "gold_missing_step", "gold_correction_ok", "notes"]


def norm_ref(source: str, section: str) -> str:
    return f"{source} §{section}"


def citation_in_expected(r: dict, expected: list[str]) -> str:
    """Auto-check: is the section TrustGuard cited one of the sections the labeller listed?
    '-' when TrustGuard cited nothing or the case lists no expected evidence."""
    if not r.get("source_id") or not expected or r["status"] == "INSUFFICIENT_EVIDENCE":
        return "-"
    return "Y" if norm_ref(r["source_id"], r["section"]) in expected else "N"


def rows_for(run_id: str, case: dict, report, gold_claims=None, gold_answer=None):
    d = report.to_dict()
    h = d.get("agent1_handoff") or {}
    expected = case.get("relevant_evidence", [])
    claims = []
    for i, r in enumerate(d["results"]):
        claims.append({
            "run_id": run_id, "case_id": case["id"], "scenario": case["scenario"], "question": case["question"],
            "agent1_answer": d["answer"], "claim_id": r["claim_id"], "claim": r["claim"], "tg_status": r["status"],
            "tg_source": r["source_id"], "tg_section": r["section"], "tg_version": r["version"],
            "citation_in_expected": citation_in_expected(r, expected), "root_cause": r.get("root_cause", ""),
            "needs_review": "Y" if r["needs_review"] else "N", "expected_evidence": "; ".join(expected),
            "key_facts": " | ".join(case.get("key_facts", [])),
            "gold_status": (gold_claims[i] if gold_claims and i < len(gold_claims) else ""), "notes": ""})
    corr = d.get("correction") or {}
    answer = {
        "run_id": run_id, "case_id": case["id"], "scenario": case["scenario"], "question": case["question"],
        "agent1_answer": d["answer"], "agent1_model": h.get("model", "fixed answer"),
        "agent1_sources": "; ".join(f"{s['source_id']} §{s['section']} ({s['status']})" for s in h.get("sources", [])),
        "tg_model": d.get("trustguard_model", ""), "tg_overall": d["overall"], "tg_message": d["overall_message"],
        "tg_missing": " | ".join((d.get("completeness") or {}).get("missing", [])),
        "correction_status": corr.get("status", ""), "correction_text": corr.get("text", ""),
        "reverification": corr.get("reverification", ""), "agent1_s": d["timings"].get("agent1_s", ""),
        "trustguard_s": d["timings"].get("trustguard_total_s", ""), "key_facts": " | ".join(case.get("key_facts", [])),
        "expected_result": case.get("expected_result", ""), "gold_answer_ok": "", "gold_missing_step": "",
        "gold_correction_ok": "", "notes": ""}
    if gold_answer:
        answer.update(gold_answer)
    return claims, answer


def write_csv(path: Path, fields: list[str], rows: list[dict]) -> None:
    # utf-8-sig so Excel opens it with the right encoding ($, §, quotes)
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def read_csv(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


SAVED_ARGS = ("runs", "limit", "only", "delay", "tg_model", "agent1_model", "agent1_scope", "mock", "tfidf",
              "no_nli", "reuse")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--live", action="store_true", help="Agent 1 answers live (default)")
    mode.add_argument("--controlled", action="store_true", help="fixed answers from controlled_cases.json")
    mode.add_argument("--reuse", metavar="DIR", help="re-check Agent 1 answers saved in an earlier live run")
    mode.add_argument("--resume", metavar="DIR", help="continue a stopped run in DIR (same settings)")
    p.add_argument("--runs", type=int, default=1, help="times to ask each live question (default 1)")
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--only", default="", help="comma-separated case ids")
    p.add_argument("--delay", type=float, default=0.0, help="seconds to wait between questions")
    p.add_argument("--tg-model", default="", help="override TrustGuard's model (ablation)")
    p.add_argument("--agent1-model", default="")
    p.add_argument("--agent1-scope", default=config.AGENT1_KB_SCOPE, choices=["all", "approved", "none"])
    p.add_argument("--mock", action="store_true", help="offline mock LLM (plumbing check only)")
    p.add_argument("--tfidf", action="store_true", help="keyword retriever instead of embeddings")
    p.add_argument("--no-nli", action="store_true")
    p.add_argument("--out", default="", help="output folder name")
    args = p.parse_args()

    # ---- resume: same folder, same settings, skip what's already done ----
    resume_dir = Path(args.resume) if args.resume else None
    if resume_dir:
        info_path = resume_dir / "run_info.json"
        if not info_path.exists():
            print(f"No run_info.json in {resume_dir}; is that a results folder?")
            return 1
        saved = json.loads(info_path.read_text(encoding="utf-8"))
        for k, v in saved.get("args", {}).items():
            setattr(args, k, v)
        kind = saved["kind"]
        out = resume_dir
    else:
        kind = "controlled" if args.controlled else "reuse" if args.reuse else "live"

    provider = "mock" if args.mock else config.LLM_PROVIDER
    tg_llm = get_client(provider, model=args.tg_model or None)
    chunks = load_knowledge_base()
    embedder, warning = make_embedder("tfidf" if args.tfidf else "sentence-transformers")
    if warning:
        print("WARNING:", warning)
    retriever = EvidenceRetriever(chunks, embedder)
    nli = None if args.no_nli else NLIChecker()
    if nli is not None and not nli.available:
        print("NOTE:", nli.error)

    if kind == "controlled":
        cases = json.loads((EVAL_DIR / "controlled_cases.json").read_text(encoding="utf-8"))["cases"]
    else:
        cases = json.loads((EVAL_DIR / "questions.json").read_text(encoding="utf-8"))["questions"]
    if args.only:
        wanted = {c.strip() for c in args.only.split(",")}
        cases = [c for c in cases if c["id"] in wanted]
    if args.limit:
        cases = cases[:args.limit]

    reuse_answers, assistant = {}, None
    if kind == "reuse":
        for row in read_csv(Path(args.reuse) / "answers_to_label.csv"):
            reuse_answers[row["run_id"]] = row
    elif kind == "live":
        a1_llm = get_client(provider, model=args.agent1_model or config.AGENT1_MODEL or None)
        assistant = BankingAssistant(a1_llm, build_agent1_retriever(chunks, embedder, args.agent1_scope),
                                     kb_scope=args.agent1_scope)

    if not resume_dir:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        out = EVAL_DIR / "results" / (args.out or f"{stamp}_{kind}{'_mock' if args.mock else ''}")
        if out.exists() and any(out.iterdir()):
            print(f"{out} already has results. Use --resume {out} to continue it, or pick another --out name.")
            return 1
        out.mkdir(parents=True, exist_ok=True)
        meta = {"kind": kind, "started": stamp, "provider": provider, "trustguard_model": getattr(tg_llm, "model", ""),
                "agent1_model": getattr(assistant.llm, "model", "") if assistant else "",
                "agent1_scope": args.agent1_scope, "retriever": embedder.label,
                "nli": (nli.model_name if nli and nli.available else "unavailable"), "runs": args.runs,
                "reused_from": args.reuse or "", "args": {k: getattr(args, k) for k in SAVED_ARGS}}
        (out / "run_info.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
        print(json.dumps({k: v for k, v in meta.items() if k != "args"}, indent=2))

    if kind == "reuse":
        by_case = {c["id"]: c for c in cases}
        jobs = [(rid, by_case[row["case_id"]], row) for rid, row in reuse_answers.items() if row["case_id"] in by_case]
    else:
        jobs = [(f"{c['id']}-r{n + 1}", c, None) for c in cases for n in range(args.runs if kind == "live" else 1)]

    # Rows already saved (resume) are kept as they are, including any labels typed in.
    claim_rows = read_csv(out / "claims_to_label.csv") if (out / "claims_to_label.csv").exists() else []
    answer_rows = read_csv(out / "answers_to_label.csv") if (out / "answers_to_label.csv").exists() else []
    done = {r["run_id"] for r in answer_rows}
    todo = [j for j in jobs if j[0] not in done]
    if resume_dir:
        print(f"Resuming {out.name}: {len(done)} done, {len(todo)} to go.")

    def save() -> None:
        write_csv(out / "claims_to_label.csv", CLAIM_FIELDS, claim_rows)
        write_csv(out / "answers_to_label.csv", ANSWER_FIELDS, answer_rows)

    errors, quota_errors, stopped = [], 0, ""
    resume_cmd = f"python eval/run_eval.py --resume {out.relative_to(ROOT) if out.is_relative_to(ROOT) else out}"
    try:
        with open(out / "runs.jsonl", "a", encoding="utf-8") as runs_file:
            for i, (run_id, case, reused) in enumerate(todo, 1):
                print(f"[{len(done) + i}/{len(jobs)}] {run_id}: {case['question'][:70]}")
                try:
                    if kind == "live":
                        report = run_two_agent(case["question"], assistant, retriever, tg_llm, nli=nli)
                    elif kind == "controlled":
                        report = run_pipeline(case["question"], case["answer"], retriever, tg_llm, nli=nli)
                    else:
                        report = run_pipeline(case["question"], reused["agent1_answer"], retriever, tg_llm, nli=nli)
                        report.handoff = AgentHandoff(question=case["question"], answer=reused["agent1_answer"],
                                                      agent_name="Banking AI Assistant (reused)",
                                                      model=reused["agent1_model"], kb_scope="")
                    quota_errors = 0
                except Exception as e:  # keep going; failures are part of the evaluation
                    errors.append({"run_id": run_id, "error": f"{type(e).__name__}: {e}"})
                    print(f"    ERROR {type(e).__name__}: {e}")
                    if isinstance(e, LLMError) and ("rate limit" in str(e).lower() or "quota" in str(e).lower()):
                        quota_errors += 1
                        if quota_errors >= 3:
                            stopped = ("3 rate-limit errors in a row: the daily quota is probably used up "
                                       "(it resets at midnight Pacific time, about 4 pm in Singapore).")
                            break
                        time.sleep(60)  # per-minute limit: wait it out once
                    else:
                        time.sleep(max(args.delay, 5 if isinstance(e, LLMError) else 0))
                    continue
                gold_claims = case.get("expected") if kind == "controlled" else None
                gold_answer = None
                if kind == "controlled":
                    ok = all(s == "SUPPORTED" for s in case["expected"]) and not case["expected_missing_step"]
                    gold_answer = {"gold_answer_ok": "Y" if ok else "N",
                                   "gold_missing_step": "Y" if case["expected_missing_step"] else "N"}
                    if len(report.results) != len(case["expected"]):
                        print(f"    ! extracted {len(report.results)} claims, expected {len(case['expected'])}: "
                              "check claim-level gold in the CSV by hand")
                if kind == "reuse":
                    gold_answer = {k: reused.get(k, "") for k in ("gold_answer_ok", "gold_missing_step")}
                claims, answer = rows_for(run_id, case, report, gold_claims, gold_answer)
                claim_rows.extend(claims)
                answer_rows.append(answer)
                runs_file.write(json.dumps({"run_id": run_id, "case_id": case["id"], **report.to_dict()},
                                           default=str) + "\n")
                runs_file.flush()
                save()  # after EVERY question, so stopping loses nothing
                print(f"    {report.overall[0]:7} {report.overall[1][:90]}")
                if args.delay:
                    time.sleep(args.delay)
    except KeyboardInterrupt:
        stopped = "Stopped by you (Ctrl+C)."
    save()
    if errors:
        old = json.loads((out / "errors.json").read_text(encoding="utf-8")) if (out / "errors.json").exists() else []
        (out / "errors.json").write_text(json.dumps(old + errors, indent=2), encoding="utf-8")

    remaining = len([j for j in jobs if j[0] not in {r["run_id"] for r in answer_rows}])
    print(f"\nSaved to {out}  ({len(answer_rows)}/{len(jobs)} done)")
    if stopped or remaining:
        print(f"{stopped} {remaining} question(s) not finished yet (including any that errored).")
        print(f"To continue later (finished questions are kept):\n    {resume_cmd}")
        return 0

    from compute_metrics import compute_and_write  # noqa: E402  (same folder)
    compute_and_write([out])
    if kind == "live":
        print("\nNext: fill gold_status in claims_to_label.csv and the gold_* columns in answers_to_label.csv,\n"
              f"then run: python eval/compute_metrics.py {out.relative_to(ROOT) if out.is_relative_to(ROOT) else out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
