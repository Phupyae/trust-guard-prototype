"""Policy validation — WHICH version of a policy applies, on WHICH date.

Why this is plain code and not the LLM's job: "is v3.0 in effect on 16 Nov 2026?" is
a date comparison. Code can't get it wrong; a language model reading two versions of
the same SOP side by side can (and that is exactly the mistake Agent 1 tends to make).

How it works
  * Every document has metadata: family (all versions of one policy share it),
    status, effective_date and expiry_date.
  * A document is IN EFFECT on a date if it is governed (Approved or Superseded),
    effective_date <= date, and (no expiry_date or date <= expiry_date).
  * The "as-of date" is today, unless the employee's question names a date
    ("in March 2025", "on 1/2/2025", "last year"). Then TrustGuard checks the answer
    against the version that applied THEN, and says so.

Superseded documents are kept in the repository (a real document management system
keeps history) so TrustGuard can explain "the assistant's figure comes from v2.1,
which stopped applying on 30 Jun 2026".
"""
import re
from dataclasses import dataclass, field
from datetime import date, timedelta

import config

MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august",
     "september", "october", "november", "december"], 1)}
MONTHS.update({k[:3]: v for k, v in list(MONTHS.items())})
MONTHS["sept"] = 9


def parse_date(value) -> date | None:
    if not value:
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


def fmt(d: date | None) -> str:
    return f"{d.day} {d:%b %Y}" if d else "no end date"  # %-d isn't supported on Windows


def _last_day_of_month(y: int, m: int) -> date:
    return (date(y + (m == 12), m % 12 + 1, 1) - timedelta(days=1))


def detect_as_of(question: str, today: date) -> tuple[date, str]:
    """Return (as_of_date, note). note == "" when the question names no date.

    Supported: "15 March 2025", "March 15, 2025", "15/03/2025" (day first, as in
    Singapore), "March 2025", "in 2025", "last year". Deliberately simple: anything
    else falls back to today, which is the right default for "what is the rule?".
    """
    q = question.lower()
    m_names = "|".join(sorted(MONTHS, key=len, reverse=True))

    def result(d: date, said: str) -> tuple[date, str]:
        if d > today:
            return today, (f"The question mentions {said}, which is in the future. Future policy changes "
                           "can't be known, so TrustGuard used the policies in effect today.")
        return d, f"The question asks about {said}, so TrustGuard used the policies in effect on {fmt(d)}."

    try:
        m = re.search(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+({m_names})\.?,?\s+(20\d\d)\b", q)
        if m:
            d = date(int(m.group(3)), MONTHS[m.group(2)], int(m.group(1)))
            return result(d, fmt(d))
        m = re.search(rf"\b({m_names})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(20\d\d)\b", q)
        if m:
            d = date(int(m.group(3)), MONTHS[m.group(1)], int(m.group(2)))
            return result(d, fmt(d))
        m = re.search(r"(?<![\d$,.])(\d{1,2})[/.-](\d{1,2})[/.-](20\d\d)\b", q)
        if m:
            d = date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
            return result(d, fmt(d))
        m = re.search(rf"\b({m_names})\.?\s+(20\d\d)\b", q)
        if m:
            y, mo = int(m.group(2)), MONTHS[m.group(1)]
            d = _last_day_of_month(y, mo)
            if y == today.year and mo == today.month:
                d = today
            return result(d, f"{m.group(1).capitalize()} {y}")
    except ValueError:  # e.g. 31/02/2025
        return today, "The question mentions a date that doesn't exist, so TrustGuard used today's date."
    if re.search(r"\blast year\b", q):
        y = today.year - 1
        return date(y, 12, 31), f"The question asks about last year ({y}), so TrustGuard used the policies in effect on 31 Dec {y}."
    m = re.search(r"(?<![\d$,.])\b(20\d\d)\b(?![\d,])", q)
    if m:
        y = int(m.group(1))
        if y < today.year:
            return date(y, 12, 31), (f"The question asks about {y}, so TrustGuard used the policies in "
                                     f"effect at the end of {y} (31 Dec {y}).")
        if y > today.year:
            return result(date(y, 1, 1), str(y))
    return today, ""


class PolicyRegistry:
    """The document management system's view of the repository."""

    def __init__(self, metadata: list[dict]):
        self.docs = {d["document_id"]: d for d in metadata}

    def is_governed(self, doc_id: str) -> bool:
        d = self.docs.get(doc_id)
        return bool(d) and d["status"] in config.GOVERNED_STATUSES

    def in_effect(self, doc_id: str, as_of: date) -> bool:
        d = self.docs.get(doc_id)
        if not d or d["status"] not in config.GOVERNED_STATUSES:
            return False
        start, end = parse_date(d["effective_date"]), parse_date(d.get("expiry_date"))
        return bool(start) and start <= as_of and (end is None or as_of <= end)

    def versions(self, family: str) -> list[dict]:
        docs = [d for d in self.docs.values() if (d.get("family") or d["document_id"]) == family]
        return sorted(docs, key=lambda d: d["effective_date"])

    def version_check(self, doc_id: str, as_of: date) -> str:
        """One sentence for derivation step 2: which version applies and what it replaced."""
        d = self.docs[doc_id]
        start = parse_date(d["effective_date"])
        text = f"Version {d['version']} (effective {fmt(start)}) is the version in effect on {fmt(as_of)}."
        others = [o for o in self.versions(d.get("family") or doc_id) if o["document_id"] != doc_id]
        older = [o for o in others if o["effective_date"] < d["effective_date"]]
        newer = [o for o in others if o["effective_date"] > d["effective_date"]]
        if older:
            o = older[-1]
            text += (f" Version {o['version']} ({fmt(parse_date(o['effective_date']))} to "
                     f"{fmt(parse_date(o.get('expiry_date')))}) no longer applies.")
        if newer:
            n = newer[0]
            text += f" A later version {n['version']} takes effect on {fmt(parse_date(n['effective_date']))}."
        return text


@dataclass
class PolicyContext:
    """Everything TrustGuard needs to know about dates for one verification."""
    registry: PolicyRegistry
    as_of: date = field(default_factory=date.today)
    as_of_note: str = ""

    @classmethod
    def for_question(cls, registry: PolicyRegistry, question: str, today: date | None = None) -> "PolicyContext":
        as_of, note = detect_as_of(question, today or date.today())
        return cls(registry=registry, as_of=as_of, as_of_note=note)

    def current(self, chunk) -> bool:
        return self.registry.in_effect(chunk.document_id, self.as_of)

    def outdated(self, chunk) -> bool:
        return self.registry.is_governed(chunk.document_id) and not self.current(chunk)
