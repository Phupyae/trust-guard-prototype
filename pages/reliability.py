"""How reliable is TrustGuard? Shows the numbers eval/compute_metrics.py wrote to metrics.json.

Two readers, layered (top to bottom):
  1. Anyone, including employees: one headline number and four plain-language tiles.
  2. Behind "See full results": by type of mistake, claim checking, corrections, failures.
  3. Inside that, collapsed: confusion matrix, precision / recall / F1, run setup.

No API key or model is needed; the page only reads files in eval/results/. A new scored run
appears in the selector automatically.
"""
import html
import re

import streamlit as st

from modules.eval_results import SCENARIO_NAMES, default_run, list_runs, ratio, seconds
from ui_theme import apply_base_theme, page_nav

st.set_page_config(page_title="How reliable is TrustGuard?", page_icon="🛡️", layout="wide")
apply_base_theme()

st.markdown("""
<style>
.rv-title {font-family:'Manrope', sans-serif; font-size:2rem; font-weight:800; color:var(--ink); letter-spacing:-0.02em;
  margin:0;}
.rv-lede {color:var(--ink-2); font-size:1rem; margin:0.2rem 0 0 0; max-width:70ch;}
.rv-kind {display:inline-flex; gap:0.5rem; align-items:center; background:#fff; border:1px solid var(--line);
  border-radius:999px; padding:0.3rem 0.9rem; font-size:0.85rem; color:var(--ink-2); margin:0.9rem 0 0.4rem;}
.rv-kind b {color:var(--navy);}
.rv-more {color:var(--ink-2); font-size:0.92rem; max-width:80ch; margin:0.4rem 0 0.4rem;}
.st-key-rv_full {background:#fff; border-radius:999px; padding:0.45rem 1rem; display:inline-flex !important; width:auto !important; box-shadow:var(--shadow); margin-bottom:0.8rem;}
.rv-note {color:var(--ink-3); font-size:0.86rem; max-width:80ch; margin:0 0 1rem 0;}
.rv-card {background:#fff; border:1px solid var(--line); border-radius:var(--radius); box-shadow:var(--shadow);
  padding:1.2rem 1.4rem; height:100%;}
.rv-label {color:var(--ink-3); font-size:0.76rem; font-weight:700; text-transform:uppercase; letter-spacing:0.06em;}
.rv-h {font-family:'Manrope', sans-serif; color:var(--ink); font-size:1.1rem; font-weight:700; margin:0 0 0.2rem;}
.rv-sub {color:var(--ink-3); font-size:0.85rem; line-height:1.45; margin:0 0 0.8rem;}

/* Headline, like the template's "Total balance" */
.rv-hero {display:grid; grid-template-columns:1.25fr 1fr; gap:1.5rem; align-items:center;}
.rv-big {font-family:'Manrope', sans-serif; font-size:3.4rem; font-weight:800; color:var(--ink); line-height:1;
  letter-spacing:-0.03em; margin:0.5rem 0 0.4rem;}
.rv-big small {font-size:1.3rem; color:var(--ink-3); font-weight:700; letter-spacing:0;}
.rv-delta {color:var(--ok); font-weight:600; font-size:0.95rem;}
.rv-delta span {color:var(--ink-3); font-weight:500;}
.rv-cmp {display:flex; flex-direction:column; gap:0.8rem;}
.rv-cmp .row {display:grid; grid-template-columns:9.5rem 1fr 3.2rem; gap:0.7rem; align-items:center;
  font-size:0.86rem; color:var(--ink-2);}
.rv-cmp .row b {color:var(--ink); display:block; font-size:0.9rem;}
.rv-cmp .val {text-align:right; font-weight:700; color:var(--ink);}
.rv-track {height:12px; background:var(--desk); border-radius:6px; overflow:hidden;}
.rv-track div {height:100%; border-radius:0 4px 4px 0;}

/* Overview tiles, like the template's "Financial overview" row */
.rv-tiles {display:grid; grid-template-columns:repeat(auto-fit, minmax(190px, 1fr)); gap:0.9rem; margin:1rem 0;}
.rv-tile {background:#fff; border:1px solid var(--line); border-radius:var(--radius); box-shadow:var(--shadow);
  padding:1rem 1.1rem;}
.rv-tile .k {color:var(--ink-3); font-size:0.74rem; font-weight:700; text-transform:uppercase; letter-spacing:0.05em;
  min-height:2.3em;}
.rv-tile .v {font-family:'Manrope', sans-serif; color:var(--ink); font-size:1.9rem; font-weight:800; margin-top:0.3rem;}
.rv-tile .n {color:var(--ink-2); font-size:0.84rem;}
.rv-tile .d {font-size:0.78rem; color:var(--ink-3); margin-top:0.35rem;}

/* Gauge, like the template's credit score (single hue: it's a percentage, not a rating band) */
.rv-gauge {text-align:center;}
.rv-gauge svg {width:100%; max-width:260px;}
.rv-gauge .num {font-family:'Manrope', sans-serif; font-size:2.6rem; font-weight:800; fill:var(--ink);}
.rv-gauge .cap {font-size:0.8rem; fill:var(--ink-3); font-weight:600;}

/* Segmented bars, like the template's "Active plans": one segment per answer */
.rv-seg {margin:0 0 0.85rem;}
.rv-seg .top {display:flex; justify-content:space-between; font-size:0.86rem; color:var(--ink); margin-bottom:0.3rem;}
.rv-seg .top span {color:var(--ink-3);}
.rv-seg .bar {display:flex; gap:3px;}
.rv-seg .bar i {flex:1; height:18px; border-radius:4px; background:var(--desk);}
.rv-seg .bar i.caught {background:var(--navy);} .rv-seg .bar i.missed {background:var(--bad);}
.rv-seg .bar i.alarm {background:#E0A100;} .rv-seg .bar i.clean {background:var(--sky);}
.rv-key {display:flex; flex-wrap:wrap; gap:0.4rem 1rem; font-size:0.78rem; color:var(--ink-2); margin-top:0.4rem;}
.rv-key span {display:inline-flex; align-items:center; gap:0.35rem;}
.rv-key i {width:12px; height:12px; border-radius:3px; display:inline-block;}

/* Activity-style list */
.rv-list {display:flex; flex-direction:column; gap:0.5rem;}
.rv-item {display:grid; grid-template-columns:2.4rem 1fr auto; gap:0.8rem; align-items:center; background:#fff;
  border:1px solid var(--line); border-radius:14px; padding:0.6rem 0.9rem;}
.rv-item .av {width:2.3rem; height:2.3rem; border-radius:50%; background:var(--tint); color:var(--navy);
  display:flex; align-items:center; justify-content:center; font-weight:700;}
.rv-item b {display:block; color:var(--ink); font-size:0.92rem;}
.rv-item small {color:var(--ink-3); font-size:0.8rem;}
.rv-item .amt {font-weight:700; color:var(--ink);}
.rv-item .amt.ok {color:var(--ok);} .rv-item .amt.bad {color:var(--bad);}

/* Detail tables */
.ev-table {border-collapse:collapse; width:100%; background:#fff; font-size:0.9rem; margin:0.3rem 0 0.6rem;
  border-radius:12px; overflow:hidden;}
.ev-table th, .ev-table td {border:1px solid var(--line); padding:0.45rem 0.7rem; text-align:right; color:var(--ink);}
.ev-table th {background:var(--panel); color:var(--navy); font-weight:600;}
.ev-table th:first-child, .ev-table td:first-child {text-align:left;}
.ev-table td.diag {background:var(--ok-bg); font-weight:700;}
.ev-table td.off {background:var(--bad-bg); font-weight:700;}
.ev-table caption {caption-side:top; text-align:left; color:var(--ink-3); font-size:0.82rem; padding-bottom:0.3rem;}
@media (max-width:820px) {.rv-hero {grid-template-columns:1fr;}}
</style>
""", unsafe_allow_html=True)


def esc(text) -> str:
    return html.escape(str(text if text is not None else ""))


def tile(title: str, metric: dict | None, note: str = "") -> str:
    value, n = ratio(metric)
    return plain_tile(title, value, n, note)


def plain_tile(title: str, value: str, n: str = "", note: str = "") -> str:
    return (f'<div class="rv-tile"><div class="k">{esc(title)}</div><div class="v">{esc(value)}</div>'
            f'<div class="n">{esc(n)}</div>{f"<div class=d>{esc(note)}</div>" if note else ""}</div>')


def gauge(metric: dict | None, caption: str) -> str:
    v = (metric or {}).get("value")
    value, n = ratio(metric)
    length = 3.14159 * 90
    filled = 0 if v is None else v * length
    return (f'<div class="rv-gauge"><svg viewBox="0 0 200 120" role="img" aria-label="{esc(caption)}: {value}, {n}">'
            f'<path d="M 10 105 A 90 90 0 0 1 190 105" fill="none" stroke="var(--desk)" stroke-width="14" '
            f'stroke-linecap="round"/>'
            f'<path d="M 10 105 A 90 90 0 0 1 190 105" fill="none" stroke="var(--navy)" stroke-width="14" '
            f'stroke-linecap="round" stroke-dasharray="{filled:.1f} {length:.1f}"><title>{value} ({n})</title></path>'
            f'<text x="100" y="92" text-anchor="middle" class="num">{value}</text>'
            f'<text x="100" y="114" text-anchor="middle" class="cap">{esc(n)}</text></svg></div>')


def segments(name: str, s: dict) -> str:
    """One segment per answer. caught/missed = wrong answers; alarm/clean = correct answers."""
    missed = max(s["agent1_wrong"] - s["wrong_caught"], 0)
    alarms = max(s["flagged"] - s["wrong_caught"], 0)
    clean = max(s["answers"] - s["agent1_wrong"] - alarms, 0)
    parts = (["caught"] * s["wrong_caught"] + ["missed"] * missed + ["alarm"] * alarms + ["clean"] * clean)
    tips = {"caught": "Wrong answer, flagged by TrustGuard", "missed": "Wrong answer, missed by TrustGuard",
            "alarm": "Correct answer, flagged anyway (false alarm)", "clean": "Correct answer, not flagged"}
    bar = "".join(f'<i class="{p}" title="{tips[p]}"></i>' for p in parts)
    summary = (f"{s['wrong_caught']} of {s['agent1_wrong']} wrong caught" if s["agent1_wrong"]
               else f"{alarms} false alarm{'s' if alarms != 1 else ''}")
    return (f'<div class="rv-seg"><div class="top"><b>{esc(name)}</b><span>{summary}</span></div>'
            f'<div class="bar" role="img" aria-label="{esc(name)}: {summary}">{bar}</div></div>')


def failure_sections(md: str) -> list[tuple[str, int]]:
    """failures.md: '## Title' followed by '- item' lines ('- none' means zero)."""
    out = []
    for block in re.split(r"^## ", md, flags=re.M)[1:]:
        title, _, body = block.partition("\n")
        items = [ln for ln in body.splitlines() if ln.startswith("- ") and not ln[2:].startswith("none")]
        out.append((title.strip(), len(items)))
    return out


# ---------- sidebar and data ----------
with st.sidebar:
    page_nav()

runs = list_runs()
st.markdown('<div class="rv-title">How reliable is TrustGuard?</div>'
            '<div class="rv-lede">We tested TrustGuard on policy questions with known correct answers. Here is how '
            'often it caught a wrong answer, and how often it raised a warning it shouldn\'t have.</div>',
            unsafe_allow_html=True)
if not runs:
    st.info("No test results yet. Run `python eval/run_eval.py --controlled` (or `--live`), label the CSVs, "
            "then `python eval/compute_metrics.py eval/results/<folder>`. See eval/README.md.")
    st.stop()

default = default_run(runs)
top = st.columns([3, 2])
with top[1]:
    run = st.selectbox("Test run", runs, index=runs.index(default), format_func=lambda r: r.label,
                       help="Every folder in eval/results/ with a metrics.json. A live run is shown first by "
                            "default, because it is the main evidence.")
m = run.metrics
A, C = m.get("answers", {}), m.get("claims", {})
info = run.run_info
with top[0]:
    if run.kind == "controlled":
        st.markdown(f'<div class="rv-kind"><b>Controlled test</b>· {A.get("answers_total", 0)} answers · '
                    f'{C.get("claims_total", 0)} claims</div>'
                    '<div class="rv-note">The assistant\'s answers in this test were written by the team, each with a '
                    'known mistake (or none). It shows TrustGuard catches the mistakes it was built for. The sample '
                    'is small, so read the percentages with that in mind.</div>', unsafe_allow_html=True)
    else:
        st.markdown(f'<div class="rv-kind"><b>Live test</b>· {A.get("answers_labelled", 0)} answers · '
                    f'{C.get("claims_labelled", 0)} claims labelled</div>'
                    '<div class="rv-note">The assistant answered every question live, with nothing scripted. Only '
                    'answers the team has labelled count towards the numbers.</div>', unsafe_allow_html=True)

# ---------- 1. headline (for everyone) ----------
sa, sb = A.get("system_a_unflagged_wrong") or {}, A.get("system_b_unflagged_wrong") or {}


def cmp_row(title: str, sub: str, metric: dict, colour: str) -> str:
    v = metric.get("value")
    value, _ = ratio(metric)
    return (f'<div class="row"><div><b>{title}</b>{sub}</div><div class="rv-track"><div style="width:'
            f'{0 if v is None else v * 100:.0f}%; background:{colour}"></div></div><div class="val">{value}</div></div>')


headline = (f'{sb.get("num", "–")}<small> of {sb.get("den", "–")} answers</small>' if sb.get("den") else "n/a")
delta = (f'<div class="rv-delta">↓ from {sa["num"]} of {sa["den"]} <span>without TrustGuard</span></div>'
         if sa.get("den") else "")
st.markdown(
    '<div class="rv-card"><div class="rv-hero"><div>'
    '<div class="rv-label">Wrong answers that reached an employee with no warning</div>'
    f'<div class="rv-big">{headline}</div>{delta}</div>'
    '<div class="rv-cmp">'
    + cmp_row("Assistant alone", "no checking", sa, "var(--bad)")
    + cmp_row("With TrustGuard", "every answer checked", sb, "var(--navy)")
    + '</div></div></div>', unsafe_allow_html=True)

ts = A.get("trustguard_seconds", {})
st.markdown('<div class="rv-tiles">'
            + tile("Wrong answers flagged", A.get("wrong_answer_detection_rate"), "Higher is better")
            + tile("Correct answers flagged anyway", A.get("false_alarm_rate"), "False alarms · lower is better")
            + tile("Missing steps caught", A.get("incomplete_answer_recall"), "Higher is better")
            + plain_tile("Time to check an answer", seconds(ts.get("median")),
                         f'median · slowest 5% {seconds(ts.get("p95"))}', "Lower is better")
            + '</div>', unsafe_allow_html=True)

# ---------- layers 2 and 3: for judges and anyone who wants the evidence (hidden until asked for) ----------
LABELS = [("SUPPORTED", "✓ Supported"), ("CONTRADICTED", "✕ Contradicted"),
          ("INSUFFICIENT_EVIDENCE", "? Insufficient evidence")]
st.markdown('<div class="rv-more">The numbers above are the short answer. The full results show how they '
            'break down by type of mistake, how each claim was checked, the suggested corrections, and every case '
            'TrustGuard got wrong.</div>', unsafe_allow_html=True)
if st.toggle("See full results", key="rv_full",
             help="By type of mistake, claim checking, corrections and failures; technical tables at the bottom."):
    # ---------- 2. three panels (for judges) ----------
    c1, c2, c3 = st.columns([1, 1.25, 1])
    with c1:
        st.markdown('<div class="rv-card"><div class="rv-h">Claims checked correctly</div>'
                    '<div class="rv-sub">Each answer is split into single claims; TrustGuard\'s status for each is '
                    'compared with the team\'s label.</div>'
                    + gauge(C.get("accuracy"), "Claims checked correctly")
                    + f'<div class="rv-sub" style="text-align:center;margin-top:0.5rem">Wrong claims marked contradicted: '
                    f'<b>{ratio(C.get("critical_error_recall"))[0]}</b> · citations correct: '
                    f'<b>{ratio(C.get("citation_accuracy_auto"))[0]}</b></div></div>', unsafe_allow_html=True)
    with c2:
        bars = "".join(segments(SCENARIO_NAMES.get(k, k), s) for k, s in A.get("by_scenario", {}).items())
        st.markdown('<div class="rv-card"><div class="rv-h">By type of mistake</div>'
                    '<div class="rv-sub">One block per answer. Hover a block for what happened.</div>' + bars
                    + '<div class="rv-key"><span><i style="background:var(--navy)"></i>Wrong, caught</span>'
                    '<span><i style="background:var(--bad)"></i>Wrong, missed</span>'
                    '<span><i style="background:var(--sky)"></i>Correct, not flagged</span>'
                    '<span><i style="background:#E0A100"></i>Correct, false alarm</span></div></div>',
                    unsafe_allow_html=True)
    with c3:
        judged = A.get("correction_accuracy") or {}
        st.markdown('<div class="rv-card"><div class="rv-h">Suggested corrections</div>'
                    '<div class="rv-sub">For a wrong answer, TrustGuard writes a corrected one and re-checks it three '
                    'independent ways.</div><div class="rv-list">'
                    f'<div class="rv-item"><div class="av">S</div><div><b>Suggested</b><small>corrections written</small>'
                    f'</div><div class="amt">{A.get("corrections_suggested", 0)}</div></div>'
                    f'<div class="rv-item"><div class="av">R</div><div><b>Passed re-checks</b><small>citation · rules · '
                    f'entailment</small></div><div class="amt">{ratio(A.get("correction_support_rate"))[0]}</div></div>'
                    f'<div class="rv-item"><div class="av">P</div><div><b>Judged correct by a person</b><small>'
                    f'{"" if judged.get("den") else "not labelled yet"}</small></div>'
                    f'<div class="amt">{ratio(judged)[0]}</div></div></div></div>', unsafe_allow_html=True)
        if not judged.get("den"):
            st.caption("Passing the automatic re-checks isn't the same as being right: until a person judges the "
                       "corrections, we claim that TrustGuard detects mistakes, not that it fixes them.")

    # ---------- 3. where it went wrong ----------
    st.markdown('<div class="rv-h" style="margin-top:1.4rem">Where TrustGuard went wrong</div>'
                '<div class="rv-sub">Every miss from this run. We show these on purpose: they are where the next '
                'improvements come from.</div>', unsafe_allow_html=True)
    sections = failure_sections(run.failures_md)
    if sections:
        st.markdown('<div class="rv-list">' + "".join(
            f'<div class="rv-item"><div class="av">{i}</div><div><b>{esc(t)}</b><small>'
            f'{"none in this run" if not n else "see the details below"}</small></div>'
            f'<div class="amt {"ok" if not n else "bad"}">{n}</div></div>' for i, (t, n) in enumerate(sections, 1))
            + '</div>', unsafe_allow_html=True)
    if m.get("errors"):
        st.warning(f"{m['errors']} question(s) errored during the run and are not counted.")

    # ---------- 4. technical detail (collapsed) ----------
    st.markdown('<div class="rv-h" style="margin-top:1.4rem">Full details</div>', unsafe_allow_html=True)
    with st.expander("Failures, item by item"):
        md = run.failures_md
        st.markdown(md.split("\n", 1)[1] if md.startswith("#") else (md or "No failures.md in this folder."))

    with st.expander("Results by type of mistake (table)"):
        rows = "".join(f'<tr><td>{esc(SCENARIO_NAMES.get(k, k))}</td><td>{s["answers"]}</td><td>{s["agent1_wrong"]}</td>'
                       f'<td>{s["wrong_caught"]} of {s["agent1_wrong"]}</td><td>{s["flagged"]}</td></tr>'
                       for k, s in A.get("by_scenario", {}).items())
        st.markdown('<table class="ev-table"><thead><tr><th>Type of question</th><th>Answers</th>'
                    '<th>Assistant wrong</th><th>Wrong answers caught</th><th>Flagged by TrustGuard</th></tr></thead>'
                    f'<tbody>{rows}</tbody></table>', unsafe_allow_html=True)

    with st.expander("Claim checking: confusion matrix, precision, recall, F1"):
        conf = C.get("confusion", {})
        if conf:
            head = "".join(f"<th>TrustGuard said: {lab}</th>" for _, lab in LABELS)
            body = ""
            for gold, glab in LABELS:
                cells = ""
                for pred, _ in LABELS:
                    n = conf.get(gold, {}).get(pred, 0)
                    cells += f'<td class="{"diag" if gold == pred and n else ("off" if n else "")}">{n}</td>'
                body += f"<tr><td>Correct label: {glab}</td>{cells}</tr>"
            st.markdown('<table class="ev-table"><caption>Rows are the correct label; columns are what TrustGuard said. '
                        'Green cells are agreements; a number in a red cell is a mistake.</caption>'
                        f'<thead><tr><th></th>{head}</tr></thead><tbody>{body}</tbody></table>', unsafe_allow_html=True)
        rows = ""
        for key, lab in LABELS:
            pc = C.get("per_class", {}).get(key)
            if pc:
                rows += (f'<tr><td>{lab}</td><td>{pc["precision"]}</td><td>{pc["recall"]}</td><td>{pc["f1"]}</td>'
                         f'<td>{pc["support"]}</td></tr>')
        st.markdown('<table class="ev-table"><thead><tr><th>Status</th><th>Precision</th><th>Recall</th><th>F1</th>'
                    f'<th>Claims</th></tr></thead><tbody>{rows}</tbody></table>', unsafe_allow_html=True)
        st.caption(f"Macro F1: {C.get('macro_f1', 'n/a')} · correct claims flagged anyway: "
                   f"{ratio(C.get('false_positive_rate'))[0]}. Precision: of the claims TrustGuard gave this status, "
                   "how many really had it. Recall: of the claims that really had it, how many TrustGuard found.")

    with st.expander("How this test was set up"):
        st.markdown(f"- **Kind:** {esc(run.kind)}\n"
                    f"- **TrustGuard model:** {esc(info.get('trustguard_model') or 'n/a')}\n"
                    f"- **Assistant (Agent 1) model:** {esc(info.get('agent1_model') or 'n/a (fixed answers)')}\n"
                    f"- **Evidence search:** {esc(info.get('retriever') or 'n/a')}\n"
                    f"- **Entailment model (check C):** {esc(info.get('nli') or 'n/a')}\n"
                    f"- **Times each question was asked:** {esc(info.get('runs', 1))}\n"
                    f"- **Results folder:** eval/results/{esc(run.folder)}")
        st.caption("Every number on this page is read from metrics.json, exactly as eval/compute_metrics.py wrote it.")
