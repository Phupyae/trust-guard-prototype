"""Evaluation results page: shows the numbers eval/compute_metrics.py wrote to metrics.json.

No API key or model is needed here; the page only reads files in eval/results/. To add a new
run, run the evaluation (see eval/README.md) and the run appears in the selector automatically.
"""
import html

import streamlit as st

from modules.eval_results import SCENARIO_NAMES, default_run, list_runs, ratio, seconds
from ui_theme import apply_base_theme, page_nav

st.set_page_config(page_title="TrustGuard AI · Evaluation", page_icon="📊", layout="wide")
apply_base_theme()

st.markdown("""
<style>
.ev-kind {border-radius:8px; padding:0.7rem 1rem; margin:0 0 1.2rem 0; font-size:0.95rem; color:var(--ink);
  border:1px solid var(--wis-line); background:#fff; border-left:6px solid var(--cobalt); max-width:80ch;}
.ev-kind b {color:var(--wis-ink);}
.ev-h2 {font-size:1.25rem; font-weight:700; color:var(--wis-ink); margin:1.6rem 0 0.2rem 0;}
.ev-sub {color:var(--ink-2); font-size:0.92rem; margin:0 0 0.8rem 0; max-width:75ch;}

/* System A vs System B: the headline comparison */
.ev-ab {display:grid; grid-template-columns:1fr 1fr; gap:1rem;}
.ev-sys {background:#fff; border:1px solid var(--rule); border-radius:10px; padding:1rem 1.2rem 1.1rem;
  border-top:6px solid currentColor;}
.ev-sys .who {font-size:0.82rem; font-weight:700; letter-spacing:0.02em; color:var(--ink-3); margin-bottom:0.5rem;}
.ev-sys .big {font-size:3rem; font-weight:700; line-height:1; color:var(--ink); margin:0.5rem 0 0.3rem;}
.ev-sys .what {color:var(--ink); font-size:1rem; max-width:40ch;}
.ev-sys .n {color:var(--ink-3); font-size:0.85rem; margin-top:0.2rem;}
.ev-track {height:12px; background:var(--neutral-bg); border-radius:6px; margin-top:0.8rem; overflow:hidden;}
.ev-track div {height:100%; background:currentColor; border-radius:0 4px 4px 0;}

/* Stat tiles */
.ev-tiles {display:grid; grid-template-columns:repeat(auto-fit, minmax(180px, 1fr)); gap:0.8rem;}
.ev-tile {background:#fff; border:1px solid var(--rule); border-radius:10px; padding:0.8rem 1rem;}
.ev-tile .k {color:var(--ink-2); font-size:0.85rem; font-weight:600; min-height:2.4em;}
.ev-tile .v {color:var(--ink); font-size:1.9rem; font-weight:700; line-height:1.15; margin-top:0.2rem;}
.ev-tile .n {color:var(--ink-3); font-size:0.82rem;}
.ev-tile .good {font-size:0.78rem; color:var(--ink-3); margin-top:0.3rem;}

/* Tables */
.ev-table {border-collapse:collapse; width:100%; background:#fff; font-size:0.92rem; margin:0.3rem 0 0.6rem;}
.ev-table th, .ev-table td {border:1px solid var(--rule); padding:0.45rem 0.7rem; text-align:right; color:var(--ink);}
.ev-table th {background:var(--wis-panel); color:var(--wis-ink); font-weight:600;}
.ev-table th:first-child, .ev-table td:first-child {text-align:left;}
.ev-table td.diag {background:var(--ok-bg); font-weight:700;}
.ev-table td.off {background:var(--bad-bg); font-weight:700;}
.ev-table caption {caption-side:top; text-align:left; color:var(--ink-3); font-size:0.82rem; padding-bottom:0.3rem;}
@media (max-width:720px) {.ev-ab {grid-template-columns:1fr;}}
</style>
""", unsafe_allow_html=True)


def esc(text) -> str:
    return html.escape(str(text if text is not None else ""))


def tile(title: str, metric: dict | None, good: str = "") -> str:
    value, n = ratio(metric)
    return (f'<div class="ev-tile"><div class="k">{esc(title)}</div><div class="v">{value}</div>'
            f'<div class="n">{esc(n)}</div>{f"<div class=good>{esc(good)}</div>" if good else ""}</div>')


def plain_tile(title: str, value: str, n: str = "", good: str = "") -> str:
    return (f'<div class="ev-tile"><div class="k">{esc(title)}</div><div class="v">{esc(value)}</div>'
            f'<div class="n">{esc(n)}</div>{f"<div class=good>{esc(good)}</div>" if good else ""}</div>')


def section(title: str, sub: str = "") -> None:
    st.markdown(f'<div class="ev-h2">{esc(title)}</div>' + (f'<p class="ev-sub">{sub}</p>' if sub else ""),
                unsafe_allow_html=True)


# ---------- header ----------
st.markdown('<div class="tg-hero"><h1><span aria-hidden="true">📊</span>Does TrustGuard make answers safer?</h1>'
            '<p>We asked the Banking AI Assistant (Agent 1) policy questions, let TrustGuard check every answer, '
            'and compared both against correct answers labelled by the team from the policy documents.</p>'
            '<span class="tg-pill">System A: Agent 1 alone</span>'
            '<span class="tg-pill">🛡️ System B: Agent 1 + TrustGuard</span></div>', unsafe_allow_html=True)

runs = list_runs()
with st.sidebar:
    page_nav()

if not runs:
    st.info("No evaluation results yet. Run `python eval/run_eval.py --controlled` (or `--live`), label the CSVs, "
            "then `python eval/compute_metrics.py eval/results/<folder>`. See eval/README.md.")
    st.stop()

default = default_run(runs)
with st.sidebar:
    st.markdown("### Results shown")
    run = st.selectbox("Evaluation run", runs, index=runs.index(default), format_func=lambda r: r.label,
                       help="Every folder in eval/results/ that has a metrics.json. Live runs are listed first "
                            "by default because they are the main evidence.")
    st.caption(f"Folder: eval/results/{run.folder}")

m = run.metrics
A, C = m.get("answers", {}), m.get("claims", {})
info = run.run_info

if run.kind == "controlled":
    st.markdown('<div class="ev-kind"><b>Controlled test.</b> Agent 1\'s answers here are <b>fixed answers written by '
                'the team</b>, each with a known error (or none). This checks that TrustGuard catches the errors we '
                'designed it for. It does not show how often a live assistant makes mistakes, and the sample is '
                f'small ({A.get("answers_total", 0)} answers, {C.get("claims_total", 0)} claims), so read the '
                'percentages with that in mind.</div>', unsafe_allow_html=True)
else:
    st.markdown('<div class="ev-kind"><b>Live test.</b> Agent 1 answered each question live, with nothing scripted. '
                f'{A.get("answers_labelled", 0)} of {A.get("answers_total", 0)} answers and '
                f'{C.get("claims_labelled", 0)} of {C.get("claims_total", 0)} claims have been labelled by the team; '
                'only labelled rows count towards the percentages.</div>', unsafe_allow_html=True)

# ---------- 1. headline ----------
section("1 · Wrong answers that reach the employee unchecked",
        "The question that matters to a bank: how often does an employee receive a wrong answer "
        "with nothing telling them not to rely on it?")
a_val, a_n = ratio(A.get("system_a_unflagged_wrong"))
b_val, b_n = ratio(A.get("system_b_unflagged_wrong"))


def bar(metric: dict | None) -> str:
    v = (metric or {}).get("value")
    width = 0 if v is None else max(v * 100, 0)
    return f'<div class="ev-track" aria-hidden="true"><div style="width:{width:.0f}%"></div></div>'


st.markdown(
    '<div class="ev-ab">'
    f'<div class="ev-sys tg-bad" style="background:#fff"><div class="who">SYSTEM A · AGENT 1 ALONE</div>'
    f'<span class="tg-chip tg-bad"><b aria-hidden="true">✕</b>No verification</span>'
    f'<div class="big">{a_val}</div><div class="what">of answers were wrong or incomplete and reached the employee '
    f'with no warning</div><div class="n">{esc(a_n)} answers</div>{bar(A.get("system_a_unflagged_wrong"))}</div>'
    f'<div class="ev-sys tg-ok" style="background:#fff"><div class="who">SYSTEM B · AGENT 1 + TRUSTGUARD</div>'
    f'<span class="tg-chip tg-ok"><b aria-hidden="true">✓</b>Checked by TrustGuard</span>'
    f'<div class="big">{b_val}</div><div class="what">of answers were wrong but still marked '
    f'“verified” by TrustGuard</div><div class="n">{esc(b_n)} answers</div>'
    f'{bar(A.get("system_b_unflagged_wrong"))}</div>'
    '</div>', unsafe_allow_html=True)

st.markdown('<div class="ev-tiles" style="margin-top:0.9rem">'
            + tile("Wrong answers TrustGuard flagged", A.get("wrong_answer_detection_rate"), "Higher is better")
            + tile("Correct answers flagged anyway (false alarms)", A.get("false_alarm_rate"), "Lower is better")
            + tile("Answers missing a required step that were caught", A.get("incomplete_answer_recall"),
                   "Higher is better")
            + plain_tile("TrustGuard time per answer (median)",
                         seconds(A.get("trustguard_seconds", {}).get("median")),
                         f'mean {seconds(A.get("trustguard_seconds", {}).get("mean"))} · '
                         f'slowest 5% {seconds(A.get("trustguard_seconds", {}).get("p95"))}', "Lower is better")
            + '</div>', unsafe_allow_html=True)

# ---------- 2. by scenario ----------
section("2 · Results by type of mistake",
        "Each question was designed to test one kind of mistake an assistant can make.")
rows = ""
for key, s in A.get("by_scenario", {}).items():
    rows += (f'<tr><td>{esc(SCENARIO_NAMES.get(key, key))}</td><td>{s["answers"]}</td><td>{s["agent1_wrong"]}</td>'
             f'<td>{s["wrong_caught"]} of {s["agent1_wrong"]}</td><td>{s["flagged"]}</td></tr>')
st.markdown('<table class="ev-table"><thead><tr><th>Type of question</th><th>Answers</th>'
            '<th>Agent 1 wrong</th><th>Wrong answers caught</th><th>Flagged by TrustGuard (total)</th></tr></thead>'
            f'<tbody>{rows}</tbody></table>', unsafe_allow_html=True)

# ---------- 3. claim level ----------
section("3 · Checking each claim",
        "TrustGuard splits every answer into single claims and gives each one a status. "
        "Here its status is compared with the team's label for the same claim.")
st.markdown('<div class="ev-tiles">'
            + tile("Claims given the right status", C.get("accuracy"), "Higher is better")
            + tile("Wrong claims marked Contradicted", C.get("critical_error_recall"),
                   "Critical error recall · higher is better")
            + tile("Correct claims flagged anyway", C.get("false_positive_rate"), "Lower is better")
            + tile("Citations pointing to the right policy section", C.get("citation_accuracy_auto"),
                   "Checked automatically · higher is better")
            + '</div>', unsafe_allow_html=True)

LABELS = [("SUPPORTED", "✓ Supported"), ("CONTRADICTED", "✕ Contradicted"),
          ("INSUFFICIENT_EVIDENCE", "? Insufficient evidence")]
conf = C.get("confusion", {})
if conf:
    head = "".join(f"<th>TrustGuard said: {lab}</th>" for _, lab in LABELS)
    body = ""
    for gold, glab in LABELS:
        cells = ""
        for pred, _ in LABELS:
            n = conf.get(gold, {}).get(pred, 0)
            cls = "diag" if gold == pred and n else ("off" if n else "")
            cells += f'<td class="{cls}">{n}</td>'
        body += f"<tr><td>Correct label: {glab}</td>{cells}</tr>"
    st.markdown('<table class="ev-table"><caption>Each row is the correct label; each column is what TrustGuard '
                'said. Green cells are agreements; anything in a red cell is a mistake.</caption>'
                f'<thead><tr><th></th>{head}</tr></thead><tbody>{body}</tbody></table>', unsafe_allow_html=True)

with st.expander("Precision, recall and F1 per status"):
    rows = ""
    for key, lab in LABELS:
        pc = C.get("per_class", {}).get(key)
        if pc:
            rows += (f'<tr><td>{lab}</td><td>{pc["precision"]}</td><td>{pc["recall"]}</td><td>{pc["f1"]}</td>'
                     f'<td>{pc["support"]}</td></tr>')
    st.markdown('<table class="ev-table"><thead><tr><th>Status</th><th>Precision</th><th>Recall</th><th>F1</th>'
                f'<th>Claims</th></tr></thead><tbody>{rows}</tbody></table>', unsafe_allow_html=True)
    st.caption(f"Macro F1 across the three statuses: {C.get('macro_f1', 'n/a')}. Precision: of the claims TrustGuard "
               "gave this status, how many really had it. Recall: of the claims that really had this status, how "
               "many TrustGuard found.")

# ---------- 4. corrections ----------
section("4 · Suggested corrections",
        "When an answer is wrong or incomplete, TrustGuard writes a suggested answer and re-checks it "
        "with three independent methods (A citation, B rules table, C entailment model).")
needs_person = "needs a person to judge the suggested answer"
st.markdown('<div class="ev-tiles">'
            + plain_tile("Corrections suggested", str(A.get("corrections_suggested", 0)))
            + tile("Corrections that passed all re-checks", A.get("correction_support_rate"), "Higher is better")
            + tile("Corrections judged correct by a person", A.get("correction_accuracy"),
                   "" if A.get("correction_accuracy", {}).get("den") else needs_person)
            + tile("Wrong answers fixed by the correction", A.get("wrong_answers_fixed_by_correction"),
                   "" if A.get("wrong_answers_fixed_by_correction", {}).get("den") else needs_person)
            + '</div>', unsafe_allow_html=True)
if not A.get("correction_accuracy", {}).get("den"):
    st.caption("Passing the automatic re-checks is not the same as being right. Until someone fills in "
               "gold_correction_ok in answers_to_label.csv, report that TrustGuard detects errors, not that it "
               "fixes them.")

# ---------- 5. limitations ----------
section("5 · Where TrustGuard went wrong",
        "Every miss from this run, straight from failures.md. We show these on purpose: they are where the "
        "next improvements come from.")
with st.expander("Failures and limitations for this run", expanded=run.kind != "controlled"):
    if run.failures_md:
        st.markdown(run.failures_md.split("\n", 1)[1] if run.failures_md.startswith("#") else run.failures_md)
    else:
        st.caption("No failures.md in this folder.")
    if m.get("errors"):
        st.warning(f"{m['errors']} question(s) errored during the run and are not counted.")

with st.expander("How this run was set up"):
    st.markdown(f"- **Kind:** {esc(run.kind)}\n"
                f"- **TrustGuard model:** {esc(info.get('trustguard_model') or 'n/a')}\n"
                f"- **Agent 1 model:** {esc(info.get('agent1_model') or 'n/a (fixed answers)')}\n"
                f"- **Evidence search:** {esc(info.get('retriever') or 'n/a')}\n"
                f"- **Entailment model (check C):** {esc(info.get('nli') or 'n/a')}\n"
                f"- **Times each question was asked:** {esc(info.get('runs', 1))}\n"
                f"- **Results folder:** eval/results/{esc(run.folder)}")
    st.caption("Numbers on this page are read from metrics.json, exactly as eval/compute_metrics.py wrote them.")
