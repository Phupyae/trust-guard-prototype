"""Deterministic checks that run AFTER the LLM's judgement.

Why have rules at all if the LLM already judged? LLMs are good at meaning but can
slip on exact facts — e.g. reading "$150" and still agreeing with "$200". Plain
Python never misreads a number. So the rules double-check the facts that matter
most in banking policy: amounts/durations, and whether something is required.

Design principle: rules can only make the system MORE cautious, never more confident.
  * Rule agrees with the LLM   -> we note the confirmation.
  * Rule disagrees with a "SUPPORTED" verdict -> downgrade + flag for human review.
  * Rules never turn an LLM "CONTRADICTED"/"INSUFFICIENT" into "SUPPORTED".
They're deliberately simple; they catch common, high-impact errors, not every error.
"""
import re

# --- Quote check -------------------------------------------------------------

def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip(" .")


def quote_in_passage(quote: str, passage: str) -> bool:
    """Did the model quote text that actually exists in the source? If not, the
    'evidence' may be invented and must not be shown as a citation."""
    return bool(quote.strip()) and _norm(quote) in _norm(passage)


# --- Numeric check -----------------------------------------------------------

_UNIT_PATTERNS = {
    "money": r"(?:\$|sgd\s?|s\$)\s?(\d[\d,]*(?:\.\d+)?)|(\d[\d,]*(?:\.\d+)?)\s?(?:dollars|sgd)",
    "percent": r"(\d+(?:\.\d+)?)\s?(?:%|percent)",
    "working days": r"(\d+)\s?working days?",
    "days": r"(\d+)\s?(?:calendar )?days?(?! of the)",
    "nights": r"(\d+)\s?nights?",
    "hours": r"(\d+)\s?hours?",
    "weeks": r"(\d+)\s?weeks?",
    "years": r"(\d+)\s?years?",
}


def extract_quantities(text: str) -> dict[str, set[float]]:
    text = text.lower()
    # "10 working days" must not ALSO count as plain "10 days"
    found: dict[str, set[float]] = {}
    for unit, pattern in _UNIT_PATTERNS.items():
        scan = text
        if unit == "days":
            scan = re.sub(r"\d+\s?working days?", "", text)
        for match in re.finditer(pattern, scan):
            raw = next(g for g in match.groups() if g)
            found.setdefault(unit, set()).add(float(raw.replace(",", "")))
    return found


def numeric_check(claim: str, evidence: str) -> tuple[str, str]:
    """Returns (result, message) where result is 'match', 'mismatch' or 'n/a'."""
    claim_q, ev_q = extract_quantities(claim), extract_quantities(evidence)
    mismatches, matches = [], []
    for unit, values in claim_q.items():
        if unit not in ev_q:
            continue  # evidence says nothing about this kind of quantity
        for v in values:
            (matches if v in ev_q[unit] else mismatches).append((unit, v))
    fmt = lambda u, v: f"${v:,.0f}" if u == "money" else f"{v:g} {u}"
    if mismatches:
        claimed = ", ".join(fmt(u, v) for u, v in mismatches)
        policy = ", ".join(fmt(u, x) for u, _ in mismatches for x in sorted(ev_q[u]))
        return "mismatch", f"Numeric check: claim states {claimed}; evidence states {policy}."
    if matches:
        return "match", "Numeric check: " + ", ".join(fmt(u, v) for u, v in matches) + " matches the evidence."
    return "n/a", ""


# --- Requirement check -------------------------------------------------------

_NO_REQUIREMENT = {
    "approval": [
        r"\b(?:automatically|auto)[ -]?approv",
        r"\bapproved automatically",
        r"\bno (?:manager |prior |further )?approval",
        r"\bwithout (?:any )?(?:manager |prior )?approval",
        r"approval (?:is|isn't|is not) (?:not )?(?:needed|required|necessary)",
        r"\b(?:do|does|don't|doesn't)(?: not)? (?:need|require) (?:any )?(?:manager )?approval",
    ],
    "receipts": [
        r"\bno receipts?\b",
        r"\bwithout (?:any )?receipts?",
        r"receipts? (?:are|is|aren't|isn't) (?:not )?(?:needed|required|necessary)",
        r"\b(?:do|does|don't|doesn't)(?: not)? (?:need|require) (?:any )?receipts?",
    ],
}
_REQUIRES = {
    "approval": r"(?:require[sd]?|must (?:be )?(?:obtain|approv)\w*|need[s]?) [\w\s]{0,30}approv|approv\w* [\w\s]{0,20}(?:is|are) required|no [\w\s]{0,40}approved automatically",
    "receipts": r"receipts? (?:must|are required|is required)|(?:attach|require)\w* [\w\s]{0,30}receipts?",
}
_DOUBLE_NEGATIVE = r"\b(?:no|not|never)\b[^.]{0,40}\bautomatic"


def requirement_check(claim: str, evidence: str) -> tuple[str, str]:
    """Flags the classic dangerous error: the answer says something is NOT required
    (approval, receipts) when the policy says it IS."""
    c, e = claim.lower(), evidence.lower()
    for topic, patterns in _NO_REQUIREMENT.items():
        says_not_required = any(re.search(p, c) for p in patterns)
        if topic == "approval" and re.search(_DOUBLE_NEGATIVE, c):
            says_not_required = False  # "no claim is approved automatically" = approval IS required
        if says_not_required and re.search(_REQUIRES[topic], e):
            return "mismatch", f"Requirement check: claim says {topic} is not required; evidence says it is."
    return "n/a", ""
