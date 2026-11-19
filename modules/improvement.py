"""Continuous improvement: turns what TrustGuard already logs into recurring patterns, a suggested
fix for each, a person's approve / reject decision, and a before / after count.

    01 record errors      logs/verifications.jsonl (one line per checked answer, per statement)
    02 collect feedback   logs/reviews.jsonl (reviewer decisions), logs/feedback.jsonl (thumbs)
    03 identify patterns  patterns(): group findings by kind of problem and SOP section
    04 recommend fixes    KINDS: a fixed, rule-based suggestion per kind of problem (no AI, so the
                          same pattern always gets the same suggestion and it can be audited)
    05 generate reports   report_markdown(), review_test_cases()
    human approval        decide(): logged to logs/improvements.jsonl. Nothing here changes the
                          assistant, TrustGuard or the SOPs by itself: a person approves the fix and
                          the owning team carries it out.
    monitor outcomes      each approved pattern shows how often it happened before vs after approval.
"""
from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from modules import event_log, review_queue

STREAM = "improvements"
APPROVER = "AI governance lead"

# kind -> (what went wrong, who fixes it, suggested fix)
KINDS = {
    "outdated": ("The assistant used a replaced SOP version", "AI assistant team",
                 "Remove replaced SOP versions from the assistant's search, or make it filter by effective date, so "
                 "it only reads the version in effect."),
    "wrong_rule": ("The assistant stated a rule wrongly", "AI assistant team",
                   "Check that the assistant's search finds this SOP section for these questions, and add it to the "
                   "assistant's examples."),
    "missing_step": ("Answers leave out a required step", "AI assistant team",
                     "Tell the assistant to always include this step when it answers about this policy."),
    "unconfirmed": ("TrustGuard couldn't confirm statements on this topic", "TrustGuard team and policy owner",
                    "Check whether the SOP covers this. If it does, improve TrustGuard's evidence search for this "
                    "section; if it doesn't, ask the policy owner to make the SOP clear."),
    "overruled": ("A reviewer decided TrustGuard was wrong", "TrustGuard team",
                  "Add these cases to TrustGuard's test set, find out why its check disagreed with the reviewer, "
                  "and re-run the evaluation."),
    "disputed": ("Staff said the check was wrong", "TrustGuard team",
                 "Go through these answers with a reviewer. Where staff are right, add them to TrustGuard's test set."),
}
_OUTDATED = re.compile(r"outdated|superseded|replaced|older version", re.I)


def _topic(source_title: str, section: str) -> str:
    if not source_title:
        return "No matching SOP section"
    return f"{source_title} §{section}" if section else source_title


def _pid(kind: str, key: str) -> str:
    return kind + "-" + hashlib.sha1(f"{kind}|{key}".encode()).hexdigest()[:8]


def occurrences(log_dir: Path | None = None) -> list[dict]:
    """Every finding, one row each: kind, key (what groups it), topic, time, question."""
    out = []
    for v in event_log.read("verifications", log_dir):
        t, q = v.get("time", ""), v.get("question", "")
        for c in v.get("claims") or []:
            topic = _topic(c.get("source_title", ""), c.get("section", ""))
            if c.get("status") == "CONTRADICTED":
                kind = "outdated" if _OUTDATED.search(c.get("root_cause") or "") else "wrong_rule"
                out.append({"kind": kind, "key": topic, "topic": topic, "time": t, "question": q})
            elif c.get("status") == "INSUFFICIENT_EVIDENCE":
                out.append({"kind": "unconfirmed", "key": topic, "topic": topic, "time": t, "question": q})
        for step in v.get("missing") or []:
            out.append({"kind": "missing_step", "key": step.strip().lower(), "topic": step.strip(), "time": t,
                        "question": q})
    for case in review_queue.cases(log_dir).values():
        # The reviewer said the assistant was right although TrustGuard raised a problem
        if case.get("status") == "decided" and case.get("decision") == "agent1_correct" \
                and case.get("overall") != "success":
            flagged = [r for r in (case.get("report") or {}).get("results", []) if r.get("status") != "SUPPORTED"]
            topic = _topic(flagged[0].get("source_title", ""), flagged[0].get("section", "")) if flagged \
                else "Whole answer"
            out.append({"kind": "overruled", "key": topic, "topic": topic, "time": case.get("decided_at", ""),
                        "question": case.get("question", ""), "case_id": case.get("case_id")})
    for f in event_log.read("feedback", log_dir):
        if f.get("rating") == "down":
            reason = f.get("reason") or "No reason given"
            out.append({"kind": "disputed", "key": reason, "topic": reason, "time": f.get("time", ""),
                        "question": f.get("question", "")})
    return out


def decisions(log_dir: Path | None = None) -> dict[str, dict]:
    """Latest approve / reject per pattern (append-only log, latest event wins)."""
    out = {}
    for e in event_log.read(STREAM, log_dir):
        if e.get("pattern_id"):
            out[e["pattern_id"]] = e
    return out


def decide(pattern_id: str, decision: str, note: str = "", log_dir: Path | None = None) -> None:
    if decision not in ("approved", "rejected"):
        raise ValueError(f"Unknown decision: {decision}")
    event_log.write(STREAM, {"pattern_id": pattern_id, "decision": decision, "note": note.strip(),
                             "by": APPROVER}, log_dir)


def patterns(log_dir: Path | None = None) -> list[dict]:
    """Findings grouped by kind + topic, most frequent first, with decision and before/after counts."""
    groups: dict[tuple, list] = defaultdict(list)
    for o in occurrences(log_dir):
        groups[(o["kind"], o["key"])].append(o)
    made = decisions(log_dir)
    out = []
    for (kind, key), items in groups.items():
        items.sort(key=lambda o: o["time"])
        what, owner, fix = KINDS[kind]
        pid = _pid(kind, key)
        d = made.get(pid)
        p = {"id": pid, "kind": kind, "what": what, "owner": owner, "fix": fix, "topic": items[0]["topic"],
             "count": len(items), "first": items[0]["time"], "last": items[-1]["time"],
             "questions": list(dict.fromkeys(o["question"] for o in items if o["question"]))[:3],
             "status": d["decision"] if d else "waiting", "decided_at": d.get("time") if d else None}
        if d and d["decision"] == "approved":
            p["before"] = sum(1 for o in items if o["time"] < d["time"])
            p["after"] = p["count"] - p["before"]
        out.append(p)
    order = {"waiting": 0, "approved": 1, "rejected": 2}
    return sorted(out, key=lambda p: (order[p["status"]], -p["count"], p["last"]), reverse=False)


def summary(log_dir: Path | None = None) -> dict:
    checks = event_log.read("verifications", log_dir)
    decided = [c for c in review_queue.cases(log_dir).values() if c.get("status") == "decided"]
    agreed = sum(1 for c in decided if c.get("decision") == "confirm_trustguard")
    return {"checks": len(checks), "flagged": sum(1 for v in checks if v.get("overall") != "success"),
            "reviews": len(decided), "agreed": agreed,
            "thumbs_down": sum(1 for f in event_log.read("feedback", log_dir) if f.get("rating") == "down")}


def _day(ts: str | None) -> str:
    try:
        return datetime.fromisoformat(ts).strftime("%d %b %Y")
    except (TypeError, ValueError):
        return ""


def report_markdown(log_dir: Path | None = None) -> str:
    """One-page summary for the teams who own the fixes."""
    s, ps = summary(log_dir), patterns(log_dir)
    lines = ["# TrustGuard improvement report", f"Generated {datetime.now().strftime('%d %b %Y, %H:%M')}", "",
             "## In numbers",
             f"- Answers checked: {s['checks']} (flagged: {s['flagged']})",
             f"- Reviewer decisions: {s['reviews']} (agreed with TrustGuard: {s['agreed']})",
             f"- Staff who said a check was wrong: {s['thumbs_down']}", "", "## Patterns and suggested fixes"]
    if not ps:
        lines.append("No findings logged yet.")
    for i, p in enumerate(ps, 1):
        status = {"waiting": "Waiting for approval", "rejected": f"Rejected on {_day(p['decided_at'])}",
                  "approved": f"Approved on {_day(p['decided_at'])}: {p.get('before', 0)} before, "
                              f"{p.get('after', 0)} since"}[p["status"]]
        lines += ["", f"### {i}. {p['what']}: {p['topic']}",
                  f"- Seen {p['count']} time{'s' if p['count'] != 1 else ''} ({_day(p['first'])} to {_day(p['last'])})",
                  f"- Suggested fix: {p['fix']}", f"- Owner: {p['owner']}", f"- Status: {status}"]
        lines += [f"- Example question: {q}" for q in p["questions"]]
    lines += ["", "Nothing in this report has been changed automatically. Each fix needs a person's approval, and "
                  "is then carried out by the owning team."]
    return "\n".join(lines) + "\n"


def review_test_cases(log_dir: Path | None = None) -> dict:
    """Reviewer decisions as candidate test cases for eval/, so TrustGuard is re-tested on the cases
    a person had to settle. Each still needs a label per statement before it can be scored."""
    cases = []
    for c in review_queue.cases(log_dir).values():
        if c.get("status") != "decided":
            continue
        cases.append({"id": c["case_id"], "scenario": "reviewed", "question": c.get("question", ""),
                      "answer": c.get("answer", ""), "trustguard_said": c.get("overall", ""),
                      "reviewer_decision": c.get("decision"), "reference_answer": review_queue.answer_to_use(c),
                      "reviewer_note": c.get("note", ""), "expected": "TO LABEL"})
    return {"_note": "Candidate test cases from Branch Operations Head reviews. Label the expected status of each "
                     "statement, then add them to eval/controlled_cases.json.", "cases": cases}
