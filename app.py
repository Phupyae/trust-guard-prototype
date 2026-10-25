"""TrustGuard AI — employee-facing verification dashboard.

Run:  streamlit run app.py

This file is presentation only. All verification logic lives in modules/, so what
the judges see is exactly what the tests exercise.
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
from modules.schemas import CONTRADICTED, INSUFFICIENT_EVIDENCE, SUPPORTED

st.set_page_config(page_title="TrustGuard AI", page_icon="🛡️", layout="wide")

STATUS_STYLE = {
    SUPPORTED: ("Supported", "#1E7B4F", "#E7F4ED"),
    CONTRADICTED: ("Contradicted", "#B42318", "#FDECEA"),
    INSUFFICIENT_EVIDENCE: ("Insufficient evidence", "#9A6700", "#FFF5DB"),
}

st.markdown("""
<style>
.block-container {padding-top: 2rem; max-width: 1150px;}
.tg-badge {display:inline-block; padding:2px 10px; border-radius:999px; font-size:0.78rem;
           font-weight:600; letter-spacing:0.02em; text-transform:uppercase;}
.tg-claim {font-size:1.05rem; font-weight:600; margin:6px 0 4px 0;}
.tg-evidence {border-left:3px solid #1F3A5F; background:#F3F5F8; padding:10px 14px;
              border-radius:0 6px 6px 0; margin:8px 0 4px 0;}
.tg-source {font-size:0.82rem; color:#4B5563; margin-top:4px;}
.tg-review {display:inline-block; margin-left:8px; font-size:0.78rem; font-weight:600; color:#6B21A8;}
.tg-mock {background:#6B21A8; color:white; padding:10px 16px; border-radius:8px; font-weight:600;}
</style>
""", unsafe_allow_html=True)


# ---------- cached resources (loaded once per server, not per click) ----------
@st.cache_resource(show_spinner="Loading policy documents and embedding model…")
def get_retriever():
    chunks = load_knowledge_base()
    embedder, warning = make_embedder()
    return EvidenceRetriever(chunks, embedder), warning


@st.cache_resource
def get_llm():
    return get_client()


@st.cache_data
def demo_cases():
    with open(config.ROOT / "tests" / "test_cases.json") as f:
        return json.load(f)["cases"]


# ---------- sidebar: system transparency ----------
retriever, retrieval_warning = get_retriever()
try:
    llm, llm_error = get_llm(), None
except LLMError as e:
    llm, llm_error = None, str(e)

with st.sidebar:
    st.markdown("### System status")
    if llm:
        model = getattr(llm, "model", "offline heuristics")
        st.markdown(f"**Language model:** `{model}`")
    else:
        st.error(llm_error)
    st.markdown(f"**Retrieval:** {retriever.embedder.label}")
    if retrieval_warning:
        st.warning(retrieval_warning)
    st.markdown(f"**Searchable sections:** {len(retriever.chunks)}  \n"
                f"**Excluded (superseded):** {retriever.excluded}")

    st.markdown("### Knowledge base")
    for doc in load_metadata():
        icon = "🟢" if doc["status"] in config.SEARCHABLE_STATUSES else "⚪"
        st.markdown(f"{icon} **{doc['title']}**  \n"
                    f"<span style='font-size:0.8rem;color:#6B7280'>{doc['document_id']} · v{doc['version']} · "
                    f"{doc['status']} · effective {doc['effective_date']}</span>", unsafe_allow_html=True)
    st.caption("All policies are fictional and used for demonstration only. No real OCBC data is used.")


# ---------- header ----------
st.title("🛡️ TrustGuard AI")
st.markdown("**Check an AI assistant's answer against approved policy, one claim at a time.** "
            "TrustGuard does not guarantee an answer is correct; it shows what the approved evidence "
            "supports, contradicts, or cannot confirm.")
if llm and llm.name == "mock":
    st.markdown('<div class="tg-mock">MOCK MODE: offline keyword heuristics, not real verification. '
                'Set LLM_PROVIDER=claude before any demo.</div>', unsafe_allow_html=True)


# ---------- input ----------
cases = demo_cases()
labels = ["✏️ Custom input"] + [c["label"] for c in cases]


def load_example():
    choice = st.session_state.example
    case = next((c for c in cases if c["label"] == choice), None)
    st.session_state.question = case["question"] if case else ""
    st.session_state.answer = case["answer"] if case else ""
    st.session_state.pop("report", None)


st.selectbox("Start from a demonstration example, or enter your own", labels,
             key="example", on_change=load_example)
st.text_input("Employee's question to the AI assistant", key="question",
              placeholder="e.g. What are the reimbursement rules for overseas business travel?")
st.text_area("AI-generated answer to verify", key="answer", height=110,
             placeholder="Paste the assistant's answer here…")
run = st.button("Verify answer", type="primary", disabled=llm is None)


# ---------- run pipeline with visible stages ----------
if run:
    try:
        question, answer = validate_inputs(st.session_state.question, st.session_state.answer)
        report = Report(question=question, answer=answer)
        with st.status("Verifying answer…", expanded=True) as status:
            st.write("**1. Extracting factual claims…**")
            t0 = time.perf_counter()
            claims = extract_claims(question, answer, llm)
            t1 = time.perf_counter()
            st.write(f"→ {len(claims)} claim(s) found in {t1 - t0:.1f}s")
            if claims:
                st.write("**2–3. Retrieving evidence and verifying each claim…**")
                report.results = verify_claims(claims, question, retriever, llm)
            t2 = time.perf_counter()
            report.timings = {"extraction_s": round(t1 - t0, 2), "verification_s": round(t2 - t1, 2)}
            status.update(label=f"Verification complete in {t2 - t0:.1f}s", state="complete", expanded=False)
        st.session_state.report = report
    except InputError as e:
        st.warning(str(e))
    except LLMError as e:
        st.error(f"Verification could not run: {e}")
    except Exception as e:  # never show a raw traceback to judges
        st.error(f"Unexpected error: {type(e).__name__}: {e}")


# ---------- results ----------
def badge(status: str) -> str:
    label, fg, bg = STATUS_STYLE[status]
    return f'<span class="tg-badge" style="color:{fg};background:{bg}">{label}</span>'


report: Report | None = st.session_state.get("report")
if report:
    st.divider()
    level, message = report.overall
    getattr(st, level)(message)

    c = report.counts
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Claims checked", len(report.results))
    m2.metric("Supported", c[SUPPORTED])
    m3.metric("Contradicted", c[CONTRADICTED])
    m4.metric("Insufficient evidence", c[INSUFFICIENT_EVIDENCE])
    if report.needs_review:
        st.info("🔍 One or more findings are flagged for human review: the AI judgement and the "
                "automated rule checks did not fully agree.")

    with st.expander("Original AI answer", expanded=False):
        st.markdown(f"**Q:** {report.question}\n\n**A:** {report.answer}")

    st.subheader("Claim-by-claim findings")
    for r in report.results:
        with st.container(border=True):
            review = '<span class="tg-review">🔍 Human review suggested</span>' if r.needs_review else ""
            st.markdown(f"{badge(r.status)}{review}<div class='tg-claim'>Claim {r.claim_id}: "
                        f"{html.escape(r.claim)}</div>", unsafe_allow_html=True)
            st.markdown(r.explanation)
            if r.source_id:
                st.markdown(
                    f"<div class='tg-evidence'>{html.escape(r.evidence)}"
                    f"<div class='tg-source'>📄 {html.escape(r.source_title)} · v{r.version} · "
                    f"Section {r.section} {html.escape(r.section_title)} · <code>{r.source_id}</code></div></div>",
                    unsafe_allow_html=True)
            with st.expander("How this was checked"):
                for check in r.rule_checks:
                    st.markdown(f"- {check}")
                st.markdown("**Passages retrieved** (similarity score, higher = more related; "
                            f"relevance threshold {retriever.min_relevance}):")
                for p in r.retrieved:
                    st.markdown(f"- `{p['score']:.3f}` {p['source_id']} §{p['section']} "
                                f"{p['section_title']}: _{p['text'][:160]}…_")

    st.caption(f"Extraction {report.timings.get('extraction_s', 0)}s · "
               f"verification {report.timings.get('verification_s', 0)}s")
    st.download_button("Download verification report (JSON)",
                       json.dumps(report.to_dict(), indent=2),
                       file_name="trustguard_report.json", mime="application/json")
