"""Review queue: the Branch Operations Head's view of answers employees sent for human review.

The reviewer sees the question, the assistant's answer and TrustGuard's findings, then either
confirms TrustGuard, writes the correct answer, or marks the assistant's answer as correct. The
decision appears in the employee's chat. In production this would be the reviewer's work queue
(with a notification); in the demo it is a page in the same app.
"""
import html

import streamlit as st

from modules import review_queue
from ui_theme import apply_base_theme, page_nav

st.set_page_config(page_title="Review queue · TrustGuard", page_icon="🛡️", layout="wide", initial_sidebar_state="expanded")
apply_base_theme()


def esc(text) -> str:
    return html.escape(str(text or ""))


VERDICT = {"error": ("bad", "✕", "TrustGuard: don't use this answer"),
           "warning": ("unk", "?", "TrustGuard: use with care"),
           "success": ("ok", "✓", "TrustGuard: matches the SOP"),
           "info": ("neutral", "–", "TrustGuard: nothing to check")}


def mark(key: str, symbol: str, text: str) -> str:
    return f'<span class="tg-st tg-{key}"><b aria-hidden="true"><span>{symbol}</span></b>{esc(text)}</span>'


with st.sidebar:
    page_nav()

st.markdown('<div class="tg-top"><div class="tg-eyebrow">Northbridge Bank · Branch Operations Head</div>'
            '<h1>Review <em>queue</em>.</h1>'
            '<p>Answers that staff sent for a human decision because TrustGuard couldn\'t give a clear ✓. '
            'Your decision is shown to the employee in their chat.</p>'
            '<div class="tg-note">Demo: in production this would be the reviewer\'s own work queue, with a notification.'
            '</div></div>', unsafe_allow_html=True)

all_cases = review_queue.cases()
waiting = [c for c in all_cases.values() if c["status"] == "waiting"]
done = [c for c in all_cases.values() if c["status"] == "decided"]


def case_header(c: dict) -> str:
    key, sym, label = VERDICT.get(c.get("overall"), VERDICT["info"])
    flag = ' · <span class="tg-small">flagged for review by TrustGuard</span>' if c.get("needs_review") else ""
    return (f'<div class="tg-agent"><span>Case {esc(c["case_id"])}</span>'
            f'<span>{esc((c.get("requested_at") or "")[:16].replace("T", " "))} UTC</span></div>'
            f'<p>{mark(key, sym, label)}{flag}</p>'
            f'<div class="tg-lbl">Employee asked</div><div class="tg-q">{esc(c["question"])}</div>'
            f'<div class="tg-lbl">Assistant answered</div><div class="tg-q">{esc(c["answer"])}</div>'
            + (f'<div class="tg-lbl">TrustGuard suggested</div><div class="tg-q">{esc(c["suggested_answer"])}</div>'
               if c.get("suggested_answer") else ""))


def findings(c: dict) -> None:
    rep = c.get("report") or {}
    rows = []
    for r in rep.get("results", []):
        status = {"SUPPORTED": ("ok", "✓", "Matches the SOP"), "CONTRADICTED": ("bad", "✕", "Doesn't match"),
                  "INSUFFICIENT_EVIDENCE": ("unk", "?", "Can't confirm")}.get(r.get("status"), ("neutral", "–", ""))
        src = f' <span class="tg-cite">{esc(r.get("source_id"))} §{esc(r.get("section"))}</span>' if r.get("source_id") else ""
        rows.append(f'<li>{mark(*status)}<div><b>{esc(r.get("claim"))}</b>SOP says: {esc(r.get("evidence") or "nothing in effect covers this")}{src}'
                    + (f'<br><span class="tg-small">{esc(r.get("root_cause"))}</span>' if r.get("root_cause") else "")
                    + '</div></li>')
    missing = (rep.get("completeness") or {}).get("missing") or []
    for m in missing:
        rows.append(f'<li>{mark("bad", "✕", "Missing")}<div><b>{esc(m)}</b></div></li>')
    if rows:
        st.markdown(f'<ul class="tg-list">{"".join(rows)}</ul>', unsafe_allow_html=True)
    else:
        st.markdown('<div class="tg-empty">No statement-level findings.</div>', unsafe_allow_html=True)


tab_wait, tab_done = st.tabs([f"Waiting · {len(waiting)}", f"Done · {len(done)}"])

with tab_wait:
    if not waiting:
        st.markdown('<div class="tg-empty">Nothing waiting. Cases appear here when an employee clicks '
                    '“Ask the Branch Operations Head”.</div>', unsafe_allow_html=True)
    for c in waiting:
        with st.container(border=True, key=f"case_{c['case_id']}"):
            st.markdown(case_header(c), unsafe_allow_html=True)
            with st.expander("TrustGuard's findings"):
                findings(c)
            with st.form(f"decide_{c['case_id']}"):
                choice = st.radio("Your decision", list(review_queue.DECISIONS),
                                  format_func=review_queue.DECISIONS.get, horizontal=True,
                                  index=0 if c.get("suggested_answer") else 1)
                text = st.text_area("Answer the employee should use (only for “Corrected answer”)",
                                    value=c.get("suggested_answer", ""), max_chars=1500)
                note = st.text_input("Note to the employee (optional)", max_chars=300)
                if st.form_submit_button("Send decision", type="primary"):
                    if choice == "corrected" and not text.strip():
                        st.warning("Write the corrected answer first.")
                    else:
                        review_queue.decide(c["case_id"], choice, text if choice == "corrected" else "", note)
                        st.rerun()

with tab_done:
    if not done:
        st.markdown('<div class="tg-empty">No decisions yet.</div>', unsafe_allow_html=True)
    for c in done:
        with st.container(border=True, key=f"done_{c['case_id']}"):
            st.markdown(case_header(c), unsafe_allow_html=True)
            use = review_queue.answer_to_use(c)
            st.markdown(f'<p>{mark("ok", "✓", review_queue.DECISIONS[c["decision"]])} '
                        f'<span class="tg-small">{esc((c.get("decided_at") or "")[:16].replace("T", " "))} UTC</span></p>'
                        + (f'<div class="tg-lbl">Answer sent to the employee</div><div class="tg-q">{esc(use)}</div>' if use else "")
                        + (f'<p class="tg-small">Note: {esc(c["note"])}</p>' if c.get("note") else ""),
                        unsafe_allow_html=True)
