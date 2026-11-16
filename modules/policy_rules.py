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
    "working days": r"(\d+)\s?(?:working|business) days?",
    "days": r"(\d+)\s?(?:calendar )?days?(?! of the)",
    "nights": r"(\d+)\s?nights?",
    "hours": r"(\d+)\s?hours?",
    "weeks": r"(\d+)\s?weeks?",
    "years": r"(\d+)\s?years?",
    "months": r"(\d+)[\s-]?months?",
    "times": r"(\d+)\s?times\b",
}


def extract_quantities(text: str) -> dict[str, set[float]]:
    text = text.lower()
    # "10 working days" must not ALSO count as plain "10 days"
    found: dict[str, set[float]] = {}
    for unit, pattern in _UNIT_PATTERNS.items():
        scan = text
        if unit == "days":
            scan = re.sub(r"\d+\s?(?:working|business) days?", "", text)
        for match in re.finditer(pattern, scan):
            raw = next(g for g in match.groups() if g)
            found.setdefault(unit, set()).add(float(raw.replace(",", "")))
    return found


def case_quantities(question: str, answer: str) -> dict[str, set[float]]:
    """Quantities that describe the employee's CASE ("withdraw $80,000"): in the question
    but not stated by the answer. The claim extractor may copy them into a claim for
    context ("...for a withdrawal of $80,000"); they are not a policy value, so they must
    not be compared with the policy's thresholds. A number the answer itself states is
    still checked, even if the question also mentions it."""
    q, a = extract_quantities(question), extract_quantities(answer)
    return {u: vs - a.get(u, set()) for u, vs in q.items() if vs - a.get(u, set())}


def numeric_check(claim: str, evidence: str, ignore: dict[str, set[float]] | None = None) -> tuple[str, str]:
    """Returns (result, message) where result is 'match', 'mismatch' or 'n/a'.
    `ignore`: quantities to skip, e.g. case_quantities() from the question."""
    claim_q, ev_q = extract_quantities(claim), extract_quantities(evidence)
    ignore = ignore or {}
    mismatches, matches = [], []
    for unit, values in claim_q.items():
        if unit not in ev_q:
            continue  # evidence says nothing about this kind of quantity
        for v in values - ignore.get(unit, set()):
            (matches if v in ev_q[unit] else mismatches).append((unit, v))
    fmt = lambda u, v: f"${v:,.0f}" if u == "money" else f"{v:g} {u}"
    if mismatches:
        claimed = ", ".join(fmt(u, v) for u, v in mismatches)
        policy = ", ".join(fmt(u, x) for u, _ in mismatches for x in sorted(ev_q[u]))
        return "mismatch", f"Numeric check: claim states {claimed}; evidence states {policy}."
    if matches:
        return "match", "Numeric check: " + ", ".join(fmt(u, v) for u, v in matches) + " matches the evidence."
    return "n/a", ""


_RATE_BASIS = r"\bper (day|night|trip|customer|month|year|week|claim|transaction)s?\b"


def rate_bases(text: str) -> set[str]:
    """What an amount is counted per: '$200 per day' and '$200 per night' are different
    rules even though the number is the same."""
    return set(re.findall(_RATE_BASIS, text.lower()))


def same_rule_numbers(claim: str, passage: str) -> bool:
    """Stricter than numeric_check()=='match': the numbers match AND, if the claim says
    what the amount is per, the passage says the same. Used to blame an old policy
    version, where a coincidental '$200' must not count."""
    if numeric_check(claim, passage)[0] != "match":
        return False
    return rate_bases(claim) <= rate_bases(passage)


# --- Extraction checks (guarding the claim-extraction AI) --------------------
# Claim extraction is also an AI writing text, so it can change, add or drop facts.
# We can't check meaning cheaply, but we CAN check numbers exactly: extraction
# should only split and reword the answer, never introduce or lose a number.

def numbers_in(text: str) -> set[float]:
    """Every number in the text, normalised ('$1,500' -> 1500.0)."""
    return {float(n.replace(",", "")) for n in re.findall(r"\d[\d,]*(?:\.\d+)?", text)}


def _fmt(n: float) -> str:
    return f"{n:,.0f}" if n == int(n) else f"{n:g}"


def extraction_check(claim: str, answer: str, question: str = "") -> list[str]:
    """Numbers in the claim that are NOT in the original answer = the extractor
    changed or invented a fact. The verdict would then be about the wrong claim.
    Numbers from the question are allowed: the extractor is told to use the question
    to make claims self-contained, so "$80,000" from the question is context, not invention."""
    invented = sorted(numbers_in(claim) - numbers_in(answer) - numbers_in(question))
    if not invented:
        return []
    return [f"Extraction check: the number(s) {', '.join(_fmt(n) for n in invented)} in this claim "
            "do not appear in the original answer. The claim may have been altered during extraction."]


def coverage_check(claims: list[str], answer: str) -> list[str]:
    """Numbers in the answer that NO claim contains = a fact may have been dropped
    and never verified. This is report-level, because the lost fact has no claim card."""
    covered = set().union(*(numbers_in(c) for c in claims)) if claims else set()
    missing = sorted(numbers_in(answer) - covered)
    if not missing:
        return []
    return [f"Coverage check: the answer mentions {', '.join(_fmt(n) for n in missing)}, "
            "but no extracted claim contains it, so that part of the answer may not have been verified."]


# --- Requirement check -------------------------------------------------------

_NO_REQUIREMENT = {
    "approval": [
        r"\b(?:automatically|auto)[ -]?approv",
        r"\bapproved automatically",
        r"\bno (?:manager |prior |further )?approval",
        r"\bwithout (?:any )?(?:manager |prior )?approval",
        # The negation must be present: "approval is required" is the OPPOSITE of this.
        # (An earlier version made "not" optional, so "approval is required from both..."
        # was read as "approval is not required".)
        r"approval (?:is not|isn't|are not|aren't) (?:needed|required|necessary)",
        r"\b(?:do|does|don't|doesn't)(?: not)? (?:need|require) (?:any )?(?:manager )?approval",
    ],
    "receipts": [
        r"\bno receipts?\b",
        r"\bwithout (?:any )?receipts?",
        r"receipts? (?:are not|is not|aren't|isn't) (?:needed|required|necessary)",
        r"\b(?:do|does|don't|doesn't)(?: not)? (?:need|require) (?:any )?receipts?",
    ],
}
_REQUIRES = {
    "approval": r"(?:require[sd]?|must (?:be )?(?:obtain|approv)\w*|need[s]?) [\w\s]{0,30}approv|approv\w* [\w\s]{0,20}(?:is|are) required|no [\w\s]{0,40}approved automatically",
    "receipts": r"receipts? (?:must|are required|is required)|(?:attach|require)\w* [\w\s]{0,30}receipts?",
}
_DOUBLE_NEGATIVE = r"\b(?:no|not|never)\b[^.]{0,40}\bautomatic"


def names_exempt_item(text: str, exemptions: list[str] | None) -> bool:
    """Does the text name an item the section exempts from its requirements (rules-table
    `exemptions`, e.g. "daily allowance" for TRAVEL_POLICY_V2 §5.2)? A sentence that
    generalises ("any/all/every expense, including the daily allowance") does not count:
    it is about every item, not the exempt one."""
    t = text.lower()
    return (any(re.search(rf"\b{re.escape(x.lower())}\b", t) for x in exemptions or [])
            and not re.search(r"\b(?:any|all|every)\b", t))


def requirement_check(claim: str, evidence: str, exemptions: list[str] | None = None) -> tuple[str, str]:
    """Flags the classic dangerous error: the answer says something is NOT required
    (approval, receipts) when the policy says it IS.
    `exemptions`: the cited section's rules-table exemptions. Only when the CLAIM names one
    ("The daily allowance does not require receipts.") does the check stand down, because
    the section itself says that item is exempt. Any other claim is still checked."""
    c, e = claim.lower(), evidence.lower()
    if names_exempt_item(claim, exemptions):
        return "n/a", ""
    for topic, patterns in _NO_REQUIREMENT.items():
        says_not_required = any(re.search(p, c) for p in patterns)
        if topic == "approval" and re.search(_DOUBLE_NEGATIVE, c):
            says_not_required = False  # "no claim is approved automatically" = approval IS required
        if says_not_required and re.search(_REQUIRES[topic], e):
            return "mismatch", f"Requirement check: claim says {topic} is not required; evidence says it is."
    return "n/a", ""
