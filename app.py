"""TrustGuard AI — employee-facing verification dashboard.

Run:  python -m streamlit run app.py

This file is presentation only. All verification logic lives in modules/, so what
the judges see is exactly what the tests exercise.

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
  --navy:#1B2F7A; --royal:#2346A8; --violet:#7B5CE6; --lav:#EEF0FB; --lav-2:#D9DEF6; --neutral:#44546A; --neutral-bg:#EEF1F5;
}
html, body, .stApp, .stMarkdown, input, textarea, button, label, [data-testid="stSidebar"] {
  font-family:'Public Sans', system-ui, sans-serif !important;
}
/* Clear Streamlit's fixed toolbar so nothing at the top of the page is hidden under it */
.block-container {padding-top:4.5rem; max-width:1080px;}
.stApp {background:#F7F8FE;}
a, a:visited {color:var(--violet);}
*:focus-visible {outline:3px solid var(--violet) !important; outline-offset:2px;}

/* Header band */
.tg-hero {background:var(--royal); color:#fff; border-radius:14px; padding:1.5rem 1.8rem 1.4rem;
  border-bottom:5px solid var(--violet); margin-bottom:1.2rem;}
.tg-hero h1 {color:#fff !important; font-size:2.1rem; font-weight:700; margin:0 0 0.4rem 0; padding:0;
  display:flex; align-items:center; gap:0.6rem;}
.tg-hero p {color:#E4E8FB; font-size:1.02rem; max-width:68ch; margin:0;}
.tg-hero .tg-pill {display:inline-block; background:rgba(255,255,255,0.14); color:#fff; border-radius:999px;
  padding:0.15rem 0.7rem; font-size:0.8rem; font-weight:600; margin-top:0.8rem; margin-right:0.4rem;}

/* Sidebar in royal navy */
[data-testid="stSidebar"] {background:var(--navy);}
[data-testid="stSidebar"] h3, [data-testid="stSidebar"] p, [data-testid="stSidebar"] li,
[data-testid="stSidebar"] strong, [data-testid="stSidebar"] .tg-kb, [data-testid="stSidebar"] .tg-kb .t {color:#fff;}
[data-testid="stSidebar"] .tg-kb small, [data-testid="stSidebar"] [data-testid="stCaptionContainer"] p {color:#C3CBEF;}
[data-testid="stSidebar"] h3 {border-bottom:2px solid var(--violet); padding-bottom:0.3rem;}
[data-testid="stSidebar"] [data-testid="stAlertContainer"] {background:#FFF3D6 !important; border-radius:8px;}
[data-testid="stSidebar"] [data-testid="stAlertContainer"] p {color:#7A5200 !important;}
[data-testid="stSidebar"] button svg {fill:#fff; color:#fff;}

/* Lavender panels for the input steps; inputs stay white so they stand out */
.stApp .st-key-panel_input, .stApp .st-key-panel_verify {background:var(--lav); border-color:var(--lav-2) !important;}
.st-key-panel_input input, .st-key-panel_input textarea,
.st-key-panel_input [data-baseweb="select"] > div {background:#fff !important;}
.stButton button[kind="secondary"] {border-color:var(--royal); color:var(--royal); background:#fff;}
.stButton button[kind="secondary"]:hover {background:var(--lav-2); color:var(--navy); border-color:var(--navy);}
.stButton button[kind="primary"] {background:var(--royal); border-color:var(--royal);}
.stButton button[kind="primary"]:hover {background:var(--navy); border-color:var(--navy);}
/* Claim cards: white on the tinted page */
[class*="st-key-card_"] {background:#fff;}
h1, h2, h3 {color:var(--ink); letter-spacing:-0.01em;}
.tg-lede {color:var(--ink-2); font-size:1.02rem; max-width:68ch; margin:-0.4rem 0 1.2rem 0;}
.tg-step {font-weight:600; font-size:1.1rem; color:var(--navy); margin:0.3rem 0 0.2rem 0;}
.tg-step span {display:inline-block; width:1.6rem; height:1.6rem; line-height:1.6rem; text-align:center;
  border-radius:50%; background:var(--violet); color:#fff; font-size:0.85rem; margin-right:0.5rem;}
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

.tg-legend {background:#fff; border:1px solid var(--lav-2); border-radius:8px; padding:0.6rem 0.9rem; display:flex; flex-wrap:wrap; gap:0.5rem 1.2rem; color:var(--ink-2); font-size:0.85rem; margin:0.2rem 0 0.8rem 0;}
.tg-legend div {display:flex; gap:0.45rem; align-items:center;}

.tg-card {border-left:5px solid currentColor; padding:0.2rem 0 0.1rem 1rem;}
.tg-card-head {display:flex; gap:0.6rem; align-items:center; flex-wrap:wrap; margin-bottom:0.7rem;}
.tg-claimno {color:var(--ink-3); font-size:0.9rem; font-weight:600;}
.tg-compare {display:grid; grid-template-columns:1fr 1fr; gap:1rem;}
.tg-col-label {color:var(--ink-3); font-size:0.82rem; font-weight:600; margin-bottom:0.3rem;}
.tg-doc {font-family:'Source Serif 4', Georgia, serif; font-size:1.06rem; line-height:1.55; color:var(--ink);
  background:#fff; border:1px solid var(--rule); border-radius:6px; padding:0.7rem 0.85rem;}
.tg-doc.empty {font-family:'Public Sans', system-ui, sans-serif; color:var(--ink-3); font-size:0.92rem; background:var(--lav);}
.tg-col-label.policy {color:var(--royal);}
.tg-source {color:var(--ink-2); font-size:0.82rem; margin-top:0.35rem;}
.tg-why {color:var(--ink); margin:0.8rem 0 0.2rem 0; max-width:80ch;}
.tg-why strong {color:var(--ink-2);}
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
st.markdown('<div class="tg-hero"><h1><span aria-hidden="true">🛡️</span>TrustGuard AI</h1>'
            '<p>Check an AI assistant\'s answer against approved bank policy, one claim at a time. TrustGuard '
            'shows what the policy supports, contradicts, or cannot confirm. It does not guarantee that an '
            'answer is correct.</p>'
            '<span class="tg-pill">Claim-by-claim checks</span><span class="tg-pill">Cited policy evidence</span>'
            '<span class="tg-pill">Fictional demo data</span></div>', unsafe_allow_html=True)


# ---------- cached resources (loaded once per server, not per click) ----------
@st.cache_resource(show_spinner=False)
def get_retriever():
    chunks = load_knowledge_base()
    embedder, warning = make_embedder()
    return EvidenceRetriever(chunks, embedder), warning


@st.cache_resource(show_spinner=False)
def get_llm():
    return get_client()


@st.cache_data
def demo_cases():
    with open(config.ROOT / "tests" / "test_cases.json", encoding="utf-8") as f:
        return json.load(f)["cases"]


with st.spinner("Loading policy documents and the search model. The first start can take 1–2 minutes "
                "while the model downloads."):
    retriever, retrieval_warning = get_retriever()
try:
    llm, llm_error = get_llm(), None
except LLMError as e:
    llm, llm_error = None, str(e)

if llm is None:
    st.error(f"Verification is unavailable: {llm_error}")
elif llm.name == "mock":
    st.markdown('<div class="tg-mock">Mock mode: offline keyword heuristics, not real verification. '
                'Set LLM_PROVIDER=gemini (or claude) in .env before any demo.</div>', unsafe_allow_html=True)


# ---------- sidebar: what the system is using (Learnability, Perceivability) ----------
with st.sidebar:
    st.markdown("### System")
    model_name = ("offline mock (not real verification)" if llm and llm.name == "mock"
                  else getattr(llm, "model", "") if llm else "not available")
    st.markdown(f"**Language model**  \n{model_name}")
    st.markdown(f"**Evidence search**  \n{retriever.embedder.label}")
    if retrieval_warning:
        st.warning(retrieval_warning)
    st.markdown(f"**Policy sections searched**  \n{len(retriever.chunks)} "
                f"({retriever.excluded} from superseded versions are excluded)")

    st.markdown("### Policy documents")
    for doc in load_metadata():
        in_use = doc["status"] in config.SEARCHABLE_STATUSES
        tag = (chip(SUPPORTED, "In use") if in_use
               else '<span class="tg-chip tg-neutral"><b aria-hidden="true">–</b>Superseded, not searched</span>')
        st.markdown(f'<div class="tg-kb">{tag}<br><b class="t">{html.escape(doc["title"])}</b><br>'
                    f'<small>Version {doc["version"]}, effective {doc["effective_date"]}</small></div>',
                    unsafe_allow_html=True)
    st.caption("All policies are fictional and used for demonstration only. No real OCBC data is used.")


# ---------- step 1: input ----------
cases = demo_cases()
CUSTOM = "Write my own"
labels = [CUSTOM] + [c["label"] for c in cases]


def load_example():
    case = next((c for c in cases if c["label"] == st.session_state.example), None)
    st.session_state.question = case["question"] if case else ""
    st.session_state.answer = case["answer"] if case else ""
    st.session_state.pop("report", None)


def clear_all():
    st.session_state.example = CUSTOM
    st.session_state.question = ""
    st.session_state.answer = ""
    st.session_state.pop("report", None)


with st.container(border=True, key="panel_input"):
    st.markdown('<div class="tg-step"><span>1</span>Enter the question and the AI\'s answer</div>', unsafe_allow_html=True)
    st.markdown('<p class="tg-help">Pick a prepared example to fill both boxes, or write your own. '
                'Choosing an example only fills the boxes; nothing runs until you press Verify answer.</p>',
                unsafe_allow_html=True)
    st.selectbox("Example", labels, key="example", on_change=load_example)
    st.text_input("Question the employee asked the AI assistant", key="question",
                  placeholder="What are the reimbursement rules for overseas business travel?",
                  help="Gives TrustGuard context, e.g. what 'it' or 'they' refer to in the answer.")
    st.text_area("The AI assistant's answer", key="answer", height=110,
                 placeholder="Paste the answer exactly as the AI assistant gave it.",
                 help="Up to 4,000 characters. Each factual statement in it is checked separately.")

# ---------- step 2: verify ----------
with st.container(border=True, key="panel_verify"):
    st.markdown('<div class="tg-step"><span>2</span>Verify the answer</div>', unsafe_allow_html=True)
    st.markdown('<p class="tg-help">TrustGuard splits the answer into claims, finds the matching policy sections, '
                'and checks each claim. This usually takes 5–15 seconds.</p>', unsafe_allow_html=True)
    b1, b2, _ = st.columns([1.3, 1, 4])
    run = b1.button("Verify answer", type="primary", disabled=llm is None, use_container_width=True)
    b2.button("Clear", on_click=clear_all, use_container_width=True)

if run:
    try:
        question, answer = validate_inputs(st.session_state.question, st.session_state.answer)
        report = Report(question=question, answer=answer)
        with st.status("Verifying the answer…", expanded=True) as status:
            st.write("Splitting the answer into separate claims…")
            t0 = time.perf_counter()
            claims = extract_claims(question, answer, llm)
            report.coverage_warnings = coverage_check([c.claim for c in claims], answer)
            t1 = time.perf_counter()
            if claims:
                st.write(f"Found {len(claims)} claim{'s' if len(claims) != 1 else ''}:")
                for c in claims:
                    st.write(f"  {c.claim_id}. {c.claim}")
                st.write("Searching the policies and checking each claim…")
                report.results = verify_claims(claims, question, retriever, llm)
            else:
                st.write("No checkable factual claims were found.")
            t2 = time.perf_counter()
            report.timings = {"extraction_s": round(t1 - t0, 2), "verification_s": round(t2 - t1, 2)}
            status.update(label=f"Verified {len(report.results)} claim{'s' if len(report.results) != 1 else ''} in {t2 - t0:.1f} seconds",
                          state="complete", expanded=False)
        st.session_state.report = report
        st.toast("Verification complete. See the results below.", icon="✅")
    except InputError as e:
        st.warning(str(e))
    except LLMError as e:
        st.error(f"Verification could not run. {e}")
    except Exception as e:  # never show a raw traceback to judges
        st.error(f"Verification stopped because of an unexpected error ({type(e).__name__}: {e}). "
                 "Try again; if it repeats, restart the app.")


# ---------- step 3: results ----------
report: Report | None = st.session_state.get("report")
st.markdown('<div class="tg-step" style="margin-top:1.6rem"><span>3</span>Read the findings</div>', unsafe_allow_html=True)

if not report:
    st.markdown('<p class="tg-help">Results appear here after you press Verify answer: an overall verdict, '
                'then each claim next to the policy text it was checked against.</p>', unsafe_allow_html=True)
else:
    # Feedback: warn if the boxes were edited after this report was produced
    if (st.session_state.get("question", "").strip() != report.question
            or st.session_state.get("answer", "").strip() != report.answer):
        st.markdown('<div class="tg-stale">You have changed the question or answer since this check. '
                    'The findings below are for the previous text. Press Verify answer to check the new text.</div>',
                    unsafe_allow_html=True)

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
        with st.container(border=True, key=f"card_{r.claim_id}"):
            st.markdown(
                f'<div class="tg-card tg-{s["key"]}" style="background:transparent">'
                f'<div class="tg-card-head">{chip(r.status)}<span class="tg-claimno">Claim {r.claim_id}</span>{review}</div>'
                f'<div class="tg-compare">'
                f'<div><div class="tg-col-label">The AI answer says</div><div class="tg-doc">{html.escape(r.claim)}</div></div>'
                f'<div><div class="tg-col-label policy">The approved policy says</div>{evidence}</div>'
                f'</div>'
                f'<div class="tg-why"><strong>Why: </strong>{html.escape(r.explanation)}</div></div>',
                unsafe_allow_html=True)
            with st.expander("How this was checked"):
                for check in r.rule_checks:
                    st.markdown(f"- {check}")
                st.markdown(f"**Policy sections found by the search** (similarity score; sections below "
                            f"{retriever.min_relevance} are treated as unrelated)")
                for p in r.retrieved:
                    st.markdown(f"- `{p['score']:.3f}` {p['source_id']} section {p['section']} "
                                f"{p['section_title']}: _{p['text'][:160]}…_")

    with st.expander("Original question and answer"):
        st.markdown(f"**Question:** {report.question}\n\n**Answer:** {report.answer}")

    st.caption(f"Claim extraction took {report.timings.get('extraction_s', 0)} s and checking took "
               f"{report.timings.get('verification_s', 0)} s.")
    st.download_button("Download this report (JSON)", json.dumps(report.to_dict(), indent=2),
                       file_name="trustguard_report.json", mime="application/json")
