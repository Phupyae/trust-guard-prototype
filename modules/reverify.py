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
    for topic in entry.get("required", []):
        if topic in policy_rules._NO_REQUIREMENT and _says_not_required(sentence.text, topic):
            problems.append(f"says {topic} {_be(topic)} not needed; the rules table says {_it(topic)} required")
    for topic in entry.get("not_required", []):
        if _says_required(sentence.text, topic):
            problems.append(f"says {topic} {_be(topic)} needed; the rules table says {_it(topic)} not required")
    if problems:
        return {"result": "fail", "detail": "The sentence " + "; ".join(problems) + "."}
    return {"result": "pass", "detail": "Amounts, periods, approvers and requirements match the rules table."}


def check_entailment(sentence, chunk, nli) -> dict:
    """Method C."""
    if nli is None:
        return {"result": "unavailable", "detail": "Entailment model not configured; method C was skipped."}
    if chunk is None:
        return {"result": "fail", "detail": "No valid section to compare with."}
    out = nli.check(chunk.text, sentence.text)
    label = out.get("label")
    if label == "unavailable":
        return {"result": "unavailable", "detail": out.get("note", "Method C was skipped.")}
    detail = {"entailment": "The policy text implies this sentence",
              "neutral": "The policy text does not clearly imply this sentence",
              "contradiction": "The policy text contradicts this sentence"}[label]
    probs = ", ".join(f"{k} {v:.2f}" for k, v in out.items() if k != "label")
    return {"result": {"entailment": "pass", "neutral": "uncertain", "contradiction": "fail"}[label],
            "detail": f"{detail} ({probs})."}


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
