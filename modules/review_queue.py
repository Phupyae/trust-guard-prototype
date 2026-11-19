"""Human review: when TrustGuard can't give a clear ✓, the employee can send the case to the
Branch Operations Head, who confirms or corrects the answer. The employee then sees the decision
in the chat.

Stored as append-only events in logs/reviews.jsonl (same approach as event_log): a "requested"
event when the employee asks, then a "decided" event from the reviewer. The current state of a
case is its latest event, so nothing is ever overwritten and the file doubles as the audit trail.

In the demo the review queue is a page in the same app. In production it would be the Branch
Operations Head's (or compliance team's) work queue, with a notification.
"""
from __future__ import annotations

import uuid
from pathlib import Path

from modules import event_log

STREAM = "reviews"
REVIEWER = "Branch Operations Head"
DECISIONS = {
    "confirm_trustguard": "TrustGuard is right",
    "corrected": "Corrected answer",
    "agent1_correct": "The assistant's answer was correct",
}


def request(report, reason: str, log_dir: Path | None = None) -> str:
    """Opens a case for one checked answer and returns its case id (e.g. TG-3F9A2C)."""
    level, message = report.overall
    suggested = report.correction.text if report.correction and report.correction.status == "suggested" else ""
    case_id = "TG-" + uuid.uuid4().hex[:6].upper()
    event_log.write(STREAM, {
        "event": "requested", "case_id": case_id, "turn_id": report.turn_id, "reason": reason,
        "question": report.question, "answer": report.answer, "overall": level, "overall_message": message,
        "suggested_answer": suggested, "needs_review": report.needs_review, "report": report.to_dict(),
    }, log_dir)
    return case_id


def decide(case_id: str, decision: str, answer: str = "", note: str = "", log_dir: Path | None = None) -> None:
    if decision not in DECISIONS:
        raise ValueError(f"Unknown decision: {decision}")
    event_log.write(STREAM, {"event": "decided", "case_id": case_id, "decision": decision,
                             "answer": answer.strip(), "note": note.strip(), "reviewer": REVIEWER}, log_dir)


def cases(log_dir: Path | None = None) -> dict[str, dict]:
    """Every case with its current state, newest first. A case is 'waiting' until decided."""
    out: dict[str, dict] = {}
    for e in event_log.read(STREAM, log_dir):
        cid = e.get("case_id")
        if not cid:
            continue
        if e.get("event") == "requested":
            out[cid] = {**e, "status": "waiting", "requested_at": e.get("time")}
        elif e.get("event") == "decided" and cid in out:
            out[cid].update(status="decided", decision=e["decision"], decided_answer=e.get("answer", ""),
                            note=e.get("note", ""), reviewer=e.get("reviewer", REVIEWER), decided_at=e.get("time"))
    return dict(sorted(out.items(), key=lambda kv: kv[1].get("requested_at") or "", reverse=True))


def for_turn(turn_id: str, log_dir: Path | None = None) -> dict | None:
    """The latest case opened for one chat answer, if any."""
    matches = [c for c in cases(log_dir).values() if c.get("turn_id") == turn_id]
    return matches[0] if matches else None


def _norm(text: str) -> str:
    return " ".join("".join(ch.lower() if ch.isalnum() or ch in "$." else " " for ch in text or "").split())


def earlier_decision(question: str, turn_id: str, log_dir: Path | None = None) -> dict | None:
    """Feedback to staff: the newest decided case for the same question, asked earlier by anyone.
    Exact match after normalising case and punctuation, so a different question never borrows
    someone else's decision."""
    q = _norm(question)
    for c in cases(log_dir).values():  # newest first
        if c["status"] == "decided" and c.get("turn_id") != turn_id and _norm(c.get("question", "")) == q:
            return c
    return None


def answer_to_use(case: dict) -> str:
    """What the employee should rely on after the review."""
    if case.get("decision") == "corrected":
        return case.get("decided_answer", "")
    if case.get("decision") == "confirm_trustguard":
        return case.get("suggested_answer") or ""
    if case.get("decision") == "agent1_correct":
        return case.get("answer", "")
    return ""
