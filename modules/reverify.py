"""Step 5b — re-verify TrustGuard's OWN suggested correction, using different methods.

If the same retrieve-and-ask-an-LLM method that wrote the correction also checked it,
TrustGuard would be marking its own homework. So the correction is re-checked by three
methods that do not depend on the LLM that wrote it:

  A  Citation check (code)    The cited section exists, the quote is in it word for word,
                              the section's version is in effect on the question's date,
                              and every number in the sentence appears in that section.
  B  Rules table check (code) The sentence's amounts, periods, approvers and "required /
                              not required" statements are compared with the hand-written
                              rules table for that section (knowledge_base/rules/).
  C  Entailment model (NLI)   A separate classifier checks that the section's text
                              logically implies the sentence (meaning, not just numbers).

Outcome for the whole correction:
  confirmed            every sentence passes A, B (or B has no rule for it) and C
  partially_confirmed  nothing failed, but C was unavailable or found a sentence only
                       "neutral" (not clearly implied) -> shown with a caution
  not_confirmed        any sentence failed A, B or C -> shown as "check the cited policy"
                       and logged for the team to analyse
"""
import json
import re
from functools import lru_cache

import config
from modules import policy_rules
from modules.policy_validation import PolicyContext, fmt
from modules.schemas import Correction

# How roles are written in policy text. Longest aliases are matched first and removed,
# so "Branch Manager" is never ALSO counted as a plain "manager".
ROLE_ALIASES = {
    "Branch Operations Head": ["branch operations head", "operations head"],
    "Branch Manager": ["branch manager"],
    "Regional Head": ["regional head of branch banking", "regional head"],
    "Group Compliance": ["group compliance", "compliance"],
    "Department Head": ["department head", "head of department"],
    "Customer Service Officer": ["customer service officer"],
    "direct manager": ["direct manager", "line manager", "reporting manager", "manager"],
}


def roles_in(text: str) -> set[str]:
    t = text.lower()
    found = set()
    pairs = sorted(((a, role) for role, aliases in ROLE_ALIASES.items() for a in aliases), key=lambda p: -len(p[0]))
    for alias, role in pairs:
        pattern = rf"\b{re.escape(alias)}s?\b"
        if re.search(pattern, t):
            found.add(role)
            t = re.sub(pattern, " ", t)
    return found


@lru_cache(maxsize=1)
def load_rules() -> dict:
    rules = {}
    for f in sorted(config.RULES_DIR.glob("*.json")):
        data = json.loads(f.read_text(encoding="utf-8"))
        rules[data["document_id"]] = data["sections"]
    return rules


def section_exemptions(document_id: str, section: str) -> list[str]:
    """The rules table's `exemptions` for one section ([] if none or no entry)."""
    return (load_rules().get(document_id, {}).get(section) or {}).get("exemptions", [])


def _says_not_required(sentence: str, topic: str) -> bool:
    s = sentence.lower()
    hit = any(re.search(p, s) for p in policy_rules._NO_REQUIREMENT.get(topic, []))
    if topic == "approval" and re.search(policy_rules._DOUBLE_NEGATIVE, s):
        hit = False
    return hit or bool(re.search(rf"\bno (?:further |additional )?{topic[:6]}\w* (?:is |are )?(?:needed|required)", s))


def _says_required(sentence: str, topic: str) -> bool:
    if _says_not_required(sentence, topic):
        return False
    pattern = policy_rules._REQUIRES.get(topic)
    return bool(pattern and re.search(pattern, sentence.lower()))


def _be(topic: str) -> str:
    return "are" if topic.endswith("s") else "is"


def _it(topic: str) -> str:
    return "they are" if topic.endswith("s") else "it is"


def check_citation(sentence, chunk, ctx: PolicyContext, question: str = "") -> dict:
    """Method A. Numbers that come from the employee's question (e.g. "$80,000") describe
    the case, not the policy, so they may appear in the sentence."""
    if chunk is None:
        return {"result": "fail", "detail": "The sentence does not point to a valid policy section."}
    problems = []
    if not policy_rules.quote_in_passage(sentence.quote, chunk.text):
        problems.append("the quoted text is not in the cited section word for word")
    if not ctx.current(chunk):
        problems.append(f"{chunk.document_id} is not in effect on {fmt(ctx.as_of)}")
    extra = (policy_rules.numbers_in(sentence.text) - policy_rules.numbers_in(chunk.text)
             - policy_rules.numbers_in(question))
    if extra:
        problems.append("the sentence states " + ", ".join(policy_rules._fmt(n) for n in sorted(extra))
                        + ", which the cited section does not contain")
    if problems:
        text = "; ".join(problems)
        return {"result": "fail", "detail": text[0].upper() + text[1:] + "."}
    return {"result": "pass", "detail": f"Quote found in {chunk.document_id} §{chunk.section} "
                                         f"(version {chunk.version}, in effect on {fmt(ctx.as_of)})."}


def check_rules(sentence, rules: dict, question: str = "") -> dict:
    """Method B: compare the sentence with the hand-written rules table, in code.
    Quantities that come from the employee's question describe the case and are skipped."""
    entry = rules.get(sentence.source_id, {}).get(sentence.section)
    if entry is None:
        return {"result": "not_covered",
                "detail": "No rules-table entry for this section, so method B has nothing to compare."}
    problems = []
    allowed: dict[str, set] = {}
    for q in entry.get("quantities", []):
        allowed.setdefault(q["unit"], set()).add(float(q["value"]))
    from_question = policy_rules.extract_quantities(question)
    for unit, values in policy_rules.extract_quantities(sentence.text).items():
        for v in values:
            if v in from_question.get(unit, set()):
                continue
            if v not in allowed.get(unit, set()):
                shown = f"${v:,.0f}" if unit == "money" else f"{v:g} {unit}"
                expected = ", ".join((f"${x:,.0f}" if unit == "money" else f"{x:g}") for x in sorted(allowed.get(unit, [])))
                problems.append(f"states {shown}; the rules table has " + (expected or f"no {unit} value") + " for this section")
    section_roles = set(entry.get("roles", []))
    named = roles_in(sentence.text)
    if named - section_roles:
        problems.append("names " + ", ".join(sorted(named - section_roles)) + ", which this section does not")
    if entry.get("all_roles_required") and (named & section_roles) and "approv" in sentence.text.lower():
        missing = section_roles - named
        if missing:
            problems.append("leaves out required approver(s): " + ", ".join(sorted(missing)))
    # Exemptions: items the section itself says are NOT subject to its requirements
    # ("The daily allowance does not require receipts."). A sentence about an exempt item
    # may say the step isn't needed - unless it generalises ("any/all/every expense").
    exempt = policy_rules.names_exempt_item(sentence.text, entry.get("exemptions"))
    for topic in entry.get("required", []):
        if topic in policy_rules._NO_REQUIREMENT and _says_not_required(sentence.text, topic) and not exempt:
            problems.append(f"says {topic} {_be(topic)} not needed; the rules table says {_it(topic)} required")
    for topic in entry.get("not_required", []):
        if _says_required(sentence.text, topic):
            problems.append(f"says {topic} {_be(topic)} needed; the rules table says {_it(topic)} not required")
    if problems:
        return {"result": "fail", "detail": "The sentence " + "; ".join(problems) + "."}
    return {"result": "pass", "detail": "Amounts, periods, approvers and requirements match the rules table."}


# Connective words make the small NLI model read a sentence as pointing at some OTHER fact
# the premise doesn't state: "The customer must ALSO give 1 business day of notice" scored
# 0.04 entailment, the same sentence without "also" 0.99. Only standalone connectives are
# removed: "in addition to", "as well as" and "too high" keep their meaning and stay.
_CONNECTIVES = [
    (r"^\s*(?:also|additionally|in addition(?!\s+to\b))\s*,?\s+", ""),      # sentence-initial
    (r",?\s+(?:also|additionally)\b(?:\s*,(?=\s))?", ""),                   # "must also give"
    (r",?\s+in addition\b(?!\s+to\b)(?:\s*,(?=\s))?", ""),                  # "..., in addition, ..."
    (r",?\s+as well\b(?!\s+as\b)(?:\s*,(?=\s))?", ""),                      # "... notice as well."
    (r",\s*too(?=\s*[.!?]?\s*$)", ""),                                      # trailing ", too." only
]


def strip_connectives(text: str) -> tuple[str, list[str]]:
    """Returns (text without standalone connectives, the connectives removed)."""
    removed, out = [], text
    for pattern, repl in _CONNECTIVES:
        for m in re.finditer(pattern, out, flags=re.IGNORECASE):
            removed.append(re.sub(r"[\s,]+", " ", m.group(0)).strip().lower())
        out = re.sub(pattern, repl, out, flags=re.IGNORECASE)
    out = re.sub(r"\s{2,}", " ", out).strip()
    if removed and out:
        out = out[0].upper() + out[1:]
    return out, removed


def check_entailment(sentence, chunk, nli) -> dict:
    """Method C. The small NLI model is unreliable with a long premise: it scored a
    sentence copied word for word from a 3-sentence section as only 0.12 entailment, but
    0.99 against the sentence itself. So the sentence is checked against the whole section
    AND against its quote (which method A proves is in the section word for word).
    Any contradiction fails; otherwise entailment by either premise passes."""
    if nli is None:
        return {"result": "unavailable", "detail": "Entailment model not configured; method C was skipped."}
    if chunk is None:
        return {"result": "fail", "detail": "No valid section to compare with."}
    hypothesis, removed = strip_connectives(sentence.text)
    outs = [nli.check(chunk.text, hypothesis)]
    quote = (sentence.quote or "").strip()
    if quote and policy_rules.quote_in_passage(quote, chunk.text) and outs[0].get("label") != "unavailable":
        outs.append(nli.check(quote, hypothesis))
    labels = [o.get("label") for o in outs]
    if "contradiction" in labels:
        out = outs[labels.index("contradiction")]
    else:
        out = max(outs, key=lambda o: o.get("entailment", 0.0))
    label = out.get("label")
    if label == "unavailable":
        return {"result": "unavailable", "detail": out.get("note", "Method C was skipped.")}
    detail = {"entailment": "The policy text implies this sentence",
              "neutral": "The policy text does not clearly imply this sentence",
              "contradiction": "The policy text contradicts this sentence"}[label]
    probs = ", ".join(f"{k} {v:.2f}" for k, v in out.items() if k != "label")
    note = (f" Checked without the connective word(s): {', '.join(dict.fromkeys(removed))}."
            if removed else "")
    return {"result": {"entailment": "pass", "neutral": "uncertain", "contradiction": "fail"}[label],
            "detail": f"{detail} ({probs}).{note}"}


# --- Band rule: a sentence that applies the policy's amount band to the question's amount ---
# NLI can't compare numbers, so "An $80,000 withdrawal requires ..." vs "Withdrawals above
# $50,000 require ..." comes back "neutral". Code can: is $80,000 inside "above $50,000"?
_MONEY = r"\$\s?(\d[\d,]*(?:\.\d+)?)"
_BAND_LOW = rf"\b(?:above|over|more than|(?<!not )exceeding)\s+{_MONEY}"
_BAND_HIGH = [rf"\b(?:up to|not exceeding|no more than|at most)\s+{_MONEY}", rf"{_MONEY}\s+or (?:less|below)"]
# "X cannot waive/approve a $300 fee": the sentence says the amount is OUTSIDE X's band.
_NEG_APPROVE = (r"\b(?:cannot|can ?not|can't|may not|must not|(?:is|are) not (?:allowed|permitted|authori[sz]ed) to)"
                r"\s+(?:\w+\s+){0,2}?(?:waive|approv|authori[sz]|process|sign off)")
_NEG_ANY = r"\b(?:not|no|never|cannot|can't|unable|neither|nor)\b"


def _num(s: str) -> float:
    return float(s.replace(",", ""))


def policy_band(text: str) -> tuple[float | None, float | None] | None:
    """(lower bound, exclusive; upper bound, inclusive) of the money band a section states,
    or None if it states none or more than one (then the rule doesn't apply)."""
    lows = {_num(m) for m in re.findall(_BAND_LOW, text, flags=re.IGNORECASE)}
    highs = {_num(m) for p in _BAND_HIGH for m in re.findall(p, text, flags=re.IGNORECASE)}
    if len(lows) > 1 or len(highs) > 1 or not (lows or highs):
        return None
    return (next(iter(lows), None), next(iter(highs), None))


def _band_text(lo, hi) -> str:
    parts = ([f"above ${lo:,.0f}"] if lo is not None else []) + ([f"up to ${hi:,.0f}"] if hi is not None else [])
    return " and ".join(parts)


def check_band(sentence, chunk, question: str) -> dict | None:
    """Replaces an UNCERTAIN method C result when the sentence's only non-policy amounts
    come from the question. Returns None when the rule doesn't apply (C stays uncertain).
    Both directions:
      the sentence applies the rule to the amount   -> the amount must be INSIDE the band
      it says a named approver cannot approve it   -> the amount must be OUTSIDE the band
    Disagreement fails. Only called after A and B passed, so the approver named is one the
    cited section names (B's role check), and every other number is the policy's own."""
    if chunk is None or not question:
        return None
    sent_q = policy_rules.extract_quantities(sentence.text)
    policy_q = policy_rules.extract_quantities(chunk.text)
    question_q = policy_rules.extract_quantities(question)
    extra = {(u, v) for u, vs in sent_q.items() for v in vs if v not in policy_q.get(u, set())}
    if not extra or any(u != "money" or v not in question_q.get("money", set()) for u, v in extra):
        return None
    band = policy_band(chunk.text)
    if band is None:
        return None
    lo, hi = band
    text = sentence.text
    if re.search(_NEG_APPROVE, text, flags=re.IGNORECASE):
        if not roles_in(text):
            return None  # "a $300 fee cannot be waived" - by whom? Not decidable in code.
        claims_inside = False
    elif re.search(_NEG_ANY, text, flags=re.IGNORECASE):
        return None  # some other negation; leave it to a person
    else:
        claims_inside = True
    amounts = sorted(v for _, v in extra)
    inside = all((lo is None or v > lo) and (hi is None or v <= hi) for v in amounts)
    shown = ", ".join(f"${v:,.0f}" for v in amounts)
    where = "inside" if inside else "outside"
    if inside == claims_inside:
        return {"result": "pass",
                "detail": f"Applies the policy band ({_band_text(lo, hi)}) to the {shown} in the question; "
                          f"band checked in code: {shown} is {where} it, as the sentence says."}
    return {"result": "fail",
            "detail": f"The sentence treats the {shown} in the question as "
                      f"{'inside' if claims_inside else 'outside'} the policy band ({_band_text(lo, hi)}), "
                      f"but code finds it is {where} it."}


def reverify(correction: Correction, chunks_by_id: dict, ctx: PolicyContext, nli=None,
             question: str = "") -> Correction:
    if correction.status != "suggested":
        return correction
    rules = load_rules()
    results = []
    for s in correction.sentences:
        chunk = chunks_by_id.get(f"{s.source_id}::{s.section}")
        s.checks = {"A_citation": check_citation(s, chunk, ctx, question),
                    "B_rules": check_rules(s, rules, question),
                    "C_entailment": check_entailment(s, chunk, nli)}
        # Band rule: only for an UNCERTAIN C (never a contradiction or a pass), and only when
        # A and B both passed, so B's role check has already ruled out the wrong approver.
        if (s.checks["C_entailment"]["result"] == "uncertain" and s.checks["A_citation"]["result"] == "pass"
                and s.checks["B_rules"]["result"] == "pass"):
            band = check_band(s, chunk, question)
            if band is not None:
                band["detail"] += f" (Entailment model alone: {s.checks['C_entailment']['detail']})"
                s.checks["C_entailment"] = band
        results.extend(c["result"] for c in s.checks.values())
    if "fail" in results:
        correction.reverification = "not_confirmed"
        correction.reverification_note = ("At least one sentence failed an independent check. Don't rely on the "
                                           "suggested answer; read the cited policy sections.")
    elif "uncertain" in results or "unavailable" in results:
        correction.reverification = "partially_confirmed"
        why = []
        if "unavailable" in results:
            why.append("the entailment model (method C) was not available")
        if "uncertain" in results:
            why.append("the entailment model could not confirm every sentence")
        correction.reverification_note = ("Citations and rules checks passed, but " + " and ".join(why)
                                          + ". Check the cited sections before acting.")
    else:
        correction.reverification = "confirmed"
        correction.reverification_note = ("Every sentence passed all three independent checks: citation, "
                                          "rules table and entailment.")
    return correction
