"""Basic error logging and feedback storage, as append-only JSON Lines files in logs/.

  verifications.jsonl   one line per verified answer (summary, for analysis)
  failures.jsonl        anything worth a second look: errors, contradictions,
                        corrections that failed re-verification, needs-review flags
  blocked_inputs.jsonl  inputs stopped by the input checks (with personal data masked)
  feedback.jsonl        employee feedback on verification results

Why JSONL: one line per event, so writing never corrupts earlier records, and the files
open directly in pandas / Excel for the evaluation write-up. No database server needed.
Questions are logged only AFTER personal data has been masked by input_guard.
"""
import json
import threading
from datetime import datetime, timezone
from pathlib import Path

import config

_lock = threading.Lock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def write(stream: str, record: dict, log_dir: Path | None = None) -> None:
    """Never raises: logging must not break the demo."""
    try:
        d = Path(log_dir or config.LOG_DIR)
        d.mkdir(parents=True, exist_ok=True)
        line = json.dumps({"time": _now(), **record}, ensure_ascii=False, default=str)
        with _lock, open(d / f"{stream}.jsonl", "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def read(stream: str, log_dir: Path | None = None) -> list[dict]:
    path = Path(log_dir or config.LOG_DIR) / f"{stream}.jsonl"
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


def log_report(report, mode: str = "", log_dir: Path | None = None) -> None:
    """One summary line per verification, plus a failure line when something needs a look."""
    level, message = report.overall
    summary = {
        "turn_id": report.turn_id, "question": report.question, "answer": report.answer, "overall": level,
        "overall_message": message, "counts": report.counts, "as_of": str(report.as_of),
        "missing": [e.element for e in report.completeness.missing] if report.completeness else [],
        "correction": report.correction.to_dict() if report.correction else None,
        "timings": report.timings, "agent1_model": report.handoff.model if report.handoff else "",
        "trustguard_model": report.trustguard_model, "mode": mode,
    }
    write("verifications", summary, log_dir)
    reasons = []
    if level == "error":
        reasons.append("contradiction")
    if report.completeness and report.completeness.missing:
        reasons.append("incomplete_answer")
    if report.needs_review:
        reasons.append("needs_review")
    if report.correction and report.correction.reverification == "not_confirmed":
        reasons.append("correction_not_confirmed")
    if reasons:
        write("failures", {"type": "verification_finding", "reasons": reasons, **summary}, log_dir)


def log_error(where: str, error: Exception, question: str = "", log_dir: Path | None = None) -> None:
    write("failures", {"type": "system_error", "where": where, "error": f"{type(error).__name__}: {error}",
                       "question": question}, log_dir)


def log_feedback(turn_id: str, rating: str, reason: str = "", comment: str = "", report=None,
                 log_dir: Path | None = None) -> None:
    write("feedback", {"turn_id": turn_id, "rating": rating, "reason": reason, "comment": comment,
                       "question": getattr(report, "question", ""),
                       "overall": report.overall[0] if report is not None else ""}, log_dir)
