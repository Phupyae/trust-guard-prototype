"""TrustGuard AI — two-agent demo: Agent 1 (Banking AI Assistant) answers the employee,
Agent 2 (TrustGuard) intercepts that answer, shows HOW the right answer is reached from
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
import json
import time

import streamlit as st

import config
from modules import event_log
from modules.banking_assistant import AssistantError, BankingAssistant, build_agent1_retriever
from modules.document_loader import load_knowledge_base, load_metadata
from modules.evidence_retriever import EvidenceRetriever, make_embedder
from modules.input_guard import RateLimiter, classify, screen
from modules.llm_client import LLMError, get_client
from modules.nli import NLIChecker
from modules.pipeline import InputError, Report, default_registry, run_pipeline
from modules.policy_validation import PolicyContext, fmt
from modules.schemas import CONTRADICTED, INSUFFICIENT_EVIDENCE, SUPPORTED
from ui_theme import apply_base_theme, icon, page_nav, reliability_link

st.set_page_config(page_title="TrustGuard AI", page_icon="🛡️", layout="wide")

# One status vocabulary for the whole app (Consistency). The icon and the word carry the
# meaning; colour reinforces it, so colour-blind users lose nothing (Perceivability).
STATUS = {
    SUPPORTED: {"key": "ok", "icon": "✓", "label": "Supported",
                "meaning": "The policy in effect states this."},
    CONTRADICTED: {"key": "bad", "icon": "✕", "label": "Contradicted",
                   "meaning": "The policy in effect says something different."},
    INSUFFICIENT_EVIDENCE: {"key": "unk", "icon": "?", "label": "Insufficient evidence",
                            "meaning": "No policy in effect confirms or rules this out."},
}
VERDICT_KEY = {"error": "bad", "warning": "unk", "success": "ok", "info": "neutral"}
VERDICT_ICON = {"error": "✕", "warning": "?", "success": "✓", "info": "–"}
VERDICT_LABEL = {"error": "TrustGuard: do not rely on this answer",
                 "warning": "TrustGuard: use with caution",
                 "success": "TrustGuard: verified",
                 "info": "TrustGuard: no checkable facts"}
RECHECK = {"confirmed": ("ok", "✓", "Suggested answer re-checked"),
           "partially_confirmed": ("unk", "?", "Suggested answer partly re-checked"),
           "not_confirmed": ("bad", "✕", "Suggested answer could not be confirmed")}
CHECK_NAMES = {"A_citation": "A · Citation (code)", "B_rules": "B · Rules table (code)",
               "C_entailment": "C · Entailment model"}
CHECK_ICON = {"pass": ("ok", "✓"), "fail": ("bad", "✕"), "uncertain": ("unk", "?"),
              "unavailable": ("neutral", "–"), "not_covered": ("neutral", "–")}
CIRCLED = "①②③④⑤⑥"

apply_base_theme()

st.markdown("""
<style>
/* Priority 2 additions: derivation steps, required elements, suggested answer */
.tg-col-label.how {color:var(--navy); margin-top:0.9rem;}
.tg-steps {list-style:none; padding:0; margin:0.3rem 0 0.4rem 0; counter-reset:none;}
.tg-steps li {display:flex; gap:0.6rem; align-items:flex-start; padding:0.35rem 0; border-bottom:1px dashed var(--rule);}
.tg-steps li:last-child {border-bottom:none;}
.tg-steps .n {color:var(--accent); font-size:1.15rem; line-height:1.2; min-width:1.3rem;}
.tg-steps b {display:block; color:var(--ink); font-size:0.9rem;}
.tg-steps span {color:var(--ink-2); font-size:0.92rem;}
.tg-root {background:var(--unk-bg); color:var(--unk); border-radius:6px; padding:0.5rem 0.75rem; margin-top:0.5rem;
  font-size:0.92rem;}
.tg-root b {color:var(--unk);}
.tg-req {list-style:none; padding:0; margin:0.3rem 0 0.8rem 0;}
.tg-req li {display:flex; gap:0.7rem; align-items:flex-start; padding:0.45rem 0; border-bottom:1px dashed var(--rule);}
.tg-req b {display:block; color:var(--ink);}
.tg-req span {display:block; color:var(--ink-2); font-size:0.86rem;}
.tg-req span.note {color:var(--ink-3); font-style:italic;}
.tg-fix {background:#fff; border:1px solid var(--line); border-left:6px solid var(--accent); border-radius:8px;
  padding:0.4rem 1.1rem 0.8rem; margin:0.8rem 0 0.5rem 0;}
.tg-fix p {font-family:'Source Serif 4', Georgia, serif; font-size:1.05rem; line-height:1.55; color:var(--ink);
  margin:0.35rem 0;}
.tg-fix .cite {font-family:'Public Sans', system-ui, sans-serif; font-size:0.78rem; color:var(--accent); white-space:nowrap;}
</style>
""", unsafe_allow_html=True)


def esc(text) -> str:
    return html.escape(str(text or ""))


def chip(status: str, text: str | None = None) -> str:
    s = STATUS[status]
    return f'<span class="tg-chip tg-{s["key"]}"><b aria-hidden="true">{s["icon"]}</b>{text or s["label"]}</span>'


def raw_chip(key: str, icon: str, text: str) -> str:
    return f'<span class="tg-chip tg-{key}"><b aria-hidden="true">{icon}</b>{esc(text)}</span>'


# ---------- header first, so the page is never blank while loading (Feedback) ----------
st.markdown('<div class="tg-hero"><h1><span class="tg-logo">' + icon("bank", "1.5rem") + '</span>Northbridge Bank AI Assistant</h1>'
            '<p>Ask about staff policies and branch procedures. Every answer is intercepted by '
            '<b>TrustGuard</b>, an independent verification layer, which shows how the right answer is reached '
            'from the policy in effect before you rely on it.</p>'
            '<span class="tg-pill">Agent 1 answers live</span><span class="tg-pill">' + icon("shield", "0.95em") + 'Checked by TrustGuard</span>'
            '<span class="tg-pill">Synthetic policies, not OCBC policy</span></div>',
            unsafe_allow_html=True)
st.markdown(
    f'<div class="tg-flow{" compact" if st.session_state.get("turns") else ""}" aria-label="How the two agents work together">'
    '<div><em>' + icon("message") + '</em><b>You</b><span>type a question</span></div><i aria-hidden="true">→</i>'
    '<div class="a1"><em>' + icon("bank") + '</em><b>Agent 1 · Banking AI Assistant</b>'
    '<span>answers fast (cheaper model)</span></div><i aria-hidden="true">→</i>'
    '<div class="a2"><em>' + icon("shield") + '</em><b>TrustGuard</b><span>derives the answer from the policy in '
    'effect, compares, corrects and re-checks (stronger model)</span></div><i aria-hidden="true">→</i>'
    '<div><em>' + icon("check") + '</em><b>You</b><span>know what to trust, and why</span></div></div>', unsafe_allow_html=True)


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


with st.sidebar:
    page_nav()
    st.markdown("### Try a question")
    st.caption("Or type your own in the chat box. Examples only fill in the question; the assistant answers live.")
    for i, q in enumerate(demo_questions()):
        st.button(q["label"], key=f"ex_side_{i}", help=q["question"], on_click=ask, args=(q["question"],),
                  use_container_width=True, disabled=assistant is None)
    st.button("Clear conversation", on_click=lambda: st.session_state.update(turns=[]), use_container_width=True)

    st.markdown("### Display mode")
    audit = st.toggle("Audit mode: always show every step", key="audit_mode",
                      help="Off (daily mode): a verified answer shows a ✓ badge, with “Show how” one click away. "
                           "Anything wrong, missing or unconfirmed opens automatically.\n\n"
                           "On (audit mode): every step of every check is always shown.")
    st.caption("Audit mode is on: every check is shown." if audit else
               "Daily mode: the explanation opens automatically only when something needs your attention.")


    SCOPE_TEXT = {"all": "The same policy repository as TrustGuard, including superseded versions. "
                         "It indexes the text only, without checking versions or effective dates.",
                  "approved": "Current policy versions only", "none": "No documents (general knowledge only)"}
    st.markdown("### How the demo is set up")
    with st.expander("Agent 1 · Banking AI Assistant", icon=":material/account_balance:"):
        st.markdown(f"**Language model** (cheaper tier)  \n{assistant.model if assistant else 'not available'}")
        st.markdown(f"**Reads**  \n{SCOPE_TEXT.get(config.AGENT1_KB_SCOPE, config.AGENT1_KB_SCOPE)}")
        if agent1_retriever is not None:
            st.markdown(f"**Passages per question**  \nTop {config.AGENT1_TOP_K}")
        st.caption("Why a cheaper model? It answers every employee question, so cost and speed matter most.")
    with st.expander("TrustGuard · verification layer", icon=":material/shield:"):
        model_name = ("offline mock (not real verification)" if llm and llm.name == "mock"
                      else getattr(llm, "model", "") if llm else "not available")
        st.markdown(f"**Language model** (stronger tier)  \n{model_name}")
        st.markdown(f"**Evidence search**  \n{retriever.embedder.label}, {len(retriever.chunks)} sections. "
                    "Only versions in effect on the question's date are used as evidence (checked in code).")
        st.markdown("**Re-check of its own corrections**  \nA citation (code) · B rules table (code) · "
                    f"C entailment model: {'ready' if nli.available else 'unavailable'}")
        if not nli.available:
            st.caption(nli.error)
    if retrieval_warning:
        st.warning(retrieval_warning)
    with st.expander("Policy repository", icon=":material/description:"):
        st.caption("Synthetic documents written for this demo. Not OCBC policy.")
        today = default_registry()
        for doc in load_metadata():
            from datetime import date
            current = today.in_effect(doc["document_id"], date.today())
            tag = (chip(SUPPORTED, "In effect today") if current else
                   raw_chip("neutral", "–", f"{doc['status']}, not in effect today"))
            st.markdown(f'<div class="tg-kb">{tag}<br><b class="t">{esc(doc["title"])}</b><br>'
                        f'<small>Version {esc(doc["version"])}, effective {esc(doc["effective_date"])}'
                        f'{", until " + esc(doc["expiry_date"]) if doc.get("expiry_date") else ""}</small></div>',
                        unsafe_allow_html=True)
    with st.expander("Logs and feedback", icon=":material/folder_open:"):
        counts = {s: len(event_log.read(s)) for s in ("verifications", "failures", "blocked_inputs", "feedback")}
        st.markdown(f"Verified answers: **{counts['verifications']}**  \nFindings and errors logged: "
                    f"**{counts['failures']}**  \nBlocked inputs: **{counts['blocked_inputs']}**  \n"
                    f"Feedback received: **{counts['feedback']}**")
        st.caption(f"Saved as JSON Lines in {config.LOG_DIR.name}/ for analysis.")


# ---------- rendering helpers ----------
A1_AVATAR, TG_AVATAR, USER_AVATAR = ":material/account_balance:", ":material/shield:", ":material/person:"
USER_MARK = '<span class="tg-you" hidden></span>'  # lets the theme style the employee's own messages


def held_chip() -> str:
    return ('<div class="tg-held"><span class="tg-chip tg-rev"><b>' + icon("clock", "0.95em") + '</b>'
            'Intercepted by TrustGuard: checking before delivery</span></div>')


def verdict_chip(report: Report) -> str:
    level, _ = report.overall
    return (f'<div class="tg-held"><span class="tg-chip tg-{VERDICT_KEY[level]}">'
            f'<b aria-hidden="true">{VERDICT_ICON[level]}</b>{VERDICT_LABEL[level]}</span></div>')


def intercept_banner() -> None:
    st.markdown('<div class="tg-agent tg-a2">TRUSTGUARD · VERIFICATION LAYER</div>'
                '<div class="tg-intercept"><span>' + icon("shield") + '</span><div>Answer intercepted'
                '<small>TrustGuard is working out the answer from the policy in effect and comparing it with '
                'the assistant\'s answer before it is delivered.</small></div></div>', unsafe_allow_html=True)


def derivation_html(steps: list[dict]) -> str:
    items = "".join(f'<li><span class="n" aria-hidden="true">{CIRCLED[min(s["step"], 6) - 1]}</span>'
                    f'<div><b>{esc(s["label"])}</b><span>{esc(s["detail"])}</span></div></li>' for s in steps)
    return f'<ol class="tg-steps" aria-label="How TrustGuard gets the answer">{items}</ol>'


def claim_card(r, key: str, full: bool) -> None:
    """full=True shows the side-by-side comparison and the derivation chain."""
    s = STATUS[r.status]
    review = raw_chip("rev", "!", "Needs review") if r.needs_review else ""
    with st.container(border=True, key=f"card_{key}_{r.claim_id}"):
        head = (f'<div class="tg-card tg-{s["key"]}" style="background:transparent">'
                f'<div class="tg-card-head">{chip(r.status)}<span class="tg-claimno">Claim {r.claim_id}</span>'
                f'{review}</div>')
        if not full:
            st.markdown(head + f'<div class="tg-doc">{esc(r.claim)}</div></div>', unsafe_allow_html=True)
            return
        if r.source_id:
            evidence = (f'<div class="tg-doc">{esc(r.evidence)}</div>'
                        f'<div class="tg-source">{esc(r.source_title)}, version {esc(r.version)}, '
                        f'section {esc(r.section)} {esc(r.section_title)}</div>')
        else:
            evidence = '<div class="tg-doc empty">No policy section in effect addresses this claim.</div>'
        root = (f'<div class="tg-root"><b>Likely cause:</b> {esc(r.root_cause)}</div>' if r.root_cause else "")
        st.markdown(head + '<div class="tg-compare">'
                    f'<div><div class="tg-col-label">The assistant says</div><div class="tg-doc">{esc(r.claim)}</div></div>'
                    f'<div><div class="tg-col-label policy">The policy in effect says</div>{evidence}</div></div>'
                    f'<div class="tg-col-label how">How TrustGuard gets the answer</div>{derivation_html(r.derivation)}'
                    f'{root}</div>', unsafe_allow_html=True)
        # A toggle, not an expander: cards can sit inside "Show how", and Streamlit
        # doesn't allow an expander inside another expander.
        if st.toggle("Technical details: rule checks and search results", key=f"tech_{key}_{r.claim_id}"):
            for check in r.rule_checks:
                st.markdown(f"- {check}")
            st.markdown(f"**Sections found by TrustGuard's search** (similarity; below {retriever.min_relevance} "
                        "counts as unrelated)")
            for p in r.retrieved:
                st.markdown(f"- `{p['score']:.3f}` {p['source_id']} §{p['section']} {p['section_title']}: "
                            f"_{p['text'][:150]}…_")


def render_completeness(report: Report, show_all: bool) -> None:
    c = report.completeness
    if not c or not c.checked or not c.elements:
        return
    shown = c.elements if show_all else c.missing
    if not shown:
        return
    rows = ""
    for e in shown:
        mark = (chip(SUPPORTED, "Included") if e.covered else chip(CONTRADICTED, "Wrong value") if e.wrong_value
                else chip(CONTRADICTED, "Missing") if e.essential
                else raw_chip("neutral", "+", "Extra detail"))
        rows += (f'<li>{mark}<div><b>{esc(e.element)}</b><span>{esc(e.source_title)} v{esc(e.version)}, '
                 f'§{esc(e.section)}: “{esc(e.quote)}”</span>'
                 + (f'<span class="note">{esc(e.note)}</span>' if e.note else "") + '</div></li>')
    title = "What a complete answer must include" if show_all else "Required by the policy, but missing from the answer"
    st.markdown(f'<div class="tg-col-label how">{title}</div><ul class="tg-req">{rows}</ul>', unsafe_allow_html=True)


def render_correction(report: Report, key: str, show_checks: bool) -> None:
    corr = report.correction
    if not corr or corr.status == "not_needed":
        return
    if corr.status != "suggested":
        st.info(corr.message)
        return
    k, icon, label = RECHECK.get(corr.reverification, ("neutral", "–", "Not re-checked"))
    body = "".join(f'<p>{esc(s.text)} <span class="cite">[{esc(s.source_id)} §{esc(s.section)}]</span></p>'
                   for s in corr.sentences)
    st.markdown(f'<div class="tg-fix"><div class="tg-col-label how">TrustGuard\'s suggested answer '
                f'(from the policy in effect)</div>{body}<div>{raw_chip(k, icon, label)}</div>'
                f'<div class="tg-source">{esc(corr.reverification_note)}</div></div>', unsafe_allow_html=True)
    with st.expander("How the suggested answer was re-checked", expanded=show_checks):
        st.caption("Different methods from the ones that wrote the suggestion, so TrustGuard isn't marking its own "
                   "homework. A and B are plain code; C is a separate classifier model.")
        for i, s in enumerate(corr.sentences, 1):
            st.markdown(f"**Sentence {i}:** {s.text}")
            for name, res in s.checks.items():
                ck, ci = CHECK_ICON.get(res["result"], ("neutral", "–"))
                st.markdown(f'{raw_chip(ck, ci, CHECK_NAMES.get(name, name))} '
                            f'<span class="tg-source">{esc(res["detail"])}</span>', unsafe_allow_html=True)


def render_feedback(report: Report) -> None:
    done_key = f"fb_done_{report.turn_id}"
    if st.session_state.get(done_key):
        st.caption("Thanks, your feedback was recorded.")
        return
    st.markdown('<div class="tg-col-label">Was this check helpful and correct?</div>', unsafe_allow_html=True)
    rating = st.feedback("thumbs", key=f"fb_{report.turn_id}")
    if rating == 1:
        event_log.log_feedback(report.turn_id, "up", report=report)
        st.session_state[done_key] = True
        st.rerun()
    elif rating == 0:
        with st.form(f"fb_form_{report.turn_id}"):
            reason = st.selectbox("What was wrong?", [
                "TrustGuard flagged a correct answer", "TrustGuard missed a wrong answer",
                "Wrong policy or section cited", "Suggested answer is wrong", "Explanation is unclear", "Other"])
            comment = st.text_area("Details (optional). Please don't include customer data.", max_chars=500)
            if st.form_submit_button("Send feedback"):
                event_log.log_feedback(report.turn_id, "down", reason, screen(comment).text or "", report)
                st.session_state[done_key] = True
                st.rerun()


def render_findings(report: Report, key: str) -> None:
    level, message = report.overall
    issue = level != "success"
    c = report.counts
    count_chips = "".join(chip(s, f"{c[s]} {STATUS[s]['label'].lower()}")
                          for s in (CONTRADICTED, INSUFFICIENT_EVIDENCE, SUPPORTED) if c[s])
    if report.missing:
        count_chips += raw_chip("bad", "✕", f"{len(report.missing)} required step{'s' if len(report.missing) != 1 else ''} missing")
    if report.needs_review:
        count_chips += raw_chip("rev", "!", "Needs a person to review")
    st.markdown(f'<div class="tg-verdict tg-{VERDICT_KEY[level]}" role="status">'
                f'<div class="big" aria-hidden="true">{VERDICT_ICON[level]}</div>'
                f'<div><div class="msg">{esc(message)}</div><div class="counts">{count_chips}</div></div></div>',
                unsafe_allow_html=True)
    reliability_link()
    notes = list(report.input_notes) + ([report.as_of_note] if report.as_of_note else [])
    for n in notes:
        st.caption(f":material/info: {n}")
    for w in report.coverage_warnings:
        st.warning(w)

    def details(full: bool) -> None:
        if report.results:
            st.markdown('<div class="tg-legend">' + "".join(
                f'<div>{chip(s)}<span>{STATUS[s]["meaning"]}</span></div>' for s in STATUS) + "</div>",
                unsafe_allow_html=True)
        problems = [r for r in report.results if r.status != SUPPORTED]
        fine = [r for r in report.results if r.status == SUPPORTED]
        for r in problems:
            claim_card(r, key, full=True)
        if fine and (full or audit):
            for r in fine:
                claim_card(r, key, full=True)
        elif fine:
            with st.expander(f"{len(fine)} supported claim{'s' if len(fine) != 1 else ''}: show how"):
                for r in fine:
                    claim_card(r, key, full=True)
        render_completeness(report, show_all=audit or (full and not issue))

    if audit:
        details(full=True)
    elif issue:
        details(full=False)
    else:
        with st.expander("Show how TrustGuard verified this answer"):
            details(full=True)
    render_correction(report, key, show_checks=audit)

    h, t = report.handoff, report.timings
    if audit and h and h.sources:
        with st.expander("What the assistant read (audit trail; TrustGuard does its own search)"):
            for src in h.sources:
                st.markdown(f"- {src['title']}, version {src['version']} ({src['status']}), section "
                            f"{src['section']} {src['section_title']}")
    st.caption(f"Agent 1 ({h.model if h else '?'}) answered in {t.get('agent1_s', 0)} s. TrustGuard "
               f"({report.trustguard_model}) took {t.get('trustguard_total_s', 0)} s: claims "
               f"{t.get('extraction_s', 0)} s, verification {t.get('verification_s', 0)} s, completeness "
               f"{t.get('completeness_s', 0)} s, correction and re-check "
               f"{round(t.get('correction_s', 0) + t.get('reverification_s', 0), 2)} s.")
    cols = st.columns([1, 1])
    with cols[0]:
        render_feedback(report)
    with cols[1]:
        st.download_button("Download TrustGuard report (JSON)", json.dumps(report.to_dict(), indent=2, default=str),
                           file_name=f"trustguard_report_{report.turn_id}.json", mime="application/json",
                           key=f"dl_{key}")


def typing(text: str):
    """Shows Agent 1's finished answer word by word, like a chat assistant."""
    for word in text.split(" "):
        yield word + " "
        time.sleep(0.03)


# ---------- the conversation ----------
with st.chat_message("assistant", avatar=A1_AVATAR):
    st.markdown('<div class="tg-agent">AGENT 1 · BANKING AI ASSISTANT</div>', unsafe_allow_html=True)
    st.markdown("Hi! I can answer questions about Northbridge Bank's staff policies and branch procedures: "
                "travel and expense claims, cash withdrawals, account opening for foreign nationals and fee "
                "waivers. Type your question below.")

for i, turn in enumerate(st.session_state.turns):
    with st.chat_message("user", avatar=USER_AVATAR):
        st.markdown(USER_MARK, unsafe_allow_html=True)
        st.markdown(turn["question"])
    if turn["kind"] == "reply":  # input checks or a non-policy message: nothing to verify
        with st.chat_message("assistant", avatar=TG_AVATAR if turn.get("guard") else A1_AVATAR):
            st.markdown(f'<div class="tg-agent{" tg-a2" if turn.get("guard") else ""}">'
                        f'{"INPUT CHECK" if turn.get("guard") else "AGENT 1 · BANKING AI ASSISTANT"}</div>',
                        unsafe_allow_html=True)
            st.markdown(turn["reply"])
            if turn.get("note"):
                st.caption(turn["note"])
        continue
    rep = turn["report"]
    with st.chat_message("assistant", avatar=A1_AVATAR):
        st.markdown('<div class="tg-agent">AGENT 1 · BANKING AI ASSISTANT</div>', unsafe_allow_html=True)
        st.markdown(rep.answer)
        st.markdown(verdict_chip(rep), unsafe_allow_html=True)
    with st.chat_message("TrustGuard", avatar=TG_AVATAR):
        st.markdown('<div class="tg-agent tg-a2">TRUSTGUARD · VERIFICATION LAYER</div>', unsafe_allow_html=True)
        render_findings(rep, f"t{i}")


def add_reply(question: str, reply: str, guard: bool, note: str = "") -> None:
    st.session_state.turns.append({"kind": "reply", "question": question, "reply": reply, "guard": guard,
                                   "note": note})
    st.rerun()


typed = st.chat_input("Ask the Banking AI Assistant about a policy or procedure…", disabled=assistant is None,
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
        notes = [n for n in (checked.message, intent.note) if n]

        # ---- Agent 1 answers in real time ----
        with st.chat_message("assistant", avatar=A1_AVATAR):
            st.markdown('<div class="tg-agent">AGENT 1 · BANKING AI ASSISTANT</div>', unsafe_allow_html=True)
            with st.spinner("Searching the knowledge base and writing an answer…"):
                handoff = assistant.answer(intent.question)
            if not handoff.answer:
                raise InputError("The assistant returned an empty answer. Try asking again.")
            st.write_stream(typing(handoff.answer))
            badge = st.empty()
            badge.markdown(held_chip(), unsafe_allow_html=True)

        # ---- TrustGuard intercepts, derives, compares, corrects and re-checks ----
        with st.chat_message("TrustGuard", avatar=TG_AVATAR):
            intercept_banner()
            ctx = PolicyContext.for_question(default_registry(), handoff.question)
            with st.status("TrustGuard is checking the answer…", expanded=True) as status:
                def on_stage(stage, data):
                    if stage == "policy":
                        st.write(f"Policy validation: using the versions in effect on {fmt(data.as_of)}.")
                    elif stage == "claims":
                        st.write(f"Split the answer into {len(data)} claim{'s' if len(data) != 1 else ''}. "
                                 "Working out what the policy says for each…" if data else
                                 "No checkable claims in the answer.")
                    elif stage == "verified":
                        st.write("Compared each claim with the policy. Checking nothing required is missing…")
                    elif stage == "completeness" and data.missing:
                        st.write(f"{len(data.missing)} required step(s) missing. Writing a suggested answer…")
                    elif stage == "correction":
                        st.write("Re-checking the suggested answer with independent methods (A, B, C)…")
                report = run_pipeline(handoff.question, handoff.answer, retriever, llm, ctx=ctx, nli=nli,
                                      on_stage=on_stage)
                report.handoff, report.input_notes = handoff, notes
                report.timings = {"agent1_s": handoff.latency_s, **report.timings}
                status.update(label=f"TrustGuard finished in {report.timings['trustguard_total_s']:.1f} s",
                              state="complete", expanded=False)
        badge.markdown(verdict_chip(report), unsafe_allow_html=True)
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
