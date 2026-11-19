"""Shared look for every page of the TrustGuard app (assistant chat and reliability results).

Colours, fonts and the status marks live here once, so a UI/UX change made in this file shows up
on every page. Page-specific styles stay in the page itself.

Visual direction (19 Nov 2026): the "clay" look of the Clico reference the team picked.
  - One soft cloud-grey surface; cards are raised (light top-left, soft shadow bottom-right) and
    wells are pressed in, so depth replaces borders. Cobalt for actions and the selected tab,
    powder blue for the top bar's main button. DM Sans for text, DM Mono for small labels.
  - Visual, not just text: a step tracker, a score ring, number highlights and an SOP timeline.
  - Type and the sliding pill tabs from the team's portfolio reference: Outfit for text, Instrument
    Serif for the one page title, JetBrains Mono for small labels, citations and timings.
  - Calm by default: colour only on the small status mark and its word, never as a big background.
    One result line, the answer to use, then details behind tabs.
The status colours (green ✓ / red ✕ / amber ?) are NOT decoration: they carry meaning, always with an
icon and a word, so they stay the same on every page whatever the brand colours are.
"""
import streamlit as st
from streamlit.errors import StreamlitAPIException

THEME_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:opsz,wght@9..40,400..700&family=DM+Mono:wght@400;500&display=swap');
:root {
  /* Navy and white (the team's choice). Variable names are shared with the components below. */
  --cloud:#F2F5FA; --surface:#FFFFFF; --inset:#EEF2F8; --field:#F7F9FC; --paper:#FFFFFF;
  --ink:#0E1A33; --ink-2:#44516A; --ink-3:#6B778C; --line:#E1E7F0; --rule:#E8EDF4;
  --cobalt:#1C3D82; --cobalt-deep:#0E2558; --bright:#2F6BE0; --powder:#CFE0F5; --blue-soft:#E6EEFA; --peach:#F2994A; --blush:#F6DEDB;
  /* Soft, flat depth: thin outline plus a gentle shadow */
  --raise-sm:0 0 0 1px #E1E7F0, 0 4px 12px rgba(14,37,88,.05);
  --raise-md:0 0 0 1px #E6EBF2, 0 12px 32px rgba(14,37,88,.07);
  --raise-lg:0 0 0 1px #E6EBF2, 0 18px 44px rgba(14,37,88,.10);
  --sink:inset 0 0 0 1px #E1E7F0;
  --sink-deep:inset 0 1px 3px rgba(14,37,88,.10), inset 0 0 0 1px #E1E7F0;
  --accent:0 6px 18px rgba(14,37,88,.28);
  --accent-press:inset 0 2px 5px rgba(0,0,0,.28);
  --field-shadow:0 0 0 1px #E1E7F0, 0 4px 14px rgba(14,37,88,.05);
  --sans:'DM Sans', 'Helvetica Neue', system-ui, sans-serif; --mono:'DM Mono', ui-monospace, Menlo, monospace;
  /* Names the pages already use, mapped onto the clay palette */
  --page:var(--cloud); --card:var(--cloud); --panel:var(--field); --desk:var(--inset);
  --navy:var(--cobalt-deep); --navy-2:var(--cobalt); --accent-c:var(--cobalt); --accent-dark:var(--cobalt-deep);
  --sky:var(--blue-soft); --tint:var(--blue-soft); --brand:var(--cobalt); --brand-soft:var(--blue-soft);
  --radius:28px; --shadow:var(--raise-md);
  /* Status: meaning, not decoration */
  --ok:#147A4B; --ok-bg:#DDF0E6; --bad:#C2392E; --bad-bg:#F6DEDB; --unk:#9A6400; --unk-bg:#F7E9CC;
  --rev:#4A5666; --rev-bg:var(--inset); --neutral:#687587; --neutral-bg:var(--inset);
  --tip:#0E1A33; --hero:radial-gradient(120% 140% at 50% 0%, #FFFFFF 0%, #EEF3FB 55%, #E3EBF7 100%);
  --glass:rgba(255,255,255,.8); --link-on:var(--cobalt-deep); --grad-a:var(--cobalt-deep); --grad-b:var(--bright);
}
html, body, .stApp, .stMarkdown, input, textarea, button, label, [data-testid="stSidebar"],
h1, h2, h3, h4, .rv-title, .rv-big, .rv-tile .v, .rv-h, .rv-gauge .num {font-family:var(--sans) !important;}
.stApp {background:var(--cloud); color:var(--ink);}
.block-container {padding-top:2.2rem; max-width:1000px;}
[data-testid="stHeader"] {background:transparent;}
[data-testid="stToolbar"] {right:1rem;}
a, a:visited {color:var(--cobalt);}
*:focus-visible {outline:3px solid rgba(102,115,134,.6) !important; outline-offset:2px;}
h1, h2, h3 {color:var(--ink);}

/* ---------- floating pill navigation (like the reference's top bar) ---------- */
.st-key-tg_nav {background:var(--cloud); border-radius:999px; padding:0.45rem 0.6rem 0.45rem 0.5rem !important;
  box-shadow:var(--raise-md); border:1px solid rgba(255,255,255,.7); margin:0 0 2.2rem 0; gap:0.4rem !important;
  flex-wrap:nowrap !important;}
.tg-logo {display:flex; align-items:center; gap:0.6rem; margin-right:0.6rem; white-space:nowrap;}
.tg-logo span {display:inline-flex; width:2.6rem; height:2.6rem; border-radius:50%; align-items:center; justify-content:center;
  background:radial-gradient(circle at 30% 28%, #4F86E8 0%, var(--cobalt) 45%, var(--cobalt-deep) 100%); color:#fff;
  box-shadow:var(--raise-sm);}
.tg-logo b {font-weight:600; font-size:1.05rem; letter-spacing:-0.01em; color:var(--ink);}
.st-key-tg_nav [data-testid="stPageLink"] a {font-family:var(--mono) !important; text-transform:uppercase; letter-spacing:0.06em;
  border-radius:999px; padding:0.45rem 0.85rem; background:transparent; transition:box-shadow .25s, background .25s;}
.st-key-tg_nav [data-testid="stPageLink"] a span, .st-key-tg_nav [data-testid="stPageLink"] a p {font-family:var(--mono) !important;
  font-size:0.8rem !important; color:var(--ink-3) !important;}
.st-key-tg_nav [data-testid="stPageLink"] a:hover {box-shadow:var(--sink);}
.st-key-tg_nav [data-testid="stPageLink"] a[aria-current="page"] {box-shadow:var(--sink); background:var(--inset);}
.st-key-tg_nav [data-testid="stPageLink"] a[aria-current="page"] span,
.st-key-tg_nav [data-testid="stPageLink"] a[aria-current="page"] p {color:var(--ink) !important; font-weight:500;}
.st-key-tg_nav .stButton button, .st-key-tg_nav .stButton button[kind="secondary"] {background:var(--powder) !important; color:#12223B !important; border:none !important;
  box-shadow:var(--raise-sm); padding:0.5rem 1.2rem; font-weight:600;}
.st-key-tg_nav .stButton button:hover {background:#8CA6CB !important;}
.st-key-tg_nav [data-testid="stCheckbox"] label p, .st-key-tg_nav [data-testid="stWidgetLabel"] p {font-family:var(--mono) !important;
  font-size:0.8rem; text-transform:uppercase; letter-spacing:0.06em; color:var(--ink-3);}

/* ---------- page header ---------- */
.tg-top {text-align:center; margin:0.5rem auto 1.8rem auto; max-width:720px;}
.tg-eyebrow, .tg-lbl, .tg-mono {font-family:var(--mono) !important; font-size:0.72rem; letter-spacing:0.08em;
  text-transform:uppercase; color:var(--ink-3);}
.tg-top h1 {font-family:var(--sans) !important; font-weight:500; font-size:3rem; line-height:1.05; letter-spacing:-0.035em;
  margin:0.5rem 0 0.7rem 0; padding:0; color:var(--ink);}
.tg-top h1 em {font-family:Georgia, 'Times New Roman', serif; font-style:italic; font-weight:400; color:var(--cobalt);}
.tg-top p {color:var(--ink-2); font-size:1.05rem; margin:0 auto; max-width:56ch;}
.tg-top .tg-note {color:var(--ink-3); font-size:0.82rem; margin-top:0.6rem;}

/* ---------- sidebar (settings, collapsed by default) ---------- */
[data-testid="stSidebar"] {background:var(--surface); border-right:1px solid var(--line);}
.tg-brand {display:flex; align-items:center; gap:0.6rem; margin:0.2rem 0 1.2rem 0.3rem; font-weight:600; font-size:1.15rem; color:var(--ink);}
.tg-brand span {display:inline-flex; width:2.2rem; height:2.2rem; border-radius:12px; align-items:center; justify-content:center;
  background:linear-gradient(140deg, var(--bright), var(--cobalt-deep)); color:#fff; box-shadow:0 6px 16px rgba(14,37,88,.25);}
[data-testid="stSidebar"] [data-testid="stPageLink"] a {border-radius:12px; padding:0.5rem 0.75rem; transition:background .2s;}
[data-testid="stSidebar"] [data-testid="stPageLink"] a:hover {background:var(--inset);}
[data-testid="stSidebar"] [data-testid="stPageLink"] a[aria-current="page"] {background:var(--blue-soft);}
[data-testid="stSidebar"] [data-testid="stPageLink"] a[aria-current="page"] span,
[data-testid="stSidebar"] [data-testid="stPageLink"] a[aria-current="page"] p {color:var(--link-on) !important; font-weight:600;}
[data-testid="stSidebar"] .stButton button {width:100%;}
[data-testid="stSidebar"] h3 {font-family:var(--mono) !important; color:var(--ink-3); font-size:0.72rem !important; font-weight:500;
  text-transform:uppercase; letter-spacing:0.08em; margin-top:1rem;}
[data-testid="stSidebar"] [data-testid="stExpander"] details {background:var(--field); box-shadow:var(--sink); border:none !important;}
.tg-kb {font-size:0.86rem; margin-bottom:0.7rem; color:var(--ink);}
.tg-kb small {color:var(--ink-3);}

/* ---------- controls: raised clay ---------- */
.stButton button, .stDownloadButton button, [data-testid="stFormSubmitButton"] button {border-radius:999px !important;
  font-weight:500; border:none !important; transition:box-shadow .2s, transform .1s;}
.stButton button[kind="secondary"], .stDownloadButton button, [data-testid="stFormSubmitButton"] button[kind="secondary"] {
  background:var(--surface) !important; color:var(--ink) !important; box-shadow:var(--raise-sm);}
.stButton button[kind="secondary"]:hover, .stDownloadButton button:hover {color:var(--cobalt) !important;}
.stButton button:active, .stDownloadButton button:active {box-shadow:var(--sink) !important; transform:translateY(1px);}
.stButton button[kind="primary"], [data-testid="stFormSubmitButton"] button[kind="primary"] {background:var(--cobalt) !important;
  color:#fff !important; box-shadow:var(--accent);}
.stButton button[kind="primary"]:active, [data-testid="stFormSubmitButton"] button[kind="primary"]:active {box-shadow:var(--accent-press) !important;}
[data-testid="stExpander"] details {background:var(--surface); border:none !important; border-radius:18px; box-shadow:var(--raise-sm);}
[data-testid="stExpander"] summary:hover {color:var(--cobalt);}
[data-baseweb="select"] > div, .stTextArea textarea, .stTextInput input {background:var(--paper) !important; border-radius:16px !important;
  border:none !important; box-shadow:var(--field-shadow);}
[data-testid="stForm"] {border:none !important; border-radius:22px; box-shadow:var(--sink); background:var(--field);}
[data-testid="stVerticalBlockBorderWrapper"]:has(> div > [class*="st-key-case_"]), [class*="st-key-case_"], [class*="st-key-done_"] {
  background:var(--surface); border:none !important; border-radius:28px; box-shadow:var(--raise-md); padding:1.2rem 1.3rem !important;}

/* ---------- tabs: inset track, raised cobalt pill that slides ---------- */
.stTabs [role="tablist"] {display:inline-flex; gap:2px; background:var(--surface); border:none !important; border-radius:999px;
  padding:5px; width:fit-content; max-width:100%; margin-bottom:0.9rem; overflow-x:auto; box-shadow:var(--raise-sm) !important;}
.stTabs [role="tablist"]::after, .stTabs [role="tablist"]::before {display:none !important;}
.stTabs [data-testid="stTab"], .stTabs [data-baseweb="tab"] {position:relative; border:none !important; border-radius:999px;
  padding:0.45rem 1.05rem !important; margin:0 !important; height:auto; min-height:0; background:transparent !important; box-shadow:none !important;}
.stTabs [data-testid="stTab"] [data-testid="stMarkdownContainer"], .stTabs [data-baseweb="tab"] [data-testid="stMarkdownContainer"] {position:relative; z-index:1;}
.stTabs [data-testid="stTab"] p, .stTabs [data-baseweb="tab"] p {font-family:var(--mono) !important; font-size:0.78rem;
  text-transform:uppercase; letter-spacing:0.05em; color:var(--ink-3); transition:color .25s; margin:0;}
.stTabs [data-testid="stTab"]:hover p {color:var(--ink);}
.stTabs [data-testid="stTab"][aria-selected="true"] p, .stTabs [data-baseweb="tab"][aria-selected="true"] p {color:#fff;}
.stTabs .react-aria-SelectionIndicator {position:absolute !important; inset:0 !important; width:100% !important; height:100% !important;
  border-radius:999px; background:var(--cobalt-deep) !important; box-shadow:0 4px 12px rgba(14,37,88,.25); z-index:0;
  transition-property:translate, width; transition-duration:.35s; transition-timing-function:cubic-bezier(.4,0,.2,1);}
.stTabs [data-baseweb="tab-highlight"] {background:var(--cobalt) !important; border-radius:999px; height:auto !important; top:5px; bottom:5px; z-index:0;}
.stTabs [data-baseweb="tab-border"] {display:none;}

/* ---------- example question chips ---------- */
[data-testid="stPills"], [data-testid="stButtonGroup"] {justify-content:center;}
[data-testid="stPills"] button, [data-testid="stButtonGroup"] button {border-radius:999px !important; border:none !important;
  background:var(--surface) !important; color:var(--ink-2) !important; box-shadow:var(--raise-sm); margin:4px !important;}
[data-testid="stPills"] button:hover, [data-testid="stButtonGroup"] button:hover {color:var(--cobalt) !important;}
[data-testid="stPills"] label, [data-testid="stButtonGroup"] label {justify-content:center; display:flex;}
.st-key-ex_pills [data-testid="stWidgetLabel"] {justify-content:center; display:flex;}
.st-key-ex_pills [data-testid="stWidgetLabel"] p {font-family:var(--mono) !important; text-transform:uppercase; font-size:0.72rem;
  letter-spacing:0.08em; color:var(--ink-3);}

/* ---------- chat ---------- */
[data-testid="stChatMessage"] {background:var(--surface); border:none; border-radius:28px; padding:1.1rem 1.3rem;
  box-shadow:var(--raise-md); margin-bottom:1.3rem;}
[data-testid="stChatMessage"] [data-testid^="stChatMessageAvatar"] {border-radius:50%; width:2.3rem; height:2.3rem;
  background:var(--surface); color:var(--cobalt); box-shadow:var(--raise-sm); display:flex; align-items:center; justify-content:center;}
[data-testid="stChatMessage"]:has(.tg-a2-mark) [data-testid^="stChatMessageAvatar"] {background:radial-gradient(circle at 30% 28%, #4F86E8 0%, var(--cobalt) 45%, var(--cobalt-deep) 100%);}
[data-testid="stChatMessage"]:has(.tg-a2-mark) [data-testid^="stChatMessageAvatar"] * {color:#fff !important;}
[data-testid="stChatMessage"]:has(.tg-you) {background:linear-gradient(140deg, var(--cobalt), var(--cobalt-deep)); flex-direction:row-reverse; max-width:72%; margin-left:auto;
  box-shadow:var(--accent); border-radius:28px 28px 8px 28px;}
[data-testid="stChatMessage"]:has(.tg-you) p {color:#fff;}
[data-testid="stChatMessage"]:has(.tg-you) [data-testid^="stChatMessageAvatar"] {background:rgba(255,255,255,.16) !important; box-shadow:none; color:#fff;}
[data-testid="stChatInput"] > div {border-radius:24px !important; border:none !important; background:var(--paper) !important;
  box-shadow:var(--field-shadow) !important; min-height:3.6rem;}
[data-testid="stChatInput"] textarea {font-family:var(--sans) !important;}
[data-testid="stChatInput"] textarea:focus-visible {outline:none !important;}
[data-testid="stChatInputSubmitButton"] {background:var(--cobalt) !important; border-radius:50% !important; color:#fff !important;
  box-shadow:var(--accent);}
[data-testid="stChatInputSubmitButton"] svg {fill:#fff !important; color:#fff !important;}
[data-testid="stBottomBlockContainer"], [data-testid="stBottom"] > div {background:var(--cloud);}
.tg-agent {font-family:var(--mono) !important; font-size:0.72rem; letter-spacing:0.08em; text-transform:uppercase; color:var(--ink-3);
  margin-bottom:0.4rem; display:flex; justify-content:space-between; gap:1rem;}

/* ---------- status marks: icon + word + colour, never colour alone ---------- */
.tg-st {display:inline-flex; align-items:center; gap:0.35rem; font-weight:600; font-size:0.9rem; white-space:nowrap;}
.tg-st b {display:inline-flex; width:1.25rem; height:1.25rem; border-radius:50%; align-items:center; justify-content:center;
  font-size:0.72rem; font-weight:700;}
.tg-st b span {color:#fff;}
.tg-ok {color:var(--ok);} .tg-bad {color:var(--bad);} .tg-unk {color:var(--unk);} .tg-rev, .tg-neutral {color:var(--rev);}
.tg-st.tg-ok b, .tg-result.tg-ok .mark {background:var(--ok);} .tg-st.tg-bad b, .tg-result.tg-bad .mark {background:var(--bad);}
.tg-st.tg-unk b, .tg-result.tg-unk .mark {background:var(--unk);} .tg-st.tg-rev b, .tg-st.tg-neutral b, .tg-result.tg-neutral .mark {background:var(--rev);}
.tg-chip {display:inline-flex; align-items:center; gap:0.35rem; padding:0.15rem 0.65rem; border-radius:999px; font-size:0.82rem;
  font-weight:600; white-space:nowrap;}
.tg-chip.tg-ok {background:var(--ok-bg);} .tg-chip.tg-bad {background:var(--bad-bg);} .tg-chip.tg-unk {background:var(--unk-bg);}
.tg-chip.tg-rev, .tg-chip.tg-neutral {background:var(--inset);}
.tg-under {margin-top:0.7rem; padding:0.5rem 0.8rem; border-radius:14px; box-shadow:var(--sink); background:var(--field); font-size:0.88rem; color:var(--ink-3);
  display:flex; align-items:center; gap:0.5rem;}

/* ---------- TrustGuard result: score ring + headline ---------- */
.tg-hero {display:flex; gap:1.1rem; align-items:center; margin:0.2rem 0 1.1rem 0;}
.tg-ring {flex:none; width:84px; height:84px; border-radius:50%; box-shadow:var(--raise-sm); display:flex; align-items:center;
  justify-content:center; position:relative; background:var(--surface);}
.tg-ring svg {position:absolute; inset:7px; width:70px; height:70px; transform:rotate(-90deg);}
.tg-ring svg circle {fill:none; stroke-width:7; stroke-linecap:round;}
.tg-ring .seg {animation:tg-draw 1s cubic-bezier(.4,0,.2,1) both;}
@keyframes tg-draw {from {stroke-dasharray:0 999;}}
.tg-ring .num {position:relative; text-align:center; line-height:1;}
.tg-ring .num b {display:block; font-size:1.2rem; font-weight:600; color:var(--ink);}
.tg-ring .num small {font-family:var(--mono); font-size:0.6rem; color:var(--ink-3); text-transform:uppercase; letter-spacing:.06em;}
.tg-result {display:flex; gap:0.7rem; align-items:flex-start;}
.tg-result .mark {flex:none; width:1.7rem; height:1.7rem; border-radius:50%; display:flex; align-items:center; justify-content:center;
  font-weight:700; margin-top:0.1rem;}
.tg-result .mark span {color:#fff;}
.tg-result h4 {margin:0; padding:0; font-size:1.25rem; font-weight:600; color:var(--ink); letter-spacing:-0.01em;}
.tg-result p {margin:0.15rem 0 0 0; color:var(--ink-2); font-size:0.97rem;}

/* ---------- step tracker (live while checking, then the record of what happened) ---------- */
.tg-track {display:flex; align-items:flex-start; margin:0.2rem 0 1.2rem 0; padding:0.9rem 0.8rem 0.7rem; border-radius:22px;
  box-shadow:var(--sink); background:var(--field);}
.tg-node {flex:1; display:flex; flex-direction:column; align-items:center; position:relative; text-align:center; min-width:0;}
.tg-node:not(:last-child)::after {content:""; position:absolute; top:1.05rem; left:calc(50% + 1.3rem); right:calc(-50% + 1.3rem);
  height:3px; border-radius:3px; background:var(--inset); box-shadow:var(--sink);}
.tg-node.done:not(:last-child)::after, .tg-node.issue:not(:last-child)::after {background:var(--cobalt); box-shadow:none;
  animation:tg-grow .5s ease-out both;}
@keyframes tg-grow {from {transform:scaleX(0); transform-origin:left;} to {transform:scaleX(1); transform-origin:left;}}
.tg-dot {width:2.1rem; height:2.1rem; border-radius:50%; display:flex; align-items:center; justify-content:center; font-size:0.85rem;
  font-weight:600; background:var(--surface); color:var(--ink-3); box-shadow:var(--raise-sm); position:relative; z-index:1;}
.tg-node.done .tg-dot {background:var(--cobalt); color:#fff; box-shadow:0 4px 10px rgba(14,37,88,.25);}
.tg-node.issue .tg-dot {background:var(--bad); color:#fff; box-shadow:0 4px 10px rgba(194,57,46,.3);}
.tg-node.warn .tg-dot {background:var(--unk); color:#fff;}
.tg-node.active .tg-dot {color:var(--cobalt); animation:tg-pulse 1.1s ease-in-out infinite;}
@keyframes tg-pulse {0%,100% {box-shadow:var(--raise-sm), 0 0 0 0 rgba(0,71,187,.35);} 50% {box-shadow:var(--raise-sm), 0 0 0 8px rgba(0,71,187,0);}}
.tg-node.skip .tg-dot {opacity:.45;}
.tg-node .t {font-family:var(--mono); font-size:0.68rem; text-transform:uppercase; letter-spacing:.06em; color:var(--ink-2); margin-top:0.45rem;}
.tg-node .d {font-size:0.75rem; color:var(--ink-3); margin-top:0.1rem; padding:0 0.2rem;}

/* ---------- answer to use, review ---------- */
.tg-useit {border-radius:22px; padding:0.95rem 1.15rem 0.85rem; margin:0 0 1.1rem 0; background:var(--paper); box-shadow:var(--field-shadow);}
.tg-useit p {margin:0.3rem 0; color:var(--ink); font-size:1rem; line-height:1.55;}
.tg-cite {font-family:var(--mono) !important; font-size:0.7rem; color:var(--cobalt-deep); background:var(--blue-soft);
  border-radius:8px; padding:0.08rem 0.45rem; white-space:nowrap; margin-left:0.3rem;}
.tg-small {font-size:0.85rem; color:var(--ink-3); margin-top:0.45rem;}
.tg-src {font-size:0.88rem; color:var(--ink-2); margin:-0.3rem 0 1rem 0;}
.tg-flag {margin:0 0 1rem 0; font-size:0.9rem; color:var(--ink-2); border-radius:18px; padding:0.65rem 0.9rem; box-shadow:var(--sink); background:var(--field);}
.tg-flag b {color:var(--ink);}
.tg-review {border-radius:22px; padding:0.9rem 1.1rem; margin:0 0 0.7rem 0; background:var(--surface); box-shadow:var(--sink);}
.tg-review.waiting {background:var(--blue-soft); box-shadow:var(--sink);}
.tg-review.done {background:var(--paper); box-shadow:var(--field-shadow); border-left:5px solid var(--ok);}
.tg-review p {margin:0.25rem 0; color:var(--ink); font-size:0.95rem;}
.tg-review .who {font-weight:600; color:var(--ink);}
.tg-case {font-family:var(--mono) !important; font-size:0.72rem; color:var(--cobalt-deep); background:var(--paper); border-radius:8px;
  padding:0.08rem 0.45rem; margin-left:0.4rem;}
.tg-q {background:var(--paper); box-shadow:var(--field-shadow); border-radius:16px; padding:0.65rem 0.85rem; margin:0.3rem 0 0.7rem 0;
  color:var(--ink); font-size:0.95rem;}

/* ---------- statements: side-by-side, numbers that differ are highlighted ---------- */
.tg-row {border-radius:22px; padding:1rem 1.1rem 0.8rem; margin-bottom:0.9rem; box-shadow:var(--raise-sm); background:var(--surface);}
.tg-row-head {display:flex; gap:0.8rem; align-items:center; flex-wrap:wrap; margin-bottom:0.7rem;}
.tg-pair {display:grid; grid-template-columns:1fr auto 1fr; gap:0.8rem; align-items:stretch;}
.tg-pair > div.side {border-radius:16px; padding:0.65rem 0.8rem; box-shadow:var(--sink); background:var(--field);}
.tg-pair > div.side.sop {background:var(--paper); box-shadow:var(--field-shadow);}
.tg-pair .vs {align-self:center; font-family:var(--mono); font-size:0.7rem; color:var(--ink-3); width:1.9rem; height:1.9rem;
  border-radius:50%; display:flex; align-items:center; justify-content:center; box-shadow:var(--raise-sm);}
.tg-pair p {margin:0.25rem 0 0 0; color:var(--ink); font-size:0.97rem; line-height:1.55;}
.tg-pair .none {color:var(--ink-3);}
mark.n-bad {background:var(--bad-bg); color:var(--bad); border-radius:6px; padding:0 0.25rem; font-weight:600; text-decoration:line-through;
  text-decoration-thickness:1.5px;}
mark.n-good {background:#DDF0E6; color:var(--ok); border-radius:6px; padding:0 0.25rem; font-weight:600;}
mark.n-same {background:var(--blue-soft); color:var(--cobalt-deep); border-radius:6px; padding:0 0.25rem; font-weight:600;}
.tg-why {margin:0.75rem 0 0 0; font-size:0.9rem; color:var(--ink-2); border-left:3px solid var(--peach); padding-left:0.7rem;}
.tg-why b {color:var(--ink);}
.tg-how {margin-top:0.65rem;}
.tg-how summary {cursor:pointer; color:var(--cobalt); font-size:0.86rem; font-weight:500; list-style:none; font-family:var(--mono);
  text-transform:uppercase; letter-spacing:.05em;}
.tg-how summary::-webkit-details-marker {display:none;}
.tg-how summary::before {content:"+ ";} .tg-how[open] summary::before {content:"– ";}
.tg-steps {list-style:none; counter-reset:s; padding:0; margin:0.5rem 0 0 0;}
.tg-steps li {counter-increment:s; display:flex; gap:0.7rem; padding:0.35rem 0; font-size:0.9rem; color:var(--ink-2);}
.tg-steps li::before {content:counter(s); flex:none; width:1.45rem; height:1.45rem; border-radius:50%; box-shadow:var(--raise-sm);
  color:var(--cobalt); font-size:0.72rem; font-weight:600; display:flex; align-items:center; justify-content:center;}
.tg-steps b {color:var(--ink); font-weight:600; margin-right:0.3rem;}
.tg-list {list-style:none; padding:0; margin:0;}
.tg-list li {display:flex; gap:0.8rem; align-items:flex-start; padding:0.6rem 0; border-top:1px solid var(--rule); font-size:0.93rem; color:var(--ink-2);}
.tg-list li:first-child {border-top:none;}
.tg-list li > div > b {display:block; color:var(--ink); font-weight:600; margin-bottom:0.2rem;}
.tg-list .tg-st {margin-right:0.8rem;}
.tg-empty {color:var(--ink-3); font-size:0.93rem; padding:0.4rem 0;}
.tg-tech {font-family:var(--mono) !important; font-size:0.76rem; color:var(--ink-2); line-height:1.6;}

/* ---------- SOP version timeline ---------- */
.tg-tl {border-radius:22px; padding:0.9rem 1rem 0.8rem; margin:0.2rem 0 1rem 0; box-shadow:var(--sink); background:var(--field);}
.tg-tl-row {margin:0.4rem 0 1.4rem 0;}
.tg-tl-name {font-size:0.85rem; color:var(--ink); font-weight:600; margin-bottom:0.45rem;}
.tg-tl-bar {position:relative; height:2.1rem; border-radius:999px; background:var(--inset); box-shadow:var(--sink-deep);}
.tg-seg {position:absolute; top:4px; bottom:4px; border-radius:999px; display:flex; align-items:center; justify-content:center;
  font-family:var(--mono); font-size:0.7rem; white-space:nowrap; overflow:hidden; animation:tg-in .6s ease-out both;}
@keyframes tg-in {from {opacity:0; transform:scaleX(.6);}}
.tg-seg.old {background:repeating-linear-gradient(135deg, #C9D2DE 0 6px, #D3DBE5 6px 12px); color:var(--ink-3);}
.tg-seg.cur {background:var(--cobalt); color:#fff;}
.tg-seg.read {outline:2.5px solid var(--peach); outline-offset:1px;}
.tg-today {position:absolute; top:-6px; bottom:-6px; width:2px; background:var(--ink); border-radius:2px;}
.tg-today span {position:absolute; top:calc(100% + 2px); left:50%; transform:translateX(-50%); font-family:var(--mono);
  font-size:0.62rem; color:var(--ink); white-space:nowrap; text-transform:uppercase;}
.tg-legend {display:flex; gap:1.1rem; flex-wrap:wrap; font-size:0.78rem; color:var(--ink-3); margin-top:0.2rem;}
.tg-legend i {display:inline-block; width:0.9rem; height:0.6rem; border-radius:4px; margin-right:0.35rem; vertical-align:middle;}

.tg-mock {background:var(--tip); color:#fff; padding:0.7rem 1rem; border-radius:18px; font-weight:500; margin-bottom:1rem;}
.tg-ico {display:inline-block; vertical-align:-0.15em; flex:none;}
.rv-fail-h {font-weight:600; color:var(--ink); font-size:0.95rem; margin:0.8rem 0 0.1rem;}
.rv-card, .rv-tile {background:var(--surface) !important; border:none !important; box-shadow:var(--raise-md) !important; border-radius:28px !important;}
@media (max-width:720px) {.tg-pair {grid-template-columns:1fr;} .tg-pair .vs {display:none;}
  [data-testid="stChatMessage"]:has(.tg-you) {max-width:100%;} .tg-top h1 {font-size:2.3rem;} .tg-node .d {display:none;}}
/* ===================== interactive pieces (Senthora-inspired) ===================== */
/* Hero: animated line mesh behind a gradient headline */
.tg-hero-wrap {position:relative; border-radius:32px; overflow:hidden; padding:2.6rem 1.5rem 2.2rem; margin:0 0 1.6rem 0;
  background:var(--hero); box-shadow:var(--raise-md);}
.tg-mesh {position:absolute; inset:0; width:100%; height:100%; pointer-events:none; opacity:.9;}
.tg-mesh path {fill:none; stroke-width:1.2;}
.tg-mesh .w1 {stroke:rgba(47,107,224,.35); animation:tg-wave 9s ease-in-out infinite alternate;}
.tg-mesh .w2 {stroke:rgba(14,37,88,.22); animation:tg-wave 12s ease-in-out infinite alternate-reverse;}
.tg-mesh .w3 {stroke:rgba(47,107,224,.18); animation:tg-wave 15s ease-in-out infinite alternate;}
@keyframes tg-wave {from {transform:translateX(-4%) translateY(0);} to {transform:translateX(4%) translateY(-10px);}}
.tg-mesh .dot {fill:var(--bright); animation:tg-blink 3s ease-in-out infinite;}
@keyframes tg-blink {0%,100% {opacity:.15;} 50% {opacity:.9;}}
.tg-hero-wrap .tg-top {position:relative; margin:0 auto;}
.tg-grad {background:linear-gradient(90deg, var(--grad-a) 0%, var(--grad-b) 45%, #5A8DEE 55%, var(--grad-a) 100%);
  background-size:220% 100%; -webkit-background-clip:text; background-clip:text; color:transparent !important;
  animation:tg-shimmer 6s linear infinite; font-style:normal !important; font-family:var(--sans) !important; font-weight:600 !important;}
@keyframes tg-shimmer {to {background-position:-220% 0;}}
.tg-chips {display:flex; gap:0.5rem; justify-content:center; flex-wrap:wrap; margin-top:1.1rem; position:relative;}
.tg-chips span {font-family:var(--mono); font-size:0.7rem; text-transform:uppercase; letter-spacing:.06em; color:var(--link-on);
  background:var(--glass); border-radius:999px; padding:0.35rem 0.8rem; box-shadow:var(--raise-sm); backdrop-filter:blur(6px);}

/* Cards arrive with a short rise, one after another */
.tg-rise {animation:tg-rise .55s cubic-bezier(.2,.7,.2,1) both;}
@keyframes tg-rise {from {opacity:0; transform:translateY(12px);}}
.tg-row:nth-child(2) {animation-delay:.08s;} .tg-row:nth-child(3) {animation-delay:.16s;} .tg-row:nth-child(4) {animation-delay:.24s;}
.tg-row {animation:tg-rise .55s cubic-bezier(.2,.7,.2,1) both;}
.tg-row:hover {box-shadow:var(--raise-md); transform:translateY(-1px); transition:box-shadow .2s, transform .2s;}

/* Agent 1's answer, marked up after the check: each statement lights up in turn; hover or tap for the fix */
.tg-ann {position:static; border-radius:6px; padding:0.05rem 0.15rem; cursor:help; outline:none;
  animation:tg-light .7s ease-out both; animation-delay:calc(var(--i) * .35s);}
.tg-ann.ok {background:linear-gradient(transparent 62%, rgba(20,122,75,.22) 62%);}
.tg-ann.bad {background:linear-gradient(transparent 62%, rgba(194,57,46,.28) 62%);}
.tg-ann.unk {background:linear-gradient(transparent 62%, rgba(154,100,0,.25) 62%);}
@keyframes tg-light {from {background-size:0% 100%; background-repeat:no-repeat;} to {background-size:100% 100%;}}
.tg-ann .tip {position:absolute; left:0; bottom:calc(100% + 8px); z-index:20; width:min(420px, 80vw); background:var(--tip); color:#fff;
  border-radius:14px; padding:0.65rem 0.8rem; font-size:0.84rem; line-height:1.45; box-shadow:0 14px 34px rgba(14,26,51,.3);
  opacity:0; transform:translateY(4px); pointer-events:none; transition:opacity .18s, transform .18s;}
.tg-ann:hover .tip, .tg-ann:focus .tip {opacity:1; transform:none;}
.tg-ann .tip b {color:#fff;} .tg-ann .tip .k {font-family:var(--mono); font-size:0.66rem; text-transform:uppercase; letter-spacing:.06em; color:#9FB4DA; display:block;}
.tg-ann .tip .fix {display:block; margin-top:0.35rem;} .tg-ann .tip s {color:#FFB4AC;} .tg-ann .tip ins {color:#A7E3C4; text-decoration:none; font-weight:600;}
.tg-answer-text {font-size:1rem; line-height:1.75; color:var(--ink); position:relative;}
.tg-legend2 {font-size:0.78rem; color:var(--ink-3); margin-top:0.55rem;}

/* Fix next to its rule: "was → now, because" */
.tg-fixline {display:flex; flex-wrap:wrap; align-items:center; gap:0.45rem; margin:0.7rem 0 0 0; font-size:0.9rem;}
.tg-fixline .was {background:var(--bad-bg); color:var(--bad); border-radius:8px; padding:0.1rem 0.45rem; text-decoration:line-through;}
.tg-fixline .now {background:var(--ok-bg); color:var(--ok); border-radius:8px; padding:0.1rem 0.45rem; font-weight:600;}
.tg-fixline .arr {color:var(--ink-3); animation:tg-nudge 1.4s ease-in-out infinite;}
@keyframes tg-nudge {0%,100% {transform:translateX(0);} 50% {transform:translateX(3px);}}

/* Step tracker: hover a step for what happened there */
.tg-node .pop {position:absolute; top:calc(100% + 6px); left:50%; transform:translate(-50%, -4px); width:200px; z-index:15;
  background:var(--tip); color:#fff; border-radius:12px; padding:0.55rem 0.7rem; font-size:0.78rem; line-height:1.4; text-align:left;
  opacity:0; pointer-events:none; transition:opacity .18s, transform .18s; box-shadow:0 12px 28px rgba(14,26,51,.28);}
.tg-node:hover .pop, .tg-node:focus-within .pop {opacity:1; transform:translate(-50%, 0);}
.tg-node {cursor:default;} .tg-node:hover .tg-dot {transform:scale(1.08); transition:transform .15s;}

/* Primary buttons: a light sweep on hover */
.stButton button[kind="primary"], [data-testid="stFormSubmitButton"] button[kind="primary"] {position:relative; overflow:hidden;
  background:linear-gradient(140deg, var(--cobalt), var(--cobalt-deep)) !important;}
.stButton button[kind="primary"]::after, [data-testid="stFormSubmitButton"] button[kind="primary"]::after {content:""; position:absolute;
  top:0; left:-60%; width:40%; height:100%; background:linear-gradient(100deg, transparent, rgba(255,255,255,.35), transparent);
  transform:skewX(-20deg); transition:left .6s;}
.stButton button[kind="primary"]:hover::after, [data-testid="stFormSubmitButton"] button[kind="primary"]:hover::after {left:120%;}

</style>
"""


# ---------- line icons (replace decorative emoji, which the team felt looked AI-generated) ----------
# Simple outline icons (shapes based on the open-source Lucide set, ISC licence).
# They take the text colour of wherever they sit. ✓ ✕ ? stay as text: they are status marks, not decoration.
_ICON_PATHS = {
    "shield": '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>',
    "bank": '<path d="M3 22h18"/><path d="M6 18v-7"/><path d="M10 18v-7"/><path d="M14 18v-7"/><path d="M18 18v-7"/>'
            '<path d="M12 2l8 5H4z"/>',
    "message": '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>',
    "check": '<path d="M20 6 9 17l-5-5"/>',
    "clock": '<circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/>',
}

DARK_CSS = """
<style>
/* Dark mode: the same navy brand on a deep-navy page. Status colours are lifted so they stay readable. */
:root {
  --cloud:#0A1428; --surface:#111E38; --inset:#0C172E; --field:#0E1A32; --paper:#14223F;
  --ink:#E9EFF9; --ink-2:#B6C2D8; --ink-3:#8593AE; --line:#22334F; --rule:#1C2B47;
  --cobalt:#3E70DB; --cobalt-deep:#1A3A7C; --bright:#7FA7F6; --powder:#25406E; --blue-soft:#1A2D55; --blush:#3D1C1F;
  --raise-sm:0 0 0 1px #1F2F4D, 0 4px 12px rgba(0,0,0,.25);
  --raise-md:0 0 0 1px #1F2F4D, 0 12px 32px rgba(0,0,0,.35);
  --raise-lg:0 0 0 1px #22334F, 0 18px 44px rgba(0,0,0,.45);
  --sink:inset 0 0 0 1px #22334F; --sink-deep:inset 0 1px 3px rgba(0,0,0,.4), inset 0 0 0 1px #22334F;
  --field-shadow:0 0 0 1px #22334F, 0 4px 14px rgba(0,0,0,.3);
  --navy:#8FB0F0; --sky:#1F3560; --tint:#1A2D55;
  --ok:#4CC38A; --ok-bg:#123527; --bad:#F2766C; --bad-bg:#3F1D20; --unk:#E8B64F; --unk-bg:#3A2C12;
  --rev:#A9B5C8; --neutral:#9AA6B9;
  --tip:#1D2D50; --hero:radial-gradient(120% 140% at 50% 0%, #1A2C52 0%, #111E38 55%, #0C172E 100%);
  --glass:rgba(17,30,56,.85); --link-on:#BFD2F7; --grad-a:#9DBBF5; --grad-b:#E3ECFF;
  color-scheme:dark;
}
.tg-mesh .w1 {stroke:rgba(127,167,246,.35);} .tg-mesh .w2 {stroke:rgba(190,210,250,.18);} .tg-mesh .w3 {stroke:rgba(127,167,246,.2);}
/* Streamlit's own widgets are drawn from the light theme in config.toml, so repaint their text and fields */
.stApp, .stApp p, .stApp li, .stApp label, .stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp summary,
[data-testid="stWidgetLabel"] p, [data-testid="stMarkdownContainer"], [data-testid="stExpander"] summary span {color:var(--ink);}
[data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p, .stApp small {color:var(--ink-3) !important;}
[data-testid="stHeader"] button, [data-testid="stToolbar"] *, [data-testid="stSidebarCollapseButton"] * ,
[data-testid="stExpandSidebarButton"] * {color:var(--ink-2) !important;}
.stApp input, .stApp textarea, [data-baseweb="select"] > div, [data-baseweb="select"] *, [data-testid="stChatInput"] textarea
  {color:var(--ink) !important; -webkit-text-fill-color:var(--ink); caret-color:var(--ink);}
.stApp textarea::placeholder, .stApp input::placeholder {color:var(--ink-3) !important; -webkit-text-fill-color:var(--ink-3);}
[data-baseweb="popover"] ul, [data-baseweb="popover"] li, [data-baseweb="menu"] {background:var(--paper) !important; color:var(--ink) !important;}
[data-baseweb="popover"] li:hover, [data-baseweb="popover"] li[aria-selected="true"] {background:var(--blue-soft) !important;}
[data-testid="stTooltipContent"], [data-baseweb="tooltip"] > div {background:var(--tip) !important; color:#fff !important;}
.stButton button[kind="secondary"], .stDownloadButton button, [data-testid="stFormSubmitButton"] button[kind="secondary"],
[data-testid="stPills"] button, [data-testid="stButtonGroup"] button {background:var(--paper) !important; color:var(--ink) !important;}
.stButton button[kind="secondary"] p, [data-testid="stPills"] button p {color:var(--ink) !important;}
[data-testid="stPills"] button[kind$="Active"], [data-testid="stButtonGroup"] button[aria-checked="true"] {background:var(--cobalt) !important;}
[data-testid="stCheckbox"] label span, [data-testid="stToggle"] label > div:first-child {border-color:var(--line);}
[data-testid="stAlert"] > div {background:var(--paper) !important; color:var(--ink) !important;}
[data-testid="stAlert"] p {color:var(--ink) !important;}
[data-testid="stCode"] pre, code {background:var(--inset) !important; color:var(--ink) !important;}
[data-testid="stStatusWidget"] *, [data-testid="stDecoration"] {color:var(--ink-2);}
/* Streamlit draws some icons with the light theme's text colour baked in; lift them */
span[color="#0E1A33"], [data-testid="stIconMaterial"][color="#0E1A33"] {color:var(--ink-2) !important;}
[data-testid^="stChatMessageAvatar"] {color:var(--ink-2);}
/* Select boxes and their option lists (React Aria in this Streamlit version) */
.react-aria-ComboBox [role="group"], .stSelectbox [role="group"] {background:var(--paper) !important; border-color:var(--line) !important;}
.react-aria-ComboBox input {background:transparent !important;}
.react-aria-Popover, .react-aria-ListBox, [role="listbox"] {background:var(--paper) !important; color:var(--ink) !important; border-color:var(--line) !important;}
[role="option"] {color:var(--ink) !important;} [role="option"][data-focused], [role="option"][data-selected] {background:var(--blue-soft) !important;}
/* Switches: give the "off" track a visible colour on the dark page */
.stApp label[data-rac]:not([data-selected]) > div:not([data-testid]) {background:#2B3F66 !important;}
/* Small tags and highlights that used dark navy text */
.tg-cite {color:var(--link-on) !important; background:var(--blue-soft) !important;}
mark.n-same {color:var(--link-on) !important;}
hr {border-color:var(--line) !important;}
</style>
"""


MESH = ('<svg class="tg-mesh" viewBox="0 0 1000 220" preserveAspectRatio="none" aria-hidden="true">'
        ' <path class="w1" d="M-60 40 C 160 10, 320 120, 520 60 S 860 0, 1080 70"/><path class="w2" d="M-60 58 C 160 32, 320 126, 520 76 S 860 20, 1080 84"/><path class="w3" d="M-60 76 C 160 54, 320 132, 520 92 S 860 40, 1080 98"/><path class="w1" d="M-60 94 C 160 76, 320 138, 520 108 S 860 60, 1080 112"/><path class="w2" d="M-60 112 C 160 98, 320 144, 520 124 S 860 80, 1080 126"/><path class="w3" d="M-60 130 C 160 120, 320 150, 520 140 S 860 100, 1080 140"/><path class="w1" d="M-60 148 C 160 142, 320 156, 520 156 S 860 120, 1080 154"/><path class="w2" d="M-60 166 C 160 164, 320 162, 520 172 S 860 140, 1080 168"/><path class="w3" d="M-60 184 C 160 186, 320 168, 520 188 S 860 160, 1080 182"/><circle class="dot" cx="140" cy="60" r="2.2" style="animation-delay:0s"/><circle class="dot" cx="330" cy="150" r="2.2" style="animation-delay:0.8s"/><circle class="dot" cx="520" cy="70" r="2.2" style="animation-delay:1.6s"/><circle class="dot" cx="720" cy="130" r="2.2" style="animation-delay:0.4s"/><circle class="dot" cx="900" cy="50" r="2.2" style="animation-delay:1.2s"/><circle class="dot" cx="980" cy="170" r="2.2" style="animation-delay:2s"/>'
        '</svg>')


def icon(name: str, size: str = "1.1em") -> str:
    return (f'<svg class="tg-ico" width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" '
            f'stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" '
            f'aria-hidden="true">{_ICON_PATHS[name]}</svg>')


def is_dark() -> bool:
    return bool(st.session_state.get("tg_dark", False))


def apply_base_theme() -> None:
    """Light by default; the sidebar switch (page_nav) adds the dark palette on top. The choice is kept in
    session_state under a plain key, so it carries over when the user moves between pages."""
    st.markdown(THEME_CSS, unsafe_allow_html=True)
    if is_dark():
        st.markdown(DARK_CSS, unsafe_allow_html=True)


def _remember_mode() -> None:
    st.session_state["tg_dark"] = st.session_state["tg_dark_switch"]


def mode_switch() -> None:
    st.toggle(":material/dark_mode: Dark mode", value=is_dark(), key="tg_dark_switch", on_change=_remember_mode,
              help="Switch between the light (white) and dark (navy) look. Kept while you move between pages.")


def page_nav() -> None:
    """Brand and links between the pages, at the top of the sidebar (the automatic page list is hidden
    in .streamlit/config.toml, because it would label the main page with its file name, "app")."""
    from modules import review_queue
    st.markdown(f'<div class="tg-brand"><span>{icon("shield", "1.05rem")}</span>TrustGuard</div>', unsafe_allow_html=True)
    mode_switch()
    try:
        waiting = sum(1 for c in review_queue.cases().values() if c["status"] == "waiting")
        st.page_link("app.py", label="Assistant", icon=":material/chat:")
        st.page_link("pages/review_queue.py", label=f"Review queue{f' · {waiting} waiting' if waiting else ''}",
                     icon=":material/fact_check:")
        st.page_link("pages/reliability.py", label="How reliable is TrustGuard?", icon=":material/verified_user:")
    except StreamlitAPIException:  # page opened on its own (e.g. in tests), not through app.py
        pass


def reliability_link() -> None:
    """Kept for compatibility. The result view no longer shows this link under every verdict
    (it is in the sidebar instead), so the chat stays uncluttered."""
    return None
