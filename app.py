"""TrustGuard AI — two-agent demo: Agent 1 (Banking AI Assistant) answers the
employee, Agent 2 (TrustGuard) intercepts that answer and verifies it before it is shown.

Run:  python -m streamlit run app.py

This file is presentation only. Agent 1 lives in modules/banking_assistant.py and all
verification logic in the other modules/, so what the judges see is what the tests exercise.

Design principles applied (see README "Interface design"):
  Perceivability  status = icon + word + colour (never colour alone); claim and policy side by side
  Predictability  numbered steps in the order things happen; buttons say exactly what they do
  Learnability    plain-language helper text; a status key next to the findings
  Feedback        visible loading, live stage-by-stage progress, stale-result notice, clear errors
  Consistency     one status vocabulary (same icon, label, colour) used everywhere
"""
import html
import json
import time

import streamlit as st

import config
from modules.claim_extractor import extract_claims
from modules.claim_verifier import verify_claims
from modules.banking_assistant import AssistantError, BankingAssistant, build_agent1_retriever
from modules.document_loader import load_knowledge_base, load_metadata
from modules.evidence_retriever import EvidenceRetriever, make_embedder
from modules.llm_client import LLMError, get_client
from modules.pipeline import InputError, Report, validate_inputs
from modules.policy_rules import coverage_check
from modules.schemas import CONTRADICTED, INSUFFICIENT_EVIDENCE, SUPPORTED

st.set_page_config(page_title="TrustGuard AI", page_icon="🛡️", layout="wide")

# One status vocabulary for the whole app (Consistency). The icon and the word carry the
# meaning; colour reinforces it, so colour-blind users lose nothing (Perceivability).
STATUS = {
    SUPPORTED: {"key": "ok", "icon": "✓", "label": "Supported",
                "meaning": "The approved policy states this."},
    CONTRADICTED: {"key": "bad", "icon": "✕", "label": "Contradicted",
                   "meaning": "The approved policy says something different."},
    INSUFFICIENT_EVIDENCE: {"key": "unk", "icon": "?", "label": "Insufficient evidence",
                            "meaning": "No approved policy confirms or rules this out."},
}
VERDICT_KEY = {"error": "bad", "warning": "unk", "success": "ok", "info": "neutral"}
VERDICT_ICON = {"error": "✕", "warning": "?", "success": "✓", "info": "–"}

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Public+Sans:wght@400;500;600;700&family=Source+Serif+4:opsz,wght@8..60,400;8..60,600&display=swap');
:root {
  --ink:#14233A; --ink-2:#44546A; --ink-3:#66758A; --rule:#CBD3DE; --desk:#EEF1F5;
  --ok:#17663F; --ok-bg:#E3F2EA; --bad:#A8201A; --bad-bg:#FBE9E7;
  --unk:#7A5200; --unk-bg:#FFF3D6; --rev:#3F4A5C; --rev-bg:#E6E9EF;
  --wis-side:#EFEFFB; --wis-line:#C9C9F0; --wis-hero:#E1E1F8; --wis-ink:#2B2D7A; --wis-panel:#F8F8FE;
  --cobalt:#2850C8; --wis-acc:#A3A1EC; --neutral:#44546A; --neutral-bg:#EEF1F5;
}
html, body, .stApp, .stMarkdown, input, textarea, button, label, [data-testid="stSidebar"] {
  font-family:'Public Sans', system-ui, sans-serif !important;
}
/* Clear Streamlit's fixed toolbar so nothing at the top of the page is hidden under it */
.block-container {padding-top:4.5rem; max-width:1080px;}
.stApp {background:#FCFCFF;}
a, a:visited {color:var(--cobalt);}
*:focus-visible {outline:3px solid var(--cobalt) !important; outline-offset:2px;}

/* Wisteria + cobalt (light). Large areas pale wisteria; cobalt only where action or emphasis is needed. */
.tg-hero {background:var(--wis-hero); color:var(--wis-ink); border:1px solid var(--wis-line); border-radius:14px;
  padding:1.5rem 1.8rem 1.4rem; border-bottom:5px solid var(--wis-acc); margin-bottom:1.2rem;}
.tg-hero h1 {color:var(--wis-ink) !important; font-size:2.1rem; font-weight:700; margin:0 0 0.4rem 0; padding:0;
  display:flex; align-items:center; gap:0.6rem;}
.tg-hero p {color:#3E4170; font-size:1.02rem; max-width:68ch; margin:0;}
.tg-hero .tg-pill {display:inline-block; background:#fff; color:var(--cobalt); border:1px solid var(--wis-line);
  border-radius:999px; padding:0.15rem 0.7rem; font-size:0.8rem; font-weight:600; margin-top:0.8rem; margin-right:0.4rem;}

/* Sidebar: pale wisteria, dark text */
[data-testid="stSidebar"] {background:var(--wis-side); border-right:1px solid var(--wis-line);}
[data-testid="stSidebar"] h3 {color:var(--wis-ink); border-bottom:2px solid var(--wis-acc); padding-bottom:0.3rem;}
[data-testid="stSidebar"] .tg-kb .t {color:var(--wis-ink);}

/* Wisteria panels for the input steps; inputs stay white so they stand out */
.stApp .st-key-panel_input, .stApp .st-key-panel_verify {background:var(--wis-panel); border-color:var(--wis-line) !important;}
.st-key-panel_input input, .st-key-panel_input textarea,
.st-key-panel_input [data-baseweb="select"] > div {background:#fff !important;}
.stButton button[kind="secondary"] {border-color:var(--cobalt); color:var(--cobalt); background:#fff;}
.stButton button[kind="secondary"]:hover {background:var(--wis-hero); color:var(--wis-ink); border-color:var(--wis-ink);}
.stButton button[kind="primary"] {background:var(--cobalt); border-color:var(--cobalt); color:#fff;}
.stButton button[kind="primary"]:hover {background:#1E3FA3; border-color:#1E3FA3;}
/* Claim cards: white on the tinted page */
[class*="st-key-card_"] {background:#fff;}
h1, h2, h3 {color:var(--ink); letter-spacing:-0.01em;}
.tg-lede {color:var(--ink-2); font-size:1.02rem; max-width:68ch; margin:-0.4rem 0 1.2rem 0;}
.tg-step {font-weight:600; font-size:1.1rem; color:var(--wis-ink); margin:0.3rem 0 0.2rem 0;}
.tg-step span {display:inline-block; width:1.6rem; height:1.6rem; line-height:1.6rem; text-align:center;
  border-radius:50%; background:var(--cobalt); color:#fff; font-size:0.85rem; margin-right:0.5rem;}
.tg-help {color:var(--ink-3); font-size:0.88rem; margin:0 0 0.6rem 0; max-width:72ch;}

.tg-chip {display:inline-flex; align-items:center; gap:0.35rem; padding:0.18rem 0.6rem; border-radius:6px;
  font-size:0.85rem; font-weight:600; border:1px solid currentColor; white-space:nowrap;}
.tg-chip b {font-size:0.95rem;}
.tg-ok {color:var(--ok); background:var(--ok-bg);}  .tg-bad {color:var(--bad); background:var(--bad-bg);}
.tg-unk {color:var(--unk); background:var(--unk-bg);} .tg-rev {color:var(--rev); background:var(--rev-bg);}
.tg-neutral {color:var(--neutral); background:var(--neutral-bg);}

.tg-verdict {display:flex; gap:0.9rem; align-items:flex-start; padding:1rem 1.2rem; border-radius:8px;
  border-left:6px solid currentColor; margin:0.6rem 0 0.8rem 0;}
.tg-verdict .big {font-size:1.6rem; font-weight:700; line-height:1;}
.tg-verdict .msg {color:var(--ink); font-weight:600; font-size:1.05rem;}
.tg-verdict .counts {display:flex; flex-wrap:wrap; gap:0.4rem; margin-top:0.55rem;}

.tg-legend {background:#fff; border:1px solid var(--wis-line); border-radius:8px; padding:0.6rem 0.9rem; display:flex; flex-wrap:wrap; gap:0.5rem 1.2rem; color:var(--ink-2); font-size:0.85rem; margin:0.2rem 0 0.8rem 0;}
.tg-legend div {display:flex; gap:0.45rem; align-items:center;}

.tg-card {border-left:5px solid currentColor; padding:0.2rem 0 0.1rem 1rem;}
.tg-card-head {display:flex; gap:0.6rem; align-items:center; flex-wrap:wrap; margin-bottom:0.7rem;}
.tg-claimno {color:var(--ink-3); font-size:0.9rem; font-weight:600;}
.tg-compare {display:grid; grid-template-columns:1fr 1fr; gap:1rem;}
.tg-col-label {color:var(--ink-3); font-size:0.82rem; font-weight:600; margin-bottom:0.3rem;}
.tg-doc {font-family:'Source Serif 4', Georgia, serif; font-size:1.06rem; line-height:1.55; color:var(--ink);
  background:#fff; border:1px solid var(--rule); border-radius:6px; padding:0.7rem 0.85rem;}
.tg-doc.empty {font-family:'Public Sans', system-ui, sans-serif; color:var(--ink-3); font-size:0.92rem; background:var(--wis-panel);}
.tg-col-label.policy {color:var(--cobalt);}
.tg-source {color:var(--ink-2); font-size:0.82rem; margin-top:0.35rem;}
.tg-why {color:var(--ink); margin:0.8rem 0 0.2rem 0; max-width:80ch;}
.tg-why strong {color:var(--ink-2);}
.tg-flow {display:flex; align-items:stretch; gap:0.5rem; margin:0 0 1.2rem 0; flex-wrap:wrap;}
.tg-flow div {flex:1 1 140px; background:#fff; border:1px solid var(--wis-line); border-radius:8px; padding:0.5rem 0.75rem;}
.tg-flow div.a1 {border-top:4px solid var(--wis-acc);} .tg-flow div.a2 {border-top:4px solid var(--cobalt);}
.tg-flow b {display:block; color:var(--wis-ink); font-size:0.88rem;} .tg-flow span {color:var(--ink-3); font-size:0.82rem;}
.tg-flow i {align-self:center; color:var(--ink-3); font-style:normal; font-weight:700;}
.tg-answer {font-size:1.08rem; line-height:1.6; color:var(--ink); background:#fff; border:1px solid var(--rule);
  border-left:6px solid currentColor; border-radius:8px; padding:0.9rem 1.1rem; margin:0.3rem 0 0.4rem 0;}
.tg-answer .who {display:block; font-size:0.8rem; font-weight:600; color:var(--ink-3); margin-bottom:0.35rem;}
.tg-answer p {color:var(--ink); margin:0;}
.tg-agent {font-size:0.78rem; font-weight:700; letter-spacing:0.02em; color:var(--ink-3); margin-bottom:0.2rem;}
.tg-agent.tg-a2 {color:var(--cobalt);}
.tg-intercept {display:flex; gap:0.6rem; align-items:center; background:var(--wis-hero); border:1px dashed var(--cobalt);
  color:var(--wis-ink); border-radius:8px; padding:0.55rem 0.9rem; font-weight:600; margin:0.1rem 0 0.6rem 0;}
.tg-intercept small {display:block; font-weight:400; color:var(--ink-2);}
.tg-held {margin-top:0.4rem;}
[data-testid="stChatMessage"] {background:transparent;}
@media (max-width:720px) {.tg-compare {grid-template-columns:1fr;} .block-container {padding-top:4rem;}}

.tg-mock {background:#3F4A5C; color:#fff; padding:0.7rem 1rem; border-radius:8px; font-weight:600; margin-bottom:0.8rem;}
.tg-stale {background:var(--desk); border:1px dashed var(--ink-3); color:var(--ink-2); padding:0.6rem 0.9rem;
  border-radius:8px; font-size:0.92rem; margin:0.4rem 0;}
.tg-kb {font-size:0.86rem; margin-bottom:0.6rem; color:var(--ink);}
.tg-kb small {color:var(--ink-3);}
</style>
""", unsafe_allow_html=True)


def chip(status: str, text: str | None = None) -> str:
    s = STATUS[status]
    return f'<span class="tg-chip tg-{s["key"]}"><b aria-hidden="true">{s["icon"]}</b>{text or s["label"]}</span>'


# ---------- header first, so the page is never blank while loading (Feedback) ----------
st.markdown('<div class="tg-hero"><h1><span aria-hidden="true">🏦</span>Northbridge Bank AI Assistant</h1>'
            '<p>Ask about staff policies and procedures. Every answer is intercepted by '
            '<b>TrustGuard</b>, an independent verification layer, and checked against approved bank policy '
            'before you rely on it.</p>'
            '<span class="tg-pill">Agent 1 answers live</span><span class="tg-pill">🛡️ Checked by TrustGuard</span>'
            '<span class="tg-pill">Fictional demo data</span></div>',
            unsafe_allow_html=True)

# The flow, drawn once so the audience always sees which agent does what (Learnability)
st.markdown(
    '<div class="tg-flow" aria-label="How the two agents work together">'
    '<div><b>You</b><span>ask a question</span></div><i aria-hidden="true">→</i>'
    '<div class="a1"><b>Agent 1 · Banking AI Assistant</b><span>answers in real time</span></div><i aria-hidden="true">→</i>'
    '<div class="a2"><b>🛡️ TrustGuard</b><span>intercepts the answer and checks each claim</span></div><i aria-hidden="true">→</i>'
    '<div><b>You</b><span>know which parts to trust, with evidence</span></div></div>', unsafe_allow_html=True)


# ---------- cached resources (loaded once per server, not per click) ----------
@st.cache_resource(show_spinner=False)
def get_retrievers():
    """Two separate indexes: TrustGuard's (approved documents only) and Agent 1's own
    (scope set by AGENT1_KB_SCOPE). The embedding model is loaded once and shared."""
    chunks = load_knowledge_base()
    embedder, warning = make_embedder()
    return EvidenceRetriever(chunks, embedder), build_agent1_retriever(chunks, embedder), warning


@st.cache_resource(show_spinner=False)
def get_llm():
    return get_client()


@st.cache_resource(show_spinner=False)
def get_agent1_llm():
    return get_client(model=config.AGENT1_MODEL or None)


@st.cache_data
def demo_questions():
    with open(config.KNOWLEDGE_BASE_DIR / "demo_questions.json", encoding="utf-8") as f:
        return json.load(f)["questions"]


with st.spinner("Loading policy documents and the search model. The first start can take 1–2 minutes "
                "while the model downloads."):
    retriever, agent1_retriever, retrieval_warning = get_retrievers()
try:
    llm, agent1_llm, llm_error = get_llm(), get_agent1_llm(), None
    assistant = BankingAssistant(agent1_llm, agent1_retriever)
except (LLMError, AssistantError) as e:
    llm, agent1_llm, assistant, llm_error = None, None, None, str(e)

if llm is None:
    st.error(f"Verification is unavailable: {llm_error}")
elif llm.name == "mock":
    st.markdown('<div class="tg-mock">Mock mode: offline keyword heuristics, not real verification. '
                'Set LLM_PROVIDER=gemini (or claude) in .env before any demo.</div>', unsafe_allow_html=True)


# ---------- sidebar: examples first, system details one click away ----------
questions = demo_questions()


def ask(question: str) -> None:
    st.session_state.pending_question = question


with st.sidebar:
    st.markdown("### Example questions")
    for i, q in enumerate(questions):
        st.button(q["label"], key=f"ex_side_{i}", help=q["question"], on_click=ask, args=(q["question"],),
                  use_container_width=True, disabled=assistant is None)
    st.button("Clear conversation", on_click=lambda: st.session_state.update(turns=[]), use_container_width=True)

    SCOPE_TEXT = {"all": "Everything, including superseded policies and an unofficial intranet FAQ, "
                         "with no version labels (simulates a bulk-loaded index nobody cleaned up)",
                  "approved": "Approved documents only", "none": "No documents (general knowledge only)"}
    st.markdown("### How the demo is set up")
    with st.expander("🏦 Agent 1 · Banking AI Assistant"):
        st.markdown(f"**Language model**  \n{assistant.model if assistant else 'not available'}")
        st.markdown(f"**Can read**  \n{SCOPE_TEXT.get(config.AGENT1_KB_SCOPE, config.AGENT1_KB_SCOPE)}")
        if agent1_retriever is not None:
            st.markdown(f"**Reads per question**  \nTop {config.AGENT1_TOP_K} passages")
    with st.expander("🛡️ TrustGuard · verification layer"):
        model_name = ("offline mock (not real verification)" if llm and llm.name == "mock"
                      else getattr(llm, "model", "") if llm else "not available")
        st.markdown(f"**Language model**  \n{model_name}")
        st.markdown(f"**Evidence search**  \n{retriever.embedder.label}")
        st.markdown(f"**Policy sections searched**  \n{len(retriever.chunks)} from approved documents "
                    f"({retriever.excluded} superseded or unofficial sections are excluded)")
    if retrieval_warning:
        st.warning(retrieval_warning)
    with st.expander("📄 Policy documents"):
        st.caption("TrustGuard only uses Approved documents. Agent 1 may read all of them, depending on its settings.")
        for doc in load_metadata():
            in_use = doc["status"] in config.SEARCHABLE_STATUSES
            tag = (chip(SUPPORTED, "Approved") if in_use
                   else f'<span class="tg-chip tg-neutral"><b aria-hidden="true">–</b>{html.escape(doc["status"])}, '
                        'TrustGuard ignores it</span>')
            st.markdown(f'<div class="tg-kb">{tag}<br><b class="t">{html.escape(doc["title"])}</b><br>'
                        f'<small>Version {doc["version"]}, effective {doc["effective_date"]}</small></div>',
                        unsafe_allow_html=True)
    st.caption("All policies are fictional and used for demonstration only. No real OCBC data is used.")


# ---------- the conversation ----------
# Agent 1 is the product the employee uses. TrustGuard appears as a second agent that
# steps into the conversation after every answer: it intercepts, checks, and labels it.
A1_AVATAR, TG_AVATAR, USER_AVATAR = "🏦", "🛡️", "🧑‍💼"
VERDICT_LABEL = {"error": "TrustGuard: do not rely on this answer",
                 "warning": "TrustGuard: use with caution",
                 "success": "TrustGuard: verified against approved policy",
                 "info": "TrustGuard: no checkable facts in this answer"}
st.session_state.setdefault("turns", [])


def held_chip() -> str:
    return ('<div class="tg-held"><span class="tg-chip tg-rev"><b aria-hidden="true">⏸</b>'
            'Intercepted by TrustGuard: checking before delivery</span></div>')


def verdict_chip(report: Report) -> str:
    level, _ = report.overall
    return (f'<div class="tg-held"><span class="tg-chip tg-{VERDICT_KEY[level]}">'
            f'<b aria-hidden="true">{VERDICT_ICON[level]}</b>{VERDICT_LABEL[level]}</span></div>')


def intercept_banner() -> None:
    st.markdown('<div class="tg-agent tg-a2">TRUSTGUARD · VERIFICATION LAYER</div>'
                '<div class="tg-intercept"><span aria-hidden="true">🛡️</span><div>Answer intercepted'
                '<small>TrustGuard is checking the assistant\'s answer against approved policy before it is '
                'delivered.</small></div></div>', unsafe_allow_html=True)


def render_findings(report: Report, turn: int) -> None:
    level, message = report.overall
    c = report.counts
    count_chips = "".join(chip(s, f"{c[s]} {STATUS[s]['label'].lower()}")
                          for s in (CONTRADICTED, INSUFFICIENT_EVIDENCE, SUPPORTED) if c[s])
    review_chip = ('<span class="tg-chip tg-rev"><b aria-hidden="true">!</b>Needs a person to review</span>'
                   if report.needs_review else "")
    st.markdown(
        f'<div class="tg-verdict tg-{VERDICT_KEY[level]}" role="status">'
        f'<div class="big" aria-hidden="true">{VERDICT_ICON[level]}</div>'
        f'<div><div class="msg">{html.escape(message)}</div>'
        f'<div class="counts">{count_chips}{review_chip}</div></div></div>', unsafe_allow_html=True)

    for warning in report.coverage_warnings:
        st.warning(warning)
    if report.needs_review:
        st.info("An automated check disagreed with the AI's work on at least one claim, so those findings are "
                "marked for review. Open “How this was checked” on the marked claim for the reason.")
    if report.results:
        st.markdown('<div class="tg-legend">' + "".join(
            f'<div>{chip(s)}<span>{STATUS[s]["meaning"]}</span></div>' for s in STATUS) + "</div>",
            unsafe_allow_html=True)

    for r in report.results:
        s = STATUS[r.status]
        review = ('<span class="tg-chip tg-rev"><b aria-hidden="true">!</b>Needs review</span>'
                  if r.needs_review else "")
        if r.source_id:
            evidence = (f'<div class="tg-doc">{html.escape(r.evidence)}</div>'
                        f'<div class="tg-source">{html.escape(r.source_title)}, version {r.version}, '
                        f'section {r.section} {html.escape(r.section_title)}</div>')
        else:
            evidence = '<div class="tg-doc empty">No approved policy section addresses this claim.</div>'
        with st.container(border=True, key=f"card_{turn}_{r.claim_id}"):
            st.markdown(
                f'<div class="tg-card tg-{s["key"]}" style="background:transparent">'
                f'<div class="tg-card-head">{chip(r.status)}<span class="tg-claimno">Claim {r.claim_id}</span>{review}</div>'
                f'<div class="tg-compare">'
                f'<div><div class="tg-col-label">The assistant says</div><div class="tg-doc">{html.escape(r.claim)}</div></div>'
                f'<div><div class="tg-col-label policy">The approved policy says</div>{evidence}</div>'
                f'</div>'
                f'<div class="tg-why"><strong>Why: </strong>{html.escape(r.explanation)}</div></div>',
                unsafe_allow_html=True)
            with st.expander("How this was checked"):
                for check in r.rule_checks:
                    st.markdown(f"- {check}")
                st.markdown(f"**Policy sections found by TrustGuard's search** (similarity score; sections below "
                            f"{retriever.min_relevance} are treated as unrelated)")
                for p in r.retrieved:
                    st.markdown(f"- `{p['score']:.3f}` {p['source_id']} section {p['section']} "
                                f"{p['section_title']}: _{p['text'][:160]}…_")

    h = report.handoff
    if h and h.sources:
        with st.expander("What the assistant read (audit trail; TrustGuard does its own search)"):
            for src in h.sources:
                note = "" if src["status"] in config.SEARCHABLE_STATUSES else \
                    f" — **{src['status']}**, not approved policy"
                st.markdown(f"- {src['title']}, version {src['version']}, section {src['section']} "
                            f"{src['section_title']}{note}")
    t = report.timings
    st.caption(f"Agent 1 answered in {t.get('agent1_s', 0)} s. TrustGuard extracted claims in "
               f"{t.get('extraction_s', 0)} s and checked them in {t.get('verification_s', 0)} s.")
    st.download_button("Download TrustGuard report (JSON)", json.dumps(report.to_dict(), indent=2),
                       file_name="trustguard_report.json", mime="application/json", key=f"dl_{turn}")


def typing(text: str):
    """Shows Agent 1's finished answer word by word, like a chat assistant. The answer is
    generated in full first (TrustGuard needs the whole answer), then displayed."""
    for word in text.split(" "):
        yield word + " "
        time.sleep(0.03)


# --- welcome message from Agent 1 ---
with st.chat_message("assistant", avatar=A1_AVATAR):
    st.markdown('<div class="tg-agent">AGENT 1 · BANKING AI ASSISTANT</div>', unsafe_allow_html=True)
    st.markdown("Hi! I can answer questions about Northbridge Bank's staff policies, such as travel claims, "
                "allowances and expense procedures. Ask me anything below, or try an example:")
    if not st.session_state.turns:
        cols = st.columns(3)
        for i, q in enumerate(questions[:6]):
            cols[i % 3].button(q["label"], key=f"ex_main_{i}", help=q["question"], on_click=ask,
                               args=(q["question"],), use_container_width=True, disabled=assistant is None)

# --- earlier turns ---
for i, rep in enumerate(st.session_state.turns):
    latest = i == len(st.session_state.turns) - 1
    with st.chat_message("user", avatar=USER_AVATAR):
        st.markdown(rep.question)
    with st.chat_message("assistant", avatar=A1_AVATAR):
        st.markdown('<div class="tg-agent">AGENT 1 · BANKING AI ASSISTANT</div>', unsafe_allow_html=True)
        st.markdown(rep.answer)
        st.markdown(verdict_chip(rep), unsafe_allow_html=True)
    with st.chat_message("TrustGuard", avatar=TG_AVATAR):
        st.markdown('<div class="tg-agent tg-a2">TRUSTGUARD · VERIFICATION LAYER</div>', unsafe_allow_html=True)
        if st.toggle("Show TrustGuard's check", value=latest, key=f"show_{i}"):
            render_findings(rep, i)

# --- a new question: Agent 1 answers live, then TrustGuard intercepts ---
typed = st.chat_input("Ask the Banking AI Assistant about staff policy…", disabled=assistant is None)
question = typed or st.session_state.pop("pending_question", None)

if question:
    turn = len(st.session_state.turns)
    with st.chat_message("user", avatar=USER_AVATAR):
        st.markdown(question)
    try:
        # Step 1: Agent 1 answers in real time
        with st.chat_message("assistant", avatar=A1_AVATAR):
            st.markdown('<div class="tg-agent">AGENT 1 · BANKING AI ASSISTANT</div>', unsafe_allow_html=True)
            with st.spinner("Searching the knowledge base and writing an answer…"):
                handoff = assistant.answer(question)
            if not handoff.answer:
                raise InputError("The assistant returned an empty answer. Try asking again.")
            st.write_stream(typing(handoff.answer))
            badge = st.empty()
            badge.markdown(held_chip(), unsafe_allow_html=True)

        # Step 2: TrustGuard intercepts the finished answer and verifies it
        with st.chat_message("TrustGuard", avatar=TG_AVATAR):
            intercept_banner()
            q, a = validate_inputs(handoff.question, handoff.answer)
            report = Report(question=q, answer=a, handoff=handoff)
            with st.status("TrustGuard is verifying the answer…", expanded=True) as status:
                st.write("Received the question and answer from Agent 1 (not its sources).")
                st.write("Splitting the answer into separate factual claims…")
                t0 = time.perf_counter()
                claims = extract_claims(q, a, llm)
                report.coverage_warnings = coverage_check([c.claim for c in claims], a)
                t1 = time.perf_counter()
                if claims:
                    st.write(f"Found {len(claims)} claim{'s' if len(claims) != 1 else ''}:")
                    for c in claims:
                        st.write(f"  {c.claim_id}. {c.claim}")
                    st.write("Searching approved policies and checking each claim…")
                    report.results = verify_claims(claims, q, retriever, llm)
                else:
                    st.write("No checkable factual claims were found in the answer.")
                t2 = time.perf_counter()
                report.timings = {"agent1_s": handoff.latency_s, "extraction_s": round(t1 - t0, 2),
                                  "verification_s": round(t2 - t1, 2)}
                status.update(label=f"TrustGuard checked {len(report.results)} claim"
                                    f"{'s' if len(report.results) != 1 else ''} in {t2 - t0:.1f} seconds",
                              state="complete", expanded=False)
            render_findings(report, turn)

        # Step 3: the verdict goes back onto the assistant's answer
        badge.markdown(verdict_chip(report), unsafe_allow_html=True)
        st.session_state.turns.append(report)
    except (InputError, AssistantError) as e:
        st.warning(str(e))
    except LLMError as e:
        st.error(f"The assistant or TrustGuard could not run. {e}")
    except Exception as e:  # never show a raw traceback to judges
        st.error(f"Something went wrong ({type(e).__name__}: {e}). Try again; if it repeats, restart the app.")
