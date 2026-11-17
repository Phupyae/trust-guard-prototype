"""Shared look for every page of the TrustGuard app (assistant chat and evaluation results).

Colours, fonts and the status chips live here once, so a UI/UX change made in this file shows up
on every page. Page-specific styles stay in the page itself.
"""
import streamlit as st
from streamlit.errors import StreamlitAPIException

BASE_CSS = """
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
"""


def apply_base_theme() -> None:
    st.markdown(BASE_CSS, unsafe_allow_html=True)


def page_nav() -> None:
    """Sidebar links between the pages (the automatic page list is hidden in .streamlit/config.toml,
    because it would label the main page with its file name, "app")."""
    try:
        st.page_link("app.py", label="Banking AI Assistant", icon="🏦")
        st.page_link("pages/evaluation.py", label="Evaluation results", icon="📊")
    except StreamlitAPIException:  # page opened on its own (e.g. in tests), not through app.py
        pass
