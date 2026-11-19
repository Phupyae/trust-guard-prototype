"""Past chats: each conversation is saved as one JSON file in logs/chats/, so "New chat" no longer
throws the old one away and it can be reopened from the sidebar.

Saved after every answer. Questions are stored AFTER input_guard has masked personal data (the
same text the logs keep). Chat ids are generated here and checked against a strict pattern before
any file is opened, so a crafted id can't point outside logs/chats/.
"""
from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

import config
from modules.pipeline import report_from_dict

_ID = re.compile(r"^[0-9a-f]{12}$")


def new_id() -> str:
    return uuid.uuid4().hex[:12]


def _dir(log_dir: Path | None = None) -> Path:
    return Path(log_dir or config.LOG_DIR) / "chats"


def _path(chat_id: str, log_dir: Path | None = None) -> Path:
    if not _ID.match(chat_id or ""):
        raise ValueError("Invalid chat id")
    return _dir(log_dir) / f"{chat_id}.json"


def _turn_to_dict(turn: dict) -> dict:
    if turn.get("kind") == "report":
        return {"kind": "report", "question": turn["question"], "report": turn["report"].to_dict()}
    return {k: v for k, v in turn.items() if k in ("kind", "question", "reply", "guard", "note")}


def _turn_from_dict(turn: dict) -> dict:
    if turn.get("kind") == "report":
        return {"kind": "report", "question": turn["question"], "report": report_from_dict(turn["report"])}
    return turn


def save(chat_id: str, turns: list[dict], log_dir: Path | None = None) -> None:
    """Never raises: saving history must not break the demo."""
    if not turns:
        return
    try:
        path = _path(chat_id, log_dir)
        path.parent.mkdir(parents=True, exist_ok=True)
        started = None
        if path.exists():
            started = json.loads(path.read_text(encoding="utf-8")).get("started")
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        data = {"id": chat_id, "started": started or now, "updated": now, "title": turns[0]["question"][:80],
                "turns": [_turn_to_dict(t) for t in turns]}
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, default=str), encoding="utf-8")
        tmp.replace(path)  # write-then-rename, so a crash never leaves half a file
    except Exception:
        pass


def load(chat_id: str, log_dir: Path | None = None) -> list[dict]:
    data = json.loads(_path(chat_id, log_dir).read_text(encoding="utf-8"))
    return [_turn_from_dict(t) for t in data.get("turns", [])]


def list_chats(log_dir: Path | None = None) -> list[dict]:
    """Newest first: id, title, updated, number of questions."""
    out = []
    d = _dir(log_dir)
    if not d.exists():
        return out
    for p in d.glob("*.json"):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if _ID.match(data.get("id", "")):
                out.append({"id": data["id"], "title": data.get("title", ""), "updated": data.get("updated", ""),
                            "questions": len(data.get("turns", []))})
        except (OSError, ValueError):
            continue
    return sorted(out, key=lambda c: c["updated"], reverse=True)
