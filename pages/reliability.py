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
from ui_theme import MESH, apply_base_theme, page_nav

st.set_page_config(page_title="How reliable is TrustGuard?", page_icon="🛡️", layout="wide", initial_sidebar_state="expanded")
apply_base_theme()

st.markdown("""
<style>
/* Same navy/white look as the assistant page; every colour comes from ui_theme variables, so dark mode works too */
.rv-hero-top h1 {font-size:2.7rem; font-weight:600; letter-spacing:-0.03em; margin:0.4rem 0 0.6rem; color:var(--ink);}
.rv-kind b {color:var(--link-on);}
.rv-note {color:var(--ink-3); font-size:0.86rem; max-width:80ch; margin:0.2rem 0 1rem 0;}
.rv-more {color:var(--ink-2); font-size:0.92rem; max-width:80ch; margin:1.2rem 0 0.4rem;}
.st-key-rv_full {background:var(--surface); border-radius:999px; padding:0.45rem 1rem; display:inline-flex !important;
  width:auto !important; box-shadow:var(--raise-sm); margin-bottom:0.8rem;}
.rv-card {padding:1.4rem 1.6rem; height:100%; animation:tg-rise .55s cubic-bezier(.2,.7,.2,1) both;}
.rv-label {font-family:var(--mono); color:var(--ink-3); font-size:0.7rem; text-transform:uppercase; letter-spacing:0.08em;}
.rv-h {color:var(--ink); font-size:1.1rem; font-weight:600; margin:0 0 0.2rem;}
.rv-sub {color:var(--ink-3); font-size:0.85rem; line-height:1.45; margin:0 0 0.8rem;}

/* Count-up numbers (Chrome/Edge animate; other browsers show the final number) */
@property --rv-n {syntax:'<integer>'; inherits:false; initial-value:0;}
.rv-count {--rv-n:var(--to); counter-reset:rvn var(--rv-n); animation:rv-count 1.6s cubic-bezier(.2,.7,.2,1) .3s both;}
.rv-count::before {content:counter(rvn);}
@keyframes rv-count {from {--rv-n:var(--from);} to {--rv-n:var(--to);}}

/* Headline: 12 answers as 12 dots, before and after TrustGuard */
.rv-hero {display:grid; grid-template-columns:1fr 1.35fr; gap:2rem; align-items:center;}
.rv-big {font-size:4.2rem; font-weight:600; color:var(--ink); line-height:1; letter-spacing:-0.04em; margin:0.6rem 0 0.4rem;}
.rv-big small {font-size:1.25rem; color:var(--ink-3); font-weight:500; letter-spacing:0;}
.rv-delta {display:inline-flex; gap:0.4rem; align-items:center; background:var(--ok-bg); color:var(--ok); font-weight:600;
  font-size:0.86rem; border-radius:999px; padding:0.25rem 0.75rem;}
.rv-delta span {font-weight:500; opacity:.85;}
.rv-rows {display:flex; flex-direction:column; gap:1.1rem;}
.rv-rowh {display:flex; justify-content:space-between; align-items:baseline; font-size:0.88rem; color:var(--ink-2); margin-bottom:0.45rem;}
.rv-rowh b {color:var(--ink); font-weight:600;} .rv-rowh .v {font-family:var(--mono); font-size:0.8rem;}
.rv-dots {display:grid; grid-template-columns:repeat(var(--n), 1fr); gap:6px;}
.rv-dots i {position:relative; aspect-ratio:1; border-radius:50%; background:var(--inset); box-shadow:var(--sink);
  animation:rv-pop .4s cubic-bezier(.3,1.6,.5,1) both; animation-delay:calc(.25s + var(--k) * .05s); cursor:default;
  display:flex; align-items:center; justify-content:center; font-size:0.62rem; color:#fff; font-weight:700;}
.rv-dots i.bad {background:var(--bad); box-shadow:0 3px 8px rgba(194,57,46,.3);}
.rv-dots i.caught {background:var(--cobalt); box-shadow:0 3px 8px rgba(28,61,130,.3);}
.rv-dots i.ok {background:var(--blue-soft); box-shadow:var(--sink);}
.rv-dots i:hover {transform:scale(1.25); z-index:3; transition:transform .15s;}
.rv-dots i .t {position:absolute; bottom:calc(100% + 8px); left:50%; transform:translateX(-50%); white-space:nowrap;
  background:var(--tip); color:#fff; font-weight:500; font-size:0.72rem; padding:0.3rem 0.55rem; border-radius:8px;
  opacity:0; pointer-events:none; transition:opacity .15s;}
.rv-dots i:hover .t {opacity:1;}
@keyframes rv-pop {from {transform:scale(0); opacity:0;}}
.rv-key {display:flex; flex-wrap:wrap; gap:0.4rem 1rem; font-size:0.78rem; color:var(--ink-2); margin-top:0.9rem;}
.rv-key span {display:inline-flex; align-items:center; gap:0.35rem;}
.rv-key i {width:11px; height:11px; border-radius:50%; display:inline-block;}

/* Four tiles, each with a small ring that fills on load */
.rv-tiles {display:grid; grid-template-columns:repeat(auto-fit, minmax(200px, 1fr)); gap:1rem; margin:1.1rem 0;}
.rv-tile {padding:1.1rem 1.2rem; display:grid; grid-template-columns:1fr auto; gap:0.2rem 0.8rem; align-items:center;
  transition:transform .2s, box-shadow .2s; animation:tg-rise .55s cubic-bezier(.2,.7,.2,1) both;}
.rv-tile:nth-child(2) {animation-delay:.08s;} .rv-tile:nth-child(3) {animation-delay:.16s;} .rv-tile:nth-child(4) {animation-delay:.24s;}
.rv-tile:hover {transform:translateY(-3px); box-shadow:var(--raise-lg) !important;}
.rv-tile .k {grid-column:1 / -1; font-family:var(--mono); color:var(--ink-3); font-size:0.68rem; text-transform:uppercase;
  letter-spacing:0.07em; min-height:2.4em;}
.rv-tile .v {color:var(--ink); font-size:2rem; font-weight:600; letter-spacing:-0.02em;}
.rv-tile .n {grid-column:1; color:var(--ink-2); font-size:0.82rem;}
.rv-tile .d {grid-column:1 / -1; margin-top:0.5rem; font-size:0.72rem; color:var(--ink-3); display:flex; align-items:center; gap:0.35rem;}
.rv-tile .d b {font-weight:600; border-radius:999px; padding:0.1rem 0.5rem; background:var(--inset); color:var(--ink-2);}
.rv-tile .d b.good {background:var(--ok-bg); color:var(--ok);}
.rv-mini {grid-row:2 / span 2; grid-column:2; width:54px; height:54px;}
.rv-mini circle {fill:none; stroke-width:7;}
.rv-mini .bg {stroke:var(--inset);}
.rv-mini .fg {stroke:var(--cobalt); stroke-linecap:round; transform:rotate(-90deg); transform-origin:50% 50%;
  stroke-dasharray:var(--c) var(--c); animation:rv-ring 1.4s cubic-bezier(.2,.7,.2,1) .35s both;}
.rv-mini .fg.low {stroke:var(--ok);}
@keyframes rv-ring {from {stroke-dashoffset:var(--c);}}
.rv-time {grid-column:1 / -1; position:relative; height:8px; border-radius:6px; background:var(--inset); margin-top:0.5rem;}
.rv-time i {position:absolute; top:0; bottom:0; left:0; border-radius:6px; background:var(--cobalt); animation:rv-grow 1.2s ease-out .4s both;}
.rv-time i.p95 {background:var(--powder); z-index:0;} .rv-time i.med {z-index:1;}
@keyframes rv-grow {from {width:0;}}

/* Gauge: draws itself */
.rv-gauge {text-align:center;}
.rv-gauge svg {width:100%; max-width:260px;}
.rv-gauge .num {font-size:2.6rem; font-weight:600; fill:var(--ink);}
.rv-gauge .cap {font-size:0.8rem; fill:var(--ink-3); font-weight:500;}
.rv-gauge .arc {animation:rv-arc 1.4s cubic-bezier(.2,.7,.2,1) .2s both;}
@keyframes rv-arc {from {stroke-dasharray:0 283;}}

/* Segmented bars: one block per answer, hover for what happened */
.rv-seg {margin:0 0 0.9rem;}
.rv-seg .top {display:flex; justify-content:space-between; font-size:0.86rem; color:var(--ink); margin-bottom:0.35rem;}
.rv-seg .top span {color:var(--ink-3);}
.rv-seg .bar {display:flex; gap:4px;}
.rv-seg .bar i {position:relative; flex:1; height:20px; border-radius:6px; background:var(--inset);
  animation:rv-pop .35s cubic-bezier(.3,1.6,.5,1) both; animation-delay:calc(var(--k) * .06s);}
.rv-seg .bar i:hover {transform:translateY(-2px); filter:brightness(1.1); transition:transform .15s;}
.rv-seg .bar i.caught {background:var(--cobalt);} .rv-seg .bar i.missed {background:var(--bad);}
.rv-seg .bar i.alarm {background:var(--unk);} .rv-seg .bar i.clean {background:var(--blue-soft); box-shadow:var(--sink);}
.rv-seg .bar i .t {position:absolute; bottom:calc(100% + 7px); left:50%; transform:translateX(-50%); white-space:nowrap;
  background:var(--tip); color:#fff; font-size:0.72rem; padding:0.3rem 0.55rem; border-radius:8px; opacity:0;
  pointer-events:none; transition:opacity .15s; z-index:5;}
.rv-seg .bar i:hover .t {opacity:1;}

/* Activity-style list */
.rv-list {display:flex; flex-direction:column; gap:0.5rem;}
.rv-item {display:grid; grid-template-columns:2.4rem 1fr auto; gap:0.8rem; align-items:center; background:var(--field);
  box-shadow:var(--sink); border-radius:16px; padding:0.6rem 0.9rem; transition:transform .15s;}
.rv-item:hover {transform:translateX(3px);}
.rv-item .av {width:2.3rem; height:2.3rem; border-radius:50%; background:var(--blue-soft); color:var(--link-on);
  display:flex; align-items:center; justify-content:center; font-weight:600;}
.rv-item b {display:block; color:var(--ink); font-size:0.92rem; font-weight:600;}
.rv-item small {color:var(--ink-3); font-size:0.8rem;}
.rv-item .amt {font-weight:600; color:var(--ink);}
.rv-item .amt.ok {color:var(--ok);} .rv-item .amt.bad {color:var(--bad);}

/* Detail tables */
.ev-table {border-collapse:collapse; width:100%; background:var(--surface); font-size:0.9rem; margin:0.3rem 0 0.6rem;
  border-radius:12px; overflow:hidden;}
.ev-table th, .ev-table td {border:1px solid var(--line); padding:0.45rem 0.7rem; text-align:right; color:var(--ink);}
.ev-table th {background:var(--field); color:var(--link-on); font-weight:600;}
.ev-table th:first-child, .ev-table td:first-child {text-align:left;}
.ev-table td.diag {background:var(--ok-bg); font-weight:700;}
.ev-table td.off {background:var(--bad-bg); font-weight:700;}
.ev-table caption {caption-side:top; text-align:left; color:var(--ink-3); font-size:0.82rem; padding-bottom:0.3rem;}
@media (max-width:820px) {.rv-hero {grid-template-columns:1fr;} .rv-hero-top h1 {font-size:2rem;}}
@media (prefers-reduced-motion:reduce) {.rv-count, .rv-dots i, .rv-mini .fg, .rv-time i, .rv-gauge .arc, .rv-seg .bar i,
  .rv-tile, .rv-card {animation:none !important;}}
</style>
""", unsafe_allow_html=True)


def esc(text) -> str:
    return html.escape(str(text if text is not None else ""))


def mini_ring(v: float | None, low_is_good: bool = False) -> str:
    """Small ring that fills to the metric. For 'lower is better' metrics the ring shows the good share
    (1 - value) in green, so a full ring always means good."""
    c = 2 * 3.14159 * 22
    share = 0 if v is None else (1 - v if low_is_good else v)
    return (f'<svg class="rv-mini" viewBox="0 0 54 54" aria-hidden="true" style="--c:{c:.1f}">'
            f'<circle class="bg" cx="27" cy="27" r="22"/><circle class="fg{" low" if low_is_good else ""}" cx="27" cy="27" '
            f'r="22" style="stroke-dashoffset:{c * (1 - share):.1f}"/></svg>')


def tile(title: str, metric: dict | None, note: str = "", low_is_good: bool = False) -> str:
    value, n = ratio(metric)
    v = (metric or {}).get("value")
    good = v is not None and ((v == 0) if low_is_good else (v == 1))
    return plain_tile(title, value, n, note, mini_ring(v, low_is_good), good)


def plain_tile(title: str, value: str, n: str = "", note: str = "", extra: str = "", good: bool = False) -> str:
    d = f'<div class="d"><b class="{"good" if good else ""}">{esc(note)}</b></div>' if note else ""
    return (f'<div class="rv-tile rv-card"><div class="k">{esc(title)}</div><div class="v">{esc(value)}</div>{extra}'
            f'<div class="n">{esc(n)}</div>{d}</div>')


def gauge(metric: dict | None, caption: str) -> str:
    v = (metric or {}).get("value")
    value, n = ratio(metric)
    length = 3.14159 * 90
    filled = 0 if v is None else v * length
    return (f'<div class="rv-gauge"><svg viewBox="0 0 200 120" role="img" aria-label="{esc(caption)}: {value}, {n}">'
            f'<path d="M 10 105 A 90 90 0 0 1 190 105" fill="none" stroke="var(--desk)" stroke-width="14" '
            f'stroke-linecap="round"/>'
            f'<path d="M 10 105 A 90 90 0 0 1 190 105" fill="none" stroke="var(--navy)" stroke-width="14" '
            f'stroke-linecap="round" class="arc" stroke-dasharray="{filled:.1f} {length:.1f}"><title>{value} ({n})</title></path>'
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
    bar = "".join(f'<i class="{p}" style="--k:{k}"><span class="t">{tips[p]}</span></i>' for k, p in enumerate(parts))
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
st.markdown('<div class="tg-hero-wrap tg-rise">' + MESH + '<div class="tg-top rv-hero-top">'
            '<div class="tg-eyebrow">Evidence · tested on questions with known answers</div>'
            '<h1>How <span class="tg-grad">reliable</span> is TrustGuard?</h1>'
            '<p>We asked policy questions where we already knew the right answer, then counted how often TrustGuard '
            'caught a wrong answer, and how often it warned about one that was fine.</p></div></div>',
            unsafe_allow_html=True)
if not runs:
    st.info("No test results yet. Run `python eval/run_eval.py --controlled` (or `--live`), label the CSVs, "
            "then `python eval/compute_metrics.py eval/results/<folder>`. See eval/README.md.")
    st.stop()

default = default_run(runs)
top = st.columns([3, 2], vertical_alignment="bottom")
with top[1]:
    run = st.selectbox("Test run", runs, index=runs.index(default), format_func=lambda r: r.label,
                       help="Every folder in eval/results/ with a metrics.json. A live run is shown first by "
                            "default, because it is the main evidence.")
m = run.metrics
A, C = m.get("answers", {}), m.get("claims", {})
info = run.run_info
with top[0]:
    if run.kind == "controlled":
        st.markdown(f'<div class="tg-chips" style="justify-content:flex-start;margin:0"><span class="rv-kind"><b>Controlled test</b></span>'
                    f'<span>{A.get("answers_total", 0)} answers</span><span>{C.get("claims_total", 0)} claims</span></div>'
                    '<div class="rv-note">The team wrote the assistant\'s answers for this test, each with a known '
                    'mistake (or none), to show TrustGuard catches the mistakes it was built for. The sample is small, '
                    'so read the percentages with that in mind.</div>', unsafe_allow_html=True)
    else:
        st.markdown(f'<div class="tg-chips" style="justify-content:flex-start;margin:0"><span class="rv-kind"><b>Live test</b></span>'
                    f'<span>{A.get("answers_labelled", 0)} answers</span><span>{C.get("claims_labelled", 0)} claims labelled</span></div>'
                    '<div class="rv-note">The assistant answered every question live, with nothing scripted. Only '
                    'answers the team has labelled count towards the numbers.</div>', unsafe_allow_html=True)

# ---------- 1. headline (for everyone) ----------
sa, sb = A.get("system_a_unflagged_wrong") or {}, A.get("system_b_unflagged_wrong") or {}
wrong_total = A.get("wrong_answer_detection_rate", {}) or {}


def dots(kind: str, total: int, wrong: int, caught: int) -> str:
    """One dot per answer. 'before': wrong answers in red. 'after': the caught ones in navy with a tick."""
    out = []
    for k in range(total):
        if k < wrong:
            if kind == "before":
                cls, tip, mark = "bad", "Wrong answer, reached the employee with no warning", ""
            elif k < caught:
                cls, tip, mark = "caught", "Wrong answer, flagged by TrustGuard", "✓"
            else:
                cls, tip, mark = "bad", "Wrong answer, missed by TrustGuard", ""
        else:
            cls, tip, mark = "ok", "Correct answer", ""
        out.append(f'<i class="{cls}" style="--k:{k + (total if kind == "after" else 0)}">{mark}<span class="t">{tip}</span></i>')
    return f'<div class="rv-dots" style="--n:{total}">{"".join(out)}</div>'


if sb.get("den"):
    total, wrong_n = sb["den"], sa.get("num", 0)
    caught_n = wrong_n - sb.get("num", 0)
    big = (f'<span class="rv-count" style="--from:{sa.get("num", 0)};--to:{sb["num"]}" '
           f'aria-label="{sb["num"]}"></span><small> of {total} answers</small>')
    delta = (f'<div class="rv-delta">↓ from {sa["num"]} of {sa["den"]} <span>without TrustGuard</span></div>'
             if sa.get("den") else "")
    st.markdown(
        '<div class="rv-card"><div class="rv-hero"><div>'
        '<div class="rv-label">Wrong answers that reached an employee with no warning</div>'
        f'<div class="rv-big">{big}</div>{delta}</div>'
        '<div><div class="rv-rows">'
        f'<div><div class="rv-rowh"><b>Assistant alone</b><span class="v">{ratio(sa)[0]} unflagged</span></div>'
        + dots("before", total, wrong_n, 0) + '</div>'
        f'<div><div class="rv-rowh"><b>With TrustGuard</b><span class="v">{ratio(sb)[0]} unflagged</span></div>'
        + dots("after", total, wrong_n, caught_n) + '</div></div>'
        '<div class="rv-key"><span><i style="background:var(--bad)"></i>Wrong, no warning</span>'
        '<span><i style="background:var(--cobalt)"></i>Wrong, flagged</span>'
        '<span><i style="background:var(--blue-soft);box-shadow:var(--sink)"></i>Correct answer</span>'
        '<span style="color:var(--ink-3)">Hover a dot</span></div></div></div></div>', unsafe_allow_html=True)

ts = A.get("trustguard_seconds", {})
scale = max(ts.get("p95") or 0, 1) * 1.15
time_bar = ('<div class="rv-time">'
            f'<i class="p95" style="width:{(ts.get("p95") or 0) / scale * 100:.0f}%"></i>'
            f'<i class="med" style="width:{(ts.get("median") or 0) / scale * 100:.0f}%"></i></div>')
st.markdown('<div class="rv-tiles">'
            + tile("Wrong answers flagged", A.get("wrong_answer_detection_rate"), "Higher is better")
            + tile("Correct answers flagged anyway", A.get("false_alarm_rate"), "Lower is better", low_is_good=True)
            + tile("Missing steps caught", A.get("incomplete_answer_recall"), "Higher is better")
            + plain_tile("Time to check an answer", seconds(ts.get("median")),
                         f'median · slowest 5% {seconds(ts.get("p95"))}', "", time_bar)
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
                    + '<div class="rv-key"><span><i style="background:var(--cobalt)"></i>Wrong, caught</span>'
                    '<span><i style="background:var(--bad)"></i>Wrong, missed</span>'
                    '<span><i style="background:var(--blue-soft);box-shadow:var(--sink)"></i>Correct, not flagged</span>'
                    '<span><i style="background:var(--unk)"></i>Correct, false alarm</span></div></div>',
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
        if not md:
            st.caption("No failures.md in this folder.")
        # failures.md uses big "##" headings; show each as a small title so it fits the page
        for block in re.split(r"^## ", md, flags=re.M)[1:]:
            title, _, body = block.partition("\n")
            st.markdown(f'<div class="rv-fail-h">{esc(title.strip())}</div>', unsafe_allow_html=True)
            st.markdown(body.strip() or "- none")

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
