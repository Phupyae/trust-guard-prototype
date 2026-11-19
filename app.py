"""TrustGuard AI — two-agent demo: Agent 1 (Banking AI Assistant) answers the employee,
Agent 2 (TrustGuard) checks that answer before the employee relies on it, shows HOW the right answer is reached from
the policy in effect, suggests a correction if needed, and re-checks that correction.

Run:  python -m streamlit run app.py

This file is presentation only. All logic lives in modules/, so what the judges see is
exactly what the tests and the evaluation script exercise.

Two display modes (mentor suggestion):
  Daily mode (default)  verified answers show a compact ✓ badge with "Show how" one click
                        away; anything wrong, missing or unconfirmed opens automatically.
  Audit mode            every step of every check is always shown (compliance review, demo).

Design principles applied (see README "Interface design"):
  Perceivability  status = icon + word + colour (never colour alone); claim and policy side by side
  Predictability  the same order every time: question → answer → check → verdict on the answer
  Learnability    plain-language helper text; a status key next to the findings
  Feedback        live stage-by-stage progress, clear input messages, errors that say what to do
  Consistency     one status vocabulary (same icon, label, colour) used everywhere
"""
import html
import re
import json
import time

import streamlit as st

import config
from modules import event_log, review_queue
from modules.banking_assistant import AssistantError, BankingAssistant, build_agent1_retriever
from modules.document_loader import load_knowledge_base, load_metadata
from modules.evidence_retriever import EvidenceRetriever, make_embedder
from modules.input_guard import RateLimiter, classify, screen
from modules.llm_client import LLMError, get_client
from modules.nli import NLIChecker
from modules.pipeline import InputError, Report, default_registry, run_pipeline
from modules.policy_validation import PolicyContext, fmt
from modules.schemas import CONTRADICTED, INSUFFICIENT_EVIDENCE, SUPPORTED
from ui_theme import MESH, apply_base_theme, icon, page_nav

st.set_page_config(page_title="TrustGuard AI", page_icon="🛡️", layout="wide", initial_sidebar_state="expanded")

# One status vocabulary for the whole app (Consistency). The icon and the word carry the
# One status vocabulary for the whole app, in plain words staff would use (Consistency).
# The icon and the word carry the meaning; colour reinforces it (Perceivability).
STATUS = {
    SUPPORTED: {"key": "ok", "icon": "✓", "label": "Matches the SOP",
                "meaning": "The SOP in effect states this."},
    CONTRADICTED: {"key": "bad", "icon": "✕", "label": "Doesn't match",
                   "meaning": "The SOP in effect says something different."},
    INSUFFICIENT_EVIDENCE: {"key": "unk", "icon": "?", "label": "Can't confirm",
                            "meaning": "No SOP in effect confirms or rules this out."},
}
VERDICT_KEY = {"error": "bad", "warning": "unk", "success": "ok", "info": "neutral"}
VERDICT_ICON = {"error": "✕", "warning": "?", "success": "✓", "info": "–"}
UNDER_LABEL = {"error": "TrustGuard: don't use this answer", "warning": "TrustGuard: use with care",
               "success": "TrustGuard: matches the current SOP", "info": "TrustGuard: nothing to check"}
RECHECK = {"confirmed": ("ok", "✓", "Re-checked against the SOP"),
           "partially_confirmed": ("unk", "?", "Partly re-checked: one check couldn't confirm a sentence"),
           "not_confirmed": ("bad", "✕", "Couldn't confirm this suggestion. Check the SOP section yourself")}
CHECK_NAMES = {"A_citation": "Quote is real", "B_rules": "Numbers match the rules table",
               "C_entailment": "Logic holds (separate model)"}
CHECK_ICON = {"pass": ("ok", "✓"), "fail": ("bad", "✕"), "uncertain": ("unk", "?"),
              "unavailable": ("neutral", "–"), "not_covered": ("neutral", "–")}

apply_base_theme()


def esc(text) -> str:
    return html.escape(str(text or ""))


def mark(key: str, symbol: str, text: str) -> str:
    """Small status mark: coloured dot with the symbol, then the word."""
    return f'<span class="tg-st tg-{key}"><b aria-hidden="true"><span>{symbol}</span></b>{esc(text)}</span>'


def chip(status: str, text: str | None = None) -> str:
    s = STATUS[status]
    return mark(s["key"], s["icon"], text or s["label"])


def raw_chip(key: str, icon: str, text: str) -> str:
    return mark(key, icon, text)


def plural(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


# ---------- top bar and header first, so the page is never blank while loading (Feedback) ----------
st.markdown('<div class="tg-hero-wrap tg-rise">' + MESH +
            '<div class="tg-top"><div class="tg-eyebrow">Northbridge Bank · Staff policy assistant</div>'
            '<h1>Ask about a <span class="tg-grad">policy</span>.</h1>'
            '<p>Agent 1 answers your question. TrustGuard checks that answer against the SOP in effect, '
            'so you know whether you can rely on it.</p>'
            '<div class="tg-chips"><span>① Agent 1 answers</span><span>② TrustGuard checks</span>'
            '<span>③ A person decides when unsure</span></div></div></div>', unsafe_allow_html=True)


# ---------- cached resources (loaded once per server, not per click) ----------
@st.cache_resource(show_spinner=False)
def get_retrievers():
    """Both agents read the same governed repository. TrustGuard's index is filtered per
    question by policy validation; Agent 1's is not (it indexes text only)."""
    chunks = load_knowledge_base()
    embedder, warning = make_embedder()
    return EvidenceRetriever(chunks, embedder), build_agent1_retriever(chunks, embedder), warning


@st.cache_resource(show_spinner=False)
def get_llms():
    return get_client(), get_client(model=config.AGENT1_MODEL or None)


@st.cache_resource(show_spinner=False)
def get_nli():
    nli = NLIChecker()
    _ = nli.available  # load now, so the first correction isn't slow
    return nli


@st.cache_data
def demo_questions():
    with open(config.KNOWLEDGE_BASE_DIR / "demo_questions.json", encoding="utf-8") as f:
        return json.load(f)["questions"]


with st.spinner("Loading policy documents and the search models. The first start can take a few minutes "
                "while the models download."):
    retriever, agent1_retriever, retrieval_warning = get_retrievers()
    nli = get_nli()
try:
    llm, agent1_llm = get_llms()
    assistant, llm_error = BankingAssistant(agent1_llm, agent1_retriever), None
except (LLMError, AssistantError) as e:
    llm, agent1_llm, assistant, llm_error = None, None, None, str(e)

if llm is None:
    st.error(f"The assistant and TrustGuard are unavailable: {llm_error}")
elif llm.name == "mock":
    st.markdown('<div class="tg-mock">Mock mode: offline keyword heuristics, not real verification. '
                'Set LLM_PROVIDER=gemini (or claude) in .env before any demo.</div>', unsafe_allow_html=True)
elif getattr(llm, "model", "") == getattr(agent1_llm, "model", None):
    st.warning("Agent 1 and TrustGuard are using the same model. Set TRUSTGUARD_MODEL and AGENT1_MODEL to "
               "different tiers in .env (see README).")

st.session_state.setdefault("turns", [])
st.session_state.setdefault("limiter", RateLimiter())


# ---------- sidebar ----------
def ask(question: str) -> None:
    st.session_state.pending_question = question


def ask_example(key: str) -> None:
    label = st.session_state.get(key)
    match = next((q for q in demo_questions() if q["label"] == label), None)
    if match:
        ask(match["question"])
    st.session_state[key] = None


with st.sidebar:
    page_nav()
    st.markdown("### View")
    audit = st.toggle("Audit mode", key="audit_mode",
                      help="Off (daily mode): a verified answer shows one line, with “Show how” one click away. "
                           "Anything wrong, missing or unconfirmed opens automatically.\n\n"
                           "On (audit mode): every step of every check is shown, plus technical details.")
    st.button("New chat", key="new_chat", icon=":material/add_comment:",
              on_click=lambda: st.session_state.update(turns=[]))

    SCOPE_TEXT = {"all": "the same SOP repository as TrustGuard, including replaced versions, without checking "
                         "versions or dates", "approved": "current SOP versions only", "none": "no documents"}
    st.markdown("### About this demo")
    with st.expander("Setup, SOPs and logs", icon=":material/info:"):
        model_name = ("offline mock (not real verification)" if llm and llm.name == "mock"
                      else getattr(llm, "model", "") if llm else "not available")
        st.markdown(f"**Agent 1** · {assistant.model if assistant else 'not available'}, reads "
                    f"{SCOPE_TEXT.get(config.AGENT1_KB_SCOPE, config.AGENT1_KB_SCOPE)}.  \n"
                    f"**TrustGuard** · {model_name}, reads only the SOP versions in effect "
                    f"({len(retriever.chunks)} sections). Logic model for re-checks: "
                    f"{'ready' if nli.available else 'unavailable'}.")
        if retrieval_warning:
            st.caption(retrieval_warning)
        from datetime import date
        registry = default_registry()
        rows = "".join(f'<div class="tg-kb">{chip(SUPPORTED, "In effect") if registry.in_effect(d["document_id"], date.today()) else raw_chip("neutral", "–", "Replaced")}'
                       f' <b>{esc(d["title"])}</b> <small>v{esc(d["version"])}</small></div>' for d in load_metadata())
        st.markdown(rows, unsafe_allow_html=True)
        counts = {k: len(event_log.read(k)) for k in ("verifications", "failures", "blocked_inputs", "feedback")}
        st.caption(f"Logged: {counts['verifications']} checks · {counts['failures']} problems · "
                   f"{counts['blocked_inputs']} blocked messages · {counts['feedback']} feedback. "
                   "Synthetic SOPs, not OCBC policy.")


# ---------- rendering helpers ----------
A1_AVATAR, TG_AVATAR, USER_AVATAR = ":material/account_balance:", ":material/shield:", ":material/person:"
USER_MARK = '<span class="tg-you" hidden></span>'   # lets the theme style the employee's own messages
A2_MARK = '<span class="tg-a2-mark" hidden></span>'  # lets the theme give TrustGuard its own avatar colour


def agent_label(text: str, right: str = "") -> str:
    return f'<div class="tg-agent"><span>{esc(text)}</span><span>{esc(right)}</span></div>'


def under_checking() -> str:
    return (f'<div class="tg-under">{icon("clock", "1em")} <span><b>Not checked yet:</b> don\'t act on this until '
            'TrustGuard finishes.</span></div>')


def under_verdict(report: Report) -> str:
    level, _ = report.overall
    case = review_queue.for_turn(report.turn_id)
    if case and case["status"] == "decided":
        return f'<div class="tg-under">{mark("ok", "✓", "Reviewed by the " + review_queue.REVIEWER)}</div>'
    if case:
        return f'<div class="tg-under">{icon("clock", "1em")} With the {esc(review_queue.REVIEWER)} for review</div>'
    return f'<div class="tg-under">{mark(VERDICT_KEY[level], VERDICT_ICON[level], UNDER_LABEL[level])}</div>'


# ---------- visual pieces: score ring, step tracker, number highlights, SOP timeline ----------
STAGES = [("version", "Version", "Pick the SOP in effect"), ("split", "Split", "Into statements"),
          ("check", "Check", "Each against the SOP"), ("missing", "Missing", "Required steps"),
          ("fix", "Fix", "Correct and re-check")]


POPS = {"version": "Date logic in plain code works out which SOP versions were in effect. Replaced versions can't be used as evidence.",
        "split": "The answer is split into single statements, so a half-right answer stays half-right.",
        "check": "For each statement, TrustGuard first writes what the SOP requires, then compares. Code re-checks numbers and quotes.",
        "missing": "From the SOP's side: what must a complete answer include? Anything absent is flagged.",
        "fix": "A corrected answer, each sentence tied to an SOP quote, re-checked three ways by methods that didn't write it."}


def tracker_html(states: dict, notes: dict | None = None) -> str:
    """Five steps joined by a line. A state per step: todo, active, done, issue, warn or skip.
    Hover a step to see what happens there."""
    notes = notes or {}
    sym = {"done": "✓", "issue": "!", "warn": "?", "skip": "–"}
    nodes = ""
    for i, (k, title, desc) in enumerate(STAGES, 1):
        st_ = states.get(k, "todo")
        nodes += (f'<div class="tg-node {st_}"><div class="tg-dot">{sym.get(st_, i)}</div>'
                  f'<div class="t">{esc(title)}</div><div class="d">{esc(notes.get(k, desc))}</div>'
                  f'<div class="pop">{esc(POPS[k])}</div></div>')
    return f'<div class="tg-track" aria-label="What TrustGuard did, step by step">{nodes}</div>'


def report_tracker(report: Report) -> str:
    c, n = report.counts, len(report.results)
    corr = report.correction
    states = {"version": "done", "split": "done" if n else "skip",
              "check": "issue" if c[CONTRADICTED] else "warn" if c[INSUFFICIENT_EVIDENCE] else "done" if n else "skip",
              "missing": "issue" if report.missing else "done",
              "fix": "done" if corr and corr.status == "suggested" else "skip"}
    as_of = fmt(report.as_of) if report.as_of else "today"
    notes = {"version": f"In effect {as_of}", "split": plural(n, "statement", "statements"),
             "check": (f"{c[SUPPORTED]} match · {c[CONTRADICTED]} wrong" + (f" · {c[INSUFFICIENT_EVIDENCE]} unsure"
                       if c[INSUFFICIENT_EVIDENCE] else "")),
             "missing": plural(len(report.missing), "missing step", "missing steps") if report.missing else "Nothing missing",
             "fix": "Re-checked" if corr and corr.reverification == "confirmed" else
                    "Partly re-checked" if corr and corr.status == "suggested" else "Not needed"}
    return tracker_html(states, notes)


def ring_html(report: Report) -> str:
    """Donut: how many statements match the SOP, with wrong and unsure segments."""
    c, n = report.counts, max(len(report.results), 1)
    circ = 2 * 3.14159 * 28
    segs, offset = "", 0.0
    for status, color in ((SUPPORTED, "var(--ok)"), (INSUFFICIENT_EVIDENCE, "var(--unk)"), (CONTRADICTED, "var(--bad)")):
        if c[status]:
            length = circ * c[status] / n
            segs += (f'<circle class="seg" cx="35" cy="35" r="28" stroke="{color}" '
                     f'stroke-dasharray="{max(length - 3, 1):.1f} {circ:.1f}" stroke-dashoffset="{-offset:.1f}"/>')
            offset += length
    track = '<circle cx="35" cy="35" r="28" stroke="var(--inset)"/>'
    label = f'{c[SUPPORTED]}/{len(report.results)}' if report.results else "–"
    return (f'<div class="tg-ring" role="img" aria-label="{c[SUPPORTED]} of {len(report.results)} statements match the SOP">'
            f'<svg viewBox="0 0 70 70">{track}{segs}</svg><div class="num"><b>{label}</b><small>match</small></div></div>')


_QTY = re.compile(r"\$\s?\d[\d,]*(?:\.\d+)?|\b\d+\s+(?:business |working |calendar )?(?:days?|months?|weeks?|years?)\b|\b\d+(?:\.\d+)?\s?%")


def _norm(token: str) -> str:
    return re.sub(r"[\s,$]", "", token.lower())


def highlight(text: str, other: str, side: str) -> str:
    """Escapes text and marks amounts and periods. On the assistant's side, a number the SOP doesn't
    contain is struck through in red; on the SOP side, a number the assistant didn't use is green."""
    found = {_norm(m.group()) for m in _QTY.finditer(other or "")}
    out, last = "", 0
    for m in _QTY.finditer(text or ""):
        same = _norm(m.group()) in found
        cls = "n-same" if same else ("n-bad" if side == "assistant" else "n-good")
        out += esc(text[last:m.start()]) + f'<mark class="{cls}">{esc(m.group())}</mark>'
        last = m.end()
    return out + esc((text or "")[last:])


def timeline_html(report: Report) -> str:
    """Every version of the SOPs this answer touched, on one time axis: replaced versions hatched,
    the one in effect in cobalt, the ones Agent 1 read outlined in peach, and the question's date."""
    from datetime import date as _date
    docs = {d["document_id"]: d for d in load_metadata()}
    cited = {r.source_id for r in report.results if r.source_id}
    read = {s.get("source_id") for s in (report.handoff.sources if report.handoff else [])}
    families = []
    for doc_id in list(cited) + sorted(read - cited):
        fam = (docs.get(doc_id) or {}).get("family")
        if fam and fam not in families:
            families.append(fam)
    if not families:
        return ""
    as_of = report.as_of or _date.today()
    rows = []
    for fam in families[:3]:
        versions = sorted((d for d in docs.values() if d.get("family") == fam), key=lambda d: d["effective_date"])
        starts = [_date.fromisoformat(d["effective_date"]) for d in versions]
        lo = min(starts + [as_of]).toordinal() - 60
        hi = max([as_of, _date.today()] + [_date.fromisoformat(d["expiry_date"]) for d in versions if d.get("expiry_date")]).toordinal() + 120
        span = hi - lo
        segs = ""
        for d, start in zip(versions, starts):
            end = _date.fromisoformat(d["expiry_date"]).toordinal() if d.get("expiry_date") else hi
            left, width = (start.toordinal() - lo) / span * 100, (end - start.toordinal()) / span * 100
            in_effect = default_registry().in_effect(d["document_id"], as_of)
            cls = ("cur" if in_effect else "old") + (" read" if d["document_id"] in read else "")
            label = f'v{d["version"]} · ' + ("in effect" if in_effect else "replaced")
            segs += (f'<div class="tg-seg {cls}" style="left:{left:.1f}%; width:{max(width - 0.6, 3):.1f}%" '
                     f'title="{esc(d["title"])} v{esc(d["version"])}: {esc(d["effective_date"])} to {esc(d.get("expiry_date") or "now")}">'
                     f'{esc(label)}</div>')
        mark_left = (as_of.toordinal() - lo) / span * 100
        segs += f'<div class="tg-today" style="left:{mark_left:.1f}%"><span>Question date</span></div>'
        rows.append(f'<div class="tg-tl-row"><div class="tg-tl-name">{esc(versions[-1]["title"])}</div>'
                    f'<div class="tg-tl-bar">{segs}</div></div>')
    legend = ('<div class="tg-legend"><span><i style="background:var(--cobalt)"></i>Version TrustGuard used</span>'
              '<span><i style="background:#C9D2DE"></i>Replaced version</span>'
              '<span><i style="background:transparent; outline:2.5px solid var(--peach)"></i>Agent 1 read this</span></div>')
    return f'<div class="tg-tl"><div class="tg-lbl">Which SOP version counts</div>{"".join(rows)}{legend}</div>'


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9$,]+", (text or "").lower()) if len(w) > 2}


def wrong_and_right(claim: str, evidence: str) -> tuple[list[str], list[str]]:
    """Amounts/periods the assistant used that the SOP doesn't, and the SOP's own ones it didn't use."""
    c = [m.group() for m in _QTY.finditer(claim or "")]
    e = [m.group() for m in _QTY.finditer(evidence or "")]
    cn, en = {_norm(x) for x in c}, {_norm(x) for x in e}
    return [x for x in c if _norm(x) not in en], [x for x in e if _norm(x) not in cn]


def fix_line(r) -> str:
    """"was → now, because …" for a statement that doesn't match."""
    if r.status != CONTRADICTED or not r.source_id:
        return ""
    was, now = wrong_and_right(r.claim, r.evidence)
    if not was and not now:
        return ""
    why = "an older SOP version" if r.root_cause else f"SOP v{r.version} §{r.section}"
    return ('<div class="tg-fixline">' + "".join(f'<span class="was">{esc(w)}</span>' for w in was[:2])
            + '<span class="arr">→</span>' + "".join(f'<span class="now">{esc(n)}</span>' for n in now[:2])
            + f'<span class="tg-small" style="margin:0">because the {"assistant used " + why if r.root_cause else "rule is in " + why}</span></div>')


def annotated_answer(report: Report) -> str:
    """Agent 1's answer, with each sentence lit up by what TrustGuard found (green, red, amber).
    Hover or tap a sentence to see what the SOP in effect says and the fix."""
    answer = report.answer or ""
    if not report.results:
        return esc(answer)
    order = {CONTRADICTED: 0, INSUFFICIENT_EVIDENCE: 1, SUPPORTED: 2}
    sentences = re.split(r"(?<=[.!?])\s+", answer.strip())
    # Each statement goes to the ONE sentence it came from: shared words, and above all shared amounts.
    assigned: dict[int, list] = {}
    for r in report.results:
        rw, rq = _words(r.claim), {_norm(m.group()) for m in _QTY.finditer(r.claim)}
        scores = []
        for idx, sent in enumerate(sentences):
            sq = {_norm(m.group()) for m in _QTY.finditer(sent)}
            words = len(_words(sent) & rw) / max(len(rw), 1)
            nums = (len(sq & rq) / max(len(rq), 1)) if rq else 0.5
            scores.append((words + 2 * nums - (1.5 if rq and sq and not (sq & rq) else 0), idx))
        score, idx = max(scores)
        if score >= 0.9:
            assigned.setdefault(idx, []).append(r)
    parts, i = [], 0
    for idx, sent in enumerate(sentences):
        best = assigned.get(idx, [])
        if not best:
            parts.append(esc(sent))
            continue
        r = sorted(best, key=lambda x: order[x.status])[0]
        key = STATUS[r.status]["key"]
        sop = (f'<span class="k">Current SOP · {esc(r.source_id)} §{esc(r.section)}</span>{esc(r.evidence)}'
               if r.source_id else '<span class="k">Current SOP</span>No SOP section in effect covers this.')
        was, now = wrong_and_right(r.claim, r.evidence) if r.status == CONTRADICTED else ([], [])
        fix = (f'<span class="fix"><s>{esc(", ".join(was))}</s> → <ins>{esc(", ".join(now))}</ins></span>'
               if was or now else "")
        cause = f'<span class="fix">{esc(r.root_cause)}</span>' if r.root_cause else ""
        parts.append(f'<span class="tg-ann {key}" tabindex="0" style="--i:{i}">{esc(sent)}'
                     f'<span class="tip"><b>{esc(STATUS[r.status]["icon"])} {esc(STATUS[r.status]["label"])}</b><br>'
                     f'{sop}{fix}{cause}</span></span>')
        i += 1
    return " ".join(parts) + '<div class="tg-legend2">Hover or tap a highlighted sentence to see what the SOP says.</div>'


def headline(report: Report) -> tuple[str, str, str, str]:
    """(status key, symbol, title, one plain sentence). Same severity order as Report.overall:
    the most serious finding decides, because one wrong fact is enough to make an answer unsafe."""
    level, _ = report.overall
    c, missing = report.counts, len(report.missing)
    key, sym = VERDICT_KEY[level], VERDICT_ICON[level]
    if level == "info":
        return key, sym, "Nothing to check", "This answer doesn't state any SOP facts to compare."
    if c[CONTRADICTED]:
        bits = [plural(c[CONTRADICTED], "statement doesn't", "statements don't") + " match the current SOP"]
        if missing:
            bits.append(plural(missing, "required step is", "required steps are") + " missing")
        text = " and ".join(bits)
        return key, sym, "Don't use this answer", text[0].upper() + text[1:] + "."
    if missing:
        return key, sym, "Incomplete answer", f"It leaves out {plural(missing, 'step', 'steps')} the SOP requires."
    if c[INSUFFICIENT_EVIDENCE]:
        return key, sym, "Use with care", (plural(c[INSUFFICIENT_EVIDENCE], "statement", "statements")
                                           + " couldn't be confirmed in the current SOP.")
    if report.coverage_warnings:
        return key, sym, "Use with care", "Everything checked matches, but part of the answer may not have been checked."
    return key, sym, "Matches the current SOP", (
        "The one statement in this answer was checked." if len(report.results) == 1
        else f"All {len(report.results)} statements in this answer were checked.")


def cite(source_id: str, section: str) -> str:
    return f'<span class="tg-cite">{esc(source_id)} §{esc(section)}</span>'


def render_answer_to_use(report: Report) -> None:
    """What the employee should do now: the corrected answer if there is one, otherwise where it came from."""
    level, _ = report.overall
    corr = report.correction
    if corr and corr.status == "suggested":
        k, sym, label = RECHECK.get(corr.reverification, ("neutral", "–", "Not re-checked"))
        body = "".join(f'<p>{esc(s.text)}{cite(s.source_id, s.section)}</p>' for s in corr.sentences)
        st.markdown(f'<div class="tg-useit tg-rise"><div class="tg-lbl">Answer to use instead</div>{body}'
                    f'<div class="tg-small">{mark(k, sym, label)}</div></div>', unsafe_allow_html=True)
    elif corr and corr.status not in ("not_needed", "suggested") and corr.message:
        st.markdown(f'<div class="tg-useit"><div class="tg-lbl">What to do</div><p>{esc(corr.message)}</p></div>',
                    unsafe_allow_html=True)
    elif level == "success":
        sources = sorted({f"{r.source_title} v{r.version} §{r.section}" for r in report.results if r.source_id})
        if sources:
            st.markdown(f'<div class="tg-src">Source: {esc(" · ".join(sources))}</div>', unsafe_allow_html=True)


def derivation_html(steps: list[dict]) -> str:
    items = "".join(f'<li><span><b>{esc(s["label"])}.</b>{esc(s["detail"])}</span></li>' for s in steps)
    return (f'<details class="tg-how"><summary>How TrustGuard worked it out</summary>'
            f'<ol class="tg-steps">{items}</ol></details>')


def statement_row(r) -> str:
    s = STATUS[r.status]
    review = mark("rev", "!", "A person should review") if r.needs_review else ""
    if r.source_id:
        sop = (f'<p>{highlight(r.evidence, r.claim, "sop")}</p><div class="tg-small">{esc(r.source_title)}, '
               f'version {esc(r.version)}{cite(r.source_id, r.section)}</div>')
    else:
        sop = '<p class="none">No SOP section in effect covers this.</p>'
    claim = highlight(r.claim, r.evidence if r.source_id else "", "assistant") if r.status != SUPPORTED else highlight(r.claim, r.evidence, "sop")
    why = f'<div class="tg-why"><b>Likely cause:</b> {esc(r.root_cause)}</div>' if r.root_cause else ""
    return (f'<div class="tg-row"><div class="tg-row-head" title="{esc(s["meaning"])}">{chip(r.status)}'
            f'<span class="tg-mono">Statement {r.claim_id}</span>{review}</div>'
            f'<div class="tg-pair"><div class="side"><div class="tg-lbl">Assistant said</div><p>{claim}</p></div>'
            f'<div class="vs" aria-hidden="true">vs</div>'
            f'<div class="side sop"><div class="tg-lbl">Current SOP says</div>{sop}</div></div>'
            f'{fix_line(r)}{why}{derivation_html(r.derivation) if r.derivation else ""}</div>')


def tab_statements(report: Report) -> None:
    if not report.results:
        st.markdown('<div class="tg-empty">No checkable statements in this answer.</div>', unsafe_allow_html=True)
        return
    ordered = sorted(report.results, key=lambda r: r.status == SUPPORTED)  # problems first
    st.markdown("".join(statement_row(r) for r in ordered), unsafe_allow_html=True)


def tab_missing(report: Report, show_all: bool) -> None:
    c = report.completeness
    if not c or not c.checked or not c.elements:
        st.markdown('<div class="tg-empty">No required steps to compare for this question.</div>',
                    unsafe_allow_html=True)
        return
    shown = c.elements if show_all else c.missing
    if not shown:
        st.markdown('<div class="tg-empty">Nothing the SOP requires is missing from the answer.</div>',
                    unsafe_allow_html=True)
        return
    rows = ""
    for e in shown:
        m = (chip(SUPPORTED, "Included") if e.covered else chip(CONTRADICTED, "Wrong value") if e.wrong_value
             else chip(CONTRADICTED, "Missing") if e.essential else raw_chip("neutral", "+", "Extra detail"))
        note = f'<br><span>{esc(e.note)}</span>' if e.note else ""
        rows += (f'<li>{m}<div><b>{esc(e.element)}</b>“{esc(e.quote)}”{cite(e.source_id, e.section)}'
                 f'{note}</div></li>')
    st.markdown(f'<ul class="tg-list">{rows}</ul>', unsafe_allow_html=True)


def tab_how(report: Report) -> None:
    tl = timeline_html(report)
    if tl:
        st.markdown(tl, unsafe_allow_html=True)
    t = report.timings
    n = len(report.results)
    as_of = fmt(report.as_of) if report.as_of else "today"
    steps = [("Picked the SOP version", f"Used the versions in effect on {as_of}. Replaced versions were not used as "
                                        f"evidence.{' ' + report.as_of_note if report.as_of_note else ''}"),
             ("Split the answer", f"Into {plural(n, 'statement', 'statements')}, each checked on its own."),
             ("Checked each statement", "Worked out what the SOP requires first, then compared. Code re-checked "
                                        "numbers, quotes and versions, and can only make a result more careful."),
             ("Looked for missing steps", "Listed what a complete answer must include, from the SOP's side.")]
    corr = report.correction
    if corr and corr.status == "suggested":
        steps.append(("Wrote and re-checked a fix", "Each sentence is tied to an SOP quote, then checked three "
                                                     "ways by methods that didn't write it."))
    st.markdown('<ol class="tg-steps">' + "".join(f'<li><span><b>{esc(a)}.</b>{esc(b)}</span></li>' for a, b in steps)
                + '</ol>', unsafe_allow_html=True)
    if corr and corr.status == "suggested":
        rows = ""
        for i, s in enumerate(corr.sentences, 1):
            checks = " ".join(mark(*CHECK_ICON.get(res["result"], ("neutral", "–")), CHECK_NAMES.get(name, name))
                              for name, res in s.checks.items())
            rows += f'<li><span class="tg-mono">{i}</span><div><b>{esc(s.text)}</b>{checks}</div></li>'
        st.markdown(f'<div class="tg-lbl" style="margin-top:0.9rem">Re-check of the suggested answer</div>'
                    f'<ul class="tg-list">{rows}</ul>', unsafe_allow_html=True)
    h = report.handoff
    st.markdown(f'<div class="tg-small tg-mono" style="margin-top:0.8rem">Agent 1 ({esc(h.model if h else "?")}) '
                f'{t.get("agent1_s", 0)} s · TrustGuard ({esc(report.trustguard_model)}) '
                f'{t.get("trustguard_total_s", 0)} s</div>', unsafe_allow_html=True)


def tab_details(report: Report, key: str) -> None:
    for r in report.results:
        checks = "<br>".join(esc(c) for c in r.rule_checks) or "No rule checks applied."
        found = "<br>".join(f'{p["score"]:.3f} · {esc(p["source_id"])} §{esc(p["section"])} {esc(p["section_title"])}'
                            for p in r.retrieved)
        st.markdown(f'<div class="tg-lbl">Statement {r.claim_id}: rule checks</div><div class="tg-tech">{checks}</div>'
                    f'<div class="tg-lbl" style="margin-top:0.5rem">Sections found by TrustGuard\'s search '
                    f'(below {retriever.min_relevance} counts as unrelated)</div><div class="tg-tech">{found}</div><br>',
                    unsafe_allow_html=True)
    h = report.handoff
    if h and h.sources:
        read = "<br>".join(f'{esc(s["title"])} v{esc(s["version"])} ({esc(s["status"])}) §{esc(s["section"])} '
                           f'{esc(s["section_title"])}' for s in h.sources)
        st.markdown(f'<div class="tg-lbl">What Agent 1 read (TrustGuard does its own search)</div>'
                    f'<div class="tg-tech">{read}</div><br>', unsafe_allow_html=True)
    for w in report.coverage_warnings:
        st.markdown(f'<div class="tg-tech">⚠ {esc(w)}</div>', unsafe_allow_html=True)
    st.download_button("Download the full report (JSON)", json.dumps(report.to_dict(), indent=2, default=str),
                       file_name=f"trustguard_report_{report.turn_id}.json", mime="application/json",
                       key=f"dl_{key}")


def render_tabs(report: Report, key: str) -> None:
    c = report.completeness
    n_missing = len(report.missing)
    labels = [f"Statements · {len(report.results)}",
              f"Missing steps · {n_missing}" if (c and c.checked) else "Missing steps",
              "How it was checked"] + (["Details"] if audit else [])
    tabs = st.tabs(labels)
    with tabs[0]:
        tab_statements(report)
    with tabs[1]:
        tab_missing(report, show_all=audit)
    with tabs[2]:
        tab_how(report)
    if audit:
        with tabs[3]:
            tab_details(report, key)


def render_feedback(report: Report) -> None:
    done_key = f"fb_done_{report.turn_id}"
    if st.session_state.get(done_key):
        st.caption("Thanks, your feedback was recorded.")
        return
    st.markdown('<div class="tg-small">Was this check right?</div>', unsafe_allow_html=True)
    rating = st.feedback("thumbs", key=f"fb_{report.turn_id}")
    if rating == 1:
        event_log.log_feedback(report.turn_id, "up", report=report)
        st.session_state[done_key] = True
        st.rerun()
    elif rating == 0:
        with st.form(f"fb_form_{report.turn_id}"):
            reason = st.selectbox("What was wrong?", [
                "TrustGuard flagged a correct answer", "TrustGuard missed a wrong answer",
                "Wrong SOP or section cited", "Suggested answer is wrong", "Explanation is unclear", "Other"])
            comment = st.text_area("Details (optional). Please don't include customer data.", max_chars=500)
            if st.form_submit_button("Send feedback"):
                event_log.log_feedback(report.turn_id, "down", reason, screen(comment).text or "", report)
                st.session_state[done_key] = True
                st.rerun()


def render_review(report: Report, key: str) -> None:
    """Human in the loop: when TrustGuard can't give a clear ✓, the employee can hand the case to the
    Branch Operations Head and gets the decision back here."""
    level, _ = report.overall
    if level == "success" and not report.needs_review:
        return
    case = review_queue.for_turn(report.turn_id)
    who = review_queue.REVIEWER
    if case is None:
        why = ("TrustGuard couldn't fully confirm this." if report.needs_review or level == "warning"
               else "TrustGuard found a problem with this answer.")
        st.markdown(f'<div class="tg-review"><p class="who">Not sure what to do?</p><p>{esc(why)} You can ask the '
                    f'{esc(who)} to review it before you act.</p></div>', unsafe_allow_html=True)
        if st.button(f"Ask the {who}", key=f"askrv_{key}", type="primary", icon=":material/person_raised_hand:"):
            review_queue.request(report, reason="needs_review" if report.needs_review else level)
            st.rerun()
        return
    if case["status"] == "waiting":
        st.markdown(f'<div class="tg-review waiting"><p class="who">{icon("clock", "1em")} Sent to the {esc(who)}'
                    f'<span class="tg-case">{esc(case["case_id"])}</span></p><p>Waiting for review. '
                    'Don\'t act on this answer until it has been reviewed.</p></div>', unsafe_allow_html=True)
        c1, c2 = st.columns([1, 2])
        with c1:
            st.button("Check for a reply", key=f"rvchk_{key}", icon=":material/refresh:")
        with c2:
            st.page_link("pages/review_queue.py", label="Open the review queue (reviewer's view)",
                         icon=":material/fact_check:")
        return
    use = review_queue.answer_to_use(case)
    note = f'<p class="tg-small">Note: {esc(case["note"])}</p>' if case.get("note") else ""
    st.markdown(f'<div class="tg-review done"><p class="who">{mark("ok", "✓", "Reviewed by the " + who)}'
                f'<span class="tg-case">{esc(case["case_id"])}</span></p>'
                f'<p class="tg-small">{esc(review_queue.DECISIONS[case["decision"]])}</p>'
                + (f'<div class="tg-lbl" style="margin-top:0.5rem">Use this answer</div><p>{esc(use)}</p>' if use else "")
                + note + '</div>', unsafe_allow_html=True)


def render_findings(report: Report, key: str) -> None:
    level, _ = report.overall
    k, sym, title, sentence = headline(report)
    st.markdown(f'<div class="tg-hero tg-rise">{ring_html(report)}<div class="tg-result tg-{k}">'
                f'<div class="mark" aria-hidden="true"><span>{sym}</span></div>'
                f'<div><h4>{esc(title)}</h4><p>{esc(sentence)}</p></div></div></div>'
                + report_tracker(report), unsafe_allow_html=True)
    if report.needs_review:
        st.markdown('<div class="tg-flag"><b>A person should review this.</b> Two of TrustGuard\'s own checks '
                    'disagreed, or part of the answer couldn\'t be checked, so it won\'t mark this as verified.</div>',
                    unsafe_allow_html=True)
    for n in report.input_notes:
        st.caption(n)
    render_answer_to_use(report)
    render_review(report, key)
    if audit or level != "success":
        render_tabs(report, key)
    else:  # daily mode, nothing wrong: keep it to one line, details one click away
        with st.expander("Show how it was checked"):
            render_tabs(report, key)
    render_feedback(report)


def typing(text: str):
    """Shows Agent 1's finished answer word by word, like a chat assistant."""
    for word in text.split(" "):
        yield word + " "
        time.sleep(0.03)


# ---------- the conversation ----------
with st.chat_message("assistant", avatar=A1_AVATAR):
    st.markdown(agent_label("Agent 1 · Banking assistant"), unsafe_allow_html=True)
    st.markdown("Hi! Ask me about Northbridge Bank's staff policies and branch procedures: travel and expense "
                "claims, cash withdrawals, account opening for foreign nationals and fee waivers.")

if not st.session_state.turns:
    st.pills("Try one", [q["label"] for q in demo_questions()], key="ex_pills", on_change=ask_example,
             args=("ex_pills",), disabled=assistant is None)

for i, turn in enumerate(st.session_state.turns):
    with st.chat_message("user", avatar=USER_AVATAR):
        st.markdown(USER_MARK, unsafe_allow_html=True)
        st.markdown(turn["question"])
    if turn["kind"] == "reply":  # input checks or a non-policy message: nothing to verify
        guard = turn.get("guard")
        with st.chat_message("assistant", avatar=TG_AVATAR if guard else A1_AVATAR):
            st.markdown((A2_MARK if guard else "") + agent_label("Input check" if guard else "Agent 1 · Banking assistant"),
                        unsafe_allow_html=True)
            st.markdown(turn["reply"])
            if turn.get("note"):
                st.caption(turn["note"])
        continue
    rep = turn["report"]
    with st.chat_message("assistant", avatar=A1_AVATAR):
        st.markdown(agent_label("Agent 1 · Banking assistant"), unsafe_allow_html=True)
        st.markdown(f'<div class="tg-answer-text">{annotated_answer(rep)}</div>', unsafe_allow_html=True)
        st.markdown(under_verdict(rep), unsafe_allow_html=True)
    with st.chat_message("TrustGuard", avatar=TG_AVATAR):
        st.markdown(A2_MARK + agent_label("TrustGuard check", f'{rep.timings.get("trustguard_total_s", 0)} s'),
                    unsafe_allow_html=True)
        render_findings(rep, f"t{i}")

# After the first answer, keep a few example questions under the conversation (ones not asked yet),
# so the demo can move on to the next case without typing.
if st.session_state.turns:
    asked = {t["question"] for t in st.session_state.turns}
    left = [q["label"] for q in demo_questions() if q["question"] not in asked]
    if left:
        st.pills("Try another", left, key="more_pills", on_change=ask_example, args=("more_pills",),
                 disabled=assistant is None)



def add_reply(question: str, reply: str, guard: bool, note: str = "") -> None:
    st.session_state.turns.append({"kind": "reply", "question": question, "reply": reply, "guard": guard,
                                   "note": note})
    st.rerun()


typed = st.chat_input("Ask about a policy or procedure…", disabled=assistant is None,
                      max_chars=2000)
question = typed or st.session_state.pop("pending_question", None)

if question:
    # ---- Layer 1 input checks: plain code, no API call ----
    checked = screen(question)
    shown_question = checked.text if checked.ok else ("(message not shown)" if checked.kind == "injection"
                                                      else question[:300])
    if not checked.ok:
        if checked.kind != "greeting":
            event_log.write("blocked_inputs", {"kind": checked.kind, "text": shown_question})
        add_reply(shown_question, checked.message, guard=checked.kind != "greeting")
    limited = st.session_state.limiter.check(checked.text)
    if limited:
        add_reply(shown_question, limited.message, guard=True)

    with st.chat_message("user", avatar=USER_AVATAR):
        st.markdown(USER_MARK, unsafe_allow_html=True)
        st.markdown(checked.text)
    try:
        # ---- Layer 2: what kind of message is this? (Agent 1's cheap model) ----
        with st.spinner("Reading your question…"):
            intent = classify(checked.text, agent1_llm)
        if intent.category != "in_scope":
            event_log.write("blocked_inputs", {"kind": intent.category, "text": checked.text})
            add_reply(checked.text, intent.reply, guard=False,
                      note="Nothing to verify: this isn't a policy question." if intent.category != "unclear"
                      else "Nothing to verify yet: the assistant needs more detail first.")
        notes_in = [n for n in (checked.message, intent.note) if n]

        # ---- Agent 1 answers in real time ----
        with st.chat_message("assistant", avatar=A1_AVATAR):
            st.markdown(agent_label("Agent 1 · Banking assistant"), unsafe_allow_html=True)
            with st.spinner("Searching the SOPs and writing an answer…"):
                handoff = assistant.answer(intent.question)
            if not handoff.answer:
                raise InputError("The assistant returned an empty answer. Try asking again.")
            st.write_stream(typing(handoff.answer))
            badge = st.empty()
            badge.markdown(under_checking(), unsafe_allow_html=True)

        # ---- TrustGuard intercepts, derives, compares, corrects and re-checks ----
        with st.chat_message("TrustGuard", avatar=TG_AVATAR):
            st.markdown(A2_MARK + agent_label("TrustGuard check"), unsafe_allow_html=True)
            ctx = PolicyContext.for_question(default_registry(), handoff.question)
            live, line = st.empty(), st.empty()
            states, notes = {"version": "active"}, {}

            def show(text: str) -> None:
                live.markdown(tracker_html(states, notes), unsafe_allow_html=True)
                line.caption(text)

            show("Working out which SOP versions were in effect…")

            def on_stage(stage, data):
                if stage == "policy":
                    states.update(version="done", split="active")
                    notes["version"] = f"In effect {fmt(data.as_of)}"
                    show(f"Using the SOP versions in effect on {fmt(data.as_of)}. Splitting the answer…")
                elif stage == "claims":
                    states.update(split="done" if data else "skip", check="active")
                    notes["split"] = plural(len(data), "statement", "statements")
                    show("Working out what the SOP says for each statement…" if data else "No statements to check.")
                elif stage == "verified":
                    states.update(check="done", missing="active")
                    show("Compared each statement with the SOP. Checking nothing required is missing…")
                elif stage == "completeness":
                    states.update(missing="issue" if data.missing else "done", fix="active")
                    if data.missing:
                        notes["missing"] = plural(len(data.missing), "missing step", "missing steps")
                    show("Writing a corrected answer…" if data.missing else "Finishing up…")
                elif stage == "correction":
                    show("Re-checking the corrected answer three ways…")

            report = run_pipeline(handoff.question, handoff.answer, retriever, llm, ctx=ctx, nli=nli,
                                  on_stage=on_stage)
            report.handoff, report.input_notes = handoff, notes_in
            report.timings = {"agent1_s": handoff.latency_s, **report.timings}
            live.markdown(report_tracker(report), unsafe_allow_html=True)
            line.caption(f"Checked in {report.timings['trustguard_total_s']:.1f} s")
        badge.markdown(under_verdict(report), unsafe_allow_html=True)
        event_log.log_report(report, mode="audit" if audit else "daily")
        st.session_state.turns.append({"kind": "report", "question": checked.text, "report": report})
        st.rerun()
    except (InputError, AssistantError) as e:
        st.warning(str(e))
    except LLMError as e:
        event_log.log_error("llm", e, checked.text)
        st.error(f"Verification unavailable: {e} The answer has NOT been verified, so don't rely on it.")
    except Exception as e:  # never show a raw traceback to judges
        event_log.log_error("app", e, checked.text)
        st.error(f"Something went wrong ({type(e).__name__}). The answer has NOT been verified. Try again; if it "
                 "repeats, restart the app.")
