"""Improvements: the continuous-improvement loop from the pitch (slide 7), built from the logs.

Record errors -> collect feedback -> identify patterns -> recommend fixes -> report, with a person
approving every fix and a before / after count to see whether it worked. The analysis lives in
modules/improvement.py; this page only shows it and records the approve / reject decisions.
"""
import html
import json

import streamlit as st

from modules import improvement
from ui_theme import MESH, apply_base_theme, page_nav

st.set_page_config(page_title="Improvements · TrustGuard", page_icon="🛡️", layout="wide",
                   initial_sidebar_state="expanded")
apply_base_theme()

st.markdown("""
<style>
.im-flow {display:flex; flex-wrap:wrap; justify-content:center; align-items:center; gap:0.45rem; margin:1.1rem 0 0;
  position:relative;}
.im-flow span {font-family:var(--mono); font-size:0.68rem; text-transform:uppercase; letter-spacing:.06em;
  background:var(--glass); color:var(--link-on); border-radius:999px; padding:0.35rem 0.75rem; box-shadow:var(--raise-sm);
  animation:tg-rise .5s cubic-bezier(.2,.7,.2,1) both;}
.im-flow span:nth-child(3) {animation-delay:.08s;} .im-flow span:nth-child(5) {animation-delay:.16s;}
.im-flow span:nth-child(7) {animation-delay:.24s;} .im-flow span:nth-child(9) {animation-delay:.32s;}
.im-flow span:nth-child(11) {animation-delay:.4s;}
.im-flow i {color:var(--ink-3); font-style:normal;}
.im-flow span.h {background:var(--cobalt); color:#fff;}
.im-stats {display:grid; grid-template-columns:repeat(auto-fit, minmax(170px, 1fr)); gap:0.9rem; margin:0 0 1.4rem;}
.im-stat {background:var(--surface); border-radius:22px; box-shadow:var(--raise-sm); padding:0.9rem 1.1rem;
  animation:tg-rise .5s cubic-bezier(.2,.7,.2,1) both;}
.im-stat .k {font-family:var(--mono); font-size:0.66rem; color:var(--ink-3); text-transform:uppercase; letter-spacing:.07em;}
.im-stat .v {font-size:1.8rem; font-weight:600; color:var(--ink); margin-top:0.2rem;}
.im-stat .n {font-size:0.8rem; color:var(--ink-2);}
.im-h {font-size:1.15rem; font-weight:600; color:var(--ink); margin:0.4rem 0 0.2rem;}
.im-sub {color:var(--ink-3); font-size:0.88rem; margin:0 0 0.9rem;}
.im-card {display:grid; grid-template-columns:3.6rem 1fr; gap:1rem; align-items:start;}
.im-count {width:3.4rem; height:3.4rem; border-radius:18px; background:var(--blue-soft); color:var(--link-on);
  display:flex; flex-direction:column; align-items:center; justify-content:center; font-weight:600; font-size:1.3rem; line-height:1;}
.im-count small {font-family:var(--mono); font-size:0.55rem; text-transform:uppercase; letter-spacing:.05em; margin-top:0.2rem;}
.im-count.hot {background:var(--cobalt); color:#fff;}
.im-tags {display:flex; flex-wrap:wrap; gap:0.4rem; margin-bottom:0.3rem;}
.im-tag {font-family:var(--mono); font-size:0.64rem; text-transform:uppercase; letter-spacing:.06em; border-radius:999px;
  padding:0.18rem 0.55rem; background:var(--inset); color:var(--ink-2);}
.im-tag.rec {background:var(--unk-bg); color:var(--unk);} .im-tag.app {background:var(--ok-bg); color:var(--ok);}
.im-tag.rej {background:var(--inset); color:var(--ink-3);} .im-tag.wait {background:var(--blue-soft); color:var(--link-on);}
.im-what {font-weight:600; color:var(--ink); font-size:1rem;}
.im-topic {color:var(--ink-2); font-size:0.9rem; margin-top:0.1rem;}
.im-q {color:var(--ink-3); font-size:0.82rem; margin-top:0.45rem;}
.im-q li {margin:0.1rem 0;}
.im-fix {margin-top:0.7rem; background:var(--field); box-shadow:var(--sink); border-radius:16px; padding:0.65rem 0.85rem;
  font-size:0.9rem; color:var(--ink);}
.im-fix b {font-family:var(--mono); font-size:0.64rem; text-transform:uppercase; letter-spacing:.07em; color:var(--ink-3);
  display:block; margin-bottom:0.15rem; font-weight:500;}
.im-fix .own {color:var(--ink-3); font-size:0.8rem; margin-top:0.3rem;}
.im-out {margin:0.8rem 0 0.2rem; display:flex; align-items:center; gap:0.6rem; font-size:0.86rem; color:var(--ink-2);}
.im-out .bars {display:flex; align-items:flex-end; gap:4px; height:34px;}
.im-out .bars i {width:22px; border-radius:6px 6px 3px 3px; background:var(--bad); animation:rv-grow2 .9s ease-out both;}
.im-out .bars i.after {background:var(--ok);}
@keyframes rv-grow2 {from {height:0;}}
[class*="st-key-pat_"] {background:var(--surface); border-radius:26px; box-shadow:var(--raise-md); padding:1.1rem 1.3rem;
  margin-bottom:0.9rem; animation:tg-rise .5s cubic-bezier(.2,.7,.2,1) both; transition:transform .2s;}
[class*="st-key-pat_"]:hover {transform:translateY(-2px);}
</style>
""", unsafe_allow_html=True)


def esc(text) -> str:
    return html.escape(str(text or ""))


def day(ts) -> str:
    return improvement._day(ts)


with st.sidebar:
    page_nav()

st.markdown('<div class="tg-hero-wrap tg-rise">' + MESH + '<div class="tg-top">'
            '<div class="tg-eyebrow">Continuous improvement · from the logs</div>'
            '<h1>What should we <span class="tg-grad">fix</span> next?</h1>'
            '<p>TrustGuard groups the mistakes it found, what reviewers decided and what staff reported into '
            'recurring problems, and suggests a fix for each. Nothing changes until a person approves it.</p>'
            '<div class="im-flow"><span>01 Record errors</span><i>→</i><span>02 Collect feedback</span><i>→</i>'
            '<span>03 Find patterns</span><i>→</i><span>04 Suggest fixes</span><i>→</i>'
            '<span class="h">Human approval</span><i>→</i><span>05 Report and monitor</span></div>'
            '</div></div>', unsafe_allow_html=True)

s = improvement.summary()
ps = improvement.patterns()
st.markdown(
    '<div class="im-stats">'
    f'<div class="im-stat"><div class="k">Answers checked</div><div class="v">{s["checks"]}</div>'
    f'<div class="n">{s["flagged"]} flagged by TrustGuard</div></div>'
    f'<div class="im-stat" style="animation-delay:.06s"><div class="k">Reviewer decisions</div><div class="v">{s["reviews"]}</div>'
    f'<div class="n">{s["agreed"]} agreed with TrustGuard</div></div>'
    f'<div class="im-stat" style="animation-delay:.12s"><div class="k">Staff said "check was wrong"</div>'
    f'<div class="v">{s["thumbs_down"]}</div><div class="n">from the 👍 / 👎 under each check</div></div>'
    f'<div class="im-stat" style="animation-delay:.18s"><div class="k">Problems to look at</div>'
    f'<div class="v">{sum(1 for p in ps if p["status"] == "waiting")}</div>'
    f'<div class="n">{sum(1 for p in ps if p["count"] > 1)} happened more than once</div></div>'
    '</div>', unsafe_allow_html=True)

top = st.columns([3, 1.1, 1.1], vertical_alignment="bottom")
with top[0]:
    st.markdown('<div class="im-h">Recurring problems and suggested fixes</div>'
                '<div class="im-sub">Most frequent first. Suggestions come from fixed rules, not AI, so the same '
                'problem always gets the same suggestion.</div>', unsafe_allow_html=True)
with top[1]:
    st.download_button("Report", improvement.report_markdown(), file_name="trustguard_improvement_report.md",
                       mime="text/markdown", icon=":material/description:", use_container_width=True,
                       help="One-page summary for the teams who own the fixes (step 05).")
with top[2]:
    st.download_button("Test cases", json.dumps(improvement.review_test_cases(), indent=2, ensure_ascii=False),
                       file_name="review_test_cases.json", mime="application/json", icon=":material/science:",
                       use_container_width=True,
                       help="Every reviewer decision as a candidate test case, so TrustGuard is re-tested on the "
                            "cases a person had to settle.")

if not ps:
    st.info("Nothing logged yet. Ask a few questions on the Assistant page (and send one to the review queue); "
            "the problems TrustGuard finds will be grouped here.")

for p in ps:
    with st.container(key=f"pat_{p['id']}"):
        tags = []
        if p["count"] > 1:
            tags.append('<span class="im-tag rec">Recurring</span>')
        tags.append({"waiting": '<span class="im-tag wait">Waiting for approval</span>',
                     "approved": f'<span class="im-tag app">✓ Approved {esc(day(p["decided_at"]))}</span>',
                     "rejected": f'<span class="im-tag rej">Rejected {esc(day(p["decided_at"]))}</span>'}[p["status"]])
        tags.append(f'<span class="im-tag">{esc(day(p["first"]))}'
                    f'{" – " + esc(day(p["last"])) if day(p["last"]) != day(p["first"]) else ""}</span>')
        qs = "".join(f"<li>{esc(q)}</li>" for q in p["questions"])
        outcome = ""
        if p["status"] == "approved":
            b, a = p.get("before", 0), p.get("after", 0)
            top_n = max(b, a, 1)
            outcome = ('<div class="im-out"><div class="bars">'
                       f'<i style="height:{max(b / top_n * 34, 3):.0f}px" title="Before approval: {b}"></i>'
                       f'<i class="after" style="height:{max(a / top_n * 34, 3):.0f}px" title="Since approval: {a}"></i>'
                       f'</div><div><b>{b}</b> before approval · <b>{a}</b> since. '
                       + ("No new cases so far." if a == 0 else "Still happening: check the fix was carried out.")
                       + '</div></div>')
        st.markdown(
            f'<div class="im-card"><div class="im-count{" hot" if p["count"] > 1 else ""}">{p["count"]}'
            f'<small>{"times" if p["count"] != 1 else "time"}</small></div><div>'
            f'<div class="im-tags">{"".join(tags)}</div>'
            f'<div class="im-what">{esc(p["what"])}</div><div class="im-topic">{esc(p["topic"])}</div>'
            + (f'<ul class="im-q">{qs}</ul>' if qs else "")
            + f'<div class="im-fix"><b>Suggested fix</b>{esc(p["fix"])}<div class="own">Owner: {esc(p["owner"])}</div></div>'
            + outcome + '</div></div>', unsafe_allow_html=True)
        if p["status"] == "waiting":
            c1, c2, _ = st.columns([1, 1, 3])
            if c1.button("Approve fix", key=f"ok_{p['id']}", type="primary", icon=":material/check:",
                         use_container_width=True):
                improvement.decide(p["id"], "approved")
                st.rerun()
            if c2.button("Reject", key=f"no_{p['id']}", icon=":material/close:", use_container_width=True):
                improvement.decide(p["id"], "rejected")
                st.rerun()

st.caption(f"Approvals are recorded as the {improvement.APPROVER} in logs/improvements.jsonl. In production this page "
           "would read the bank's central logs, and approved fixes would go to the owning team's backlog.")
