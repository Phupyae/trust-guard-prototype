"""Shared look for every page of the TrustGuard app (assistant chat and reliability results).

Colours, fonts and the status chips live here once, so a UI/UX change made in this file shows up
on every page. Page-specific styles stay in the page itself.

Visual direction (Nov 2026): based on the "Cairo" digital banking template the team chose.
  - Deep navy for the header and primary actions; pale blue-grey page; content on white cards
  - Large rounded corners, circular icon badges, pill-shaped buttons
  - Big, bold numbers with a small caption underneath
The status colours (green ✓ / red ✕ / amber ?) are NOT decoration: they carry meaning, always with an
icon and a word, so they stay the same on every page whatever the brand colours are.
"""
import streamlit as st
from streamlit.errors import StreamlitAPIException

BASE_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Manrope:wght@500;600;700;800&family=Inter:wght@400;500;600;700&family=Source+Serif+4:opsz,wght@8..60,400;8..60,600&display=swap');
:root {
  /* Brand (from the Cairo template) */
  --navy:#0E2558; --navy-2:#1C3D82; --accent:#2457C5; --accent-dark:#1A45A3;
  --sky:#CFE2F7; --tint:#EAF2FC; --sidebar:#FFFFFF; --page:#F3F5F9; --panel:#F7F9FC; --line:#E2E7EF;
  /* Text */
  --ink:#0E1A33; --ink-2:#465469; --ink-3:#6A7587; --rule:#DCE2EA; --desk:#EEF1F5;
  /* Status: meaning, not decoration */
  --ok:#17663F; --ok-bg:#E5F4EC; --bad:#B0241C; --bad-bg:#FCEBE9;
  --unk:#7A5200; --unk-bg:#FFF4D9; --rev:#3F4A5C; --rev-bg:#E9ECF2; --neutral:#465469; --neutral-bg:#EEF1F5;
  --radius:16px; --shadow:0 1px 2px rgba(14,37,88,0.04), 0 4px 16px rgba(14,37,88,0.06);
}
html, body, .stApp, .stMarkdown, input, textarea, button, label, [data-testid="stSidebar"] {
  font-family:'Inter', system-ui, sans-serif !important;
}
h1, h2, h3, .tg-hero h1 {font-family:'Manrope', 'Inter', system-ui, sans-serif !important;}
/* Clear Streamlit's fixed toolbar so nothing at the top of the page is hidden under it */
.block-container {padding-top:4.5rem; max-width:1100px;}
.stApp {background:var(--page);}
[data-testid="stHeader"] {background:transparent;}
a, a:visited {color:var(--accent);}
*:focus-visible {outline:3px solid var(--accent) !important; outline-offset:2px;}

/* Header: navy gradient like the template's app header, white text */
.tg-hero {background:linear-gradient(135deg, var(--navy) 0%, var(--navy-2) 70%, #4F6FB5 130%); color:#fff;
  border-radius:24px; padding:1.8rem 2rem 1.6rem; margin-bottom:1.2rem; box-shadow:var(--shadow);}
.tg-hero h1 {color:#fff !important; font-size:2.1rem; font-weight:800; letter-spacing:-0.02em;
  margin:0 0 0.5rem 0; padding:0; display:flex; align-items:center; gap:0.7rem;}
.tg-hero h1 .tg-logo {display:inline-flex; align-items:center; justify-content:center; width:2.6rem; height:2.6rem;
  border-radius:50%; background:rgba(255,255,255,0.14); font-size:1.3rem;}
.tg-hero p {color:#D9E4F7; font-size:1.02rem; max-width:68ch; margin:0;}
.tg-hero p b {color:#fff;}
.tg-hero .tg-pill {display:inline-block; background:rgba(255,255,255,0.12); color:#fff;
  border:1px solid rgba(255,255,255,0.28); border-radius:999px; padding:0.25rem 0.85rem; font-size:0.8rem;
  font-weight:600; margin-top:1rem; margin-right:0.4rem;}

/* Sidebar: white, navigation like the template's dashboard (icon + label, active item highlighted) */
[data-testid="stSidebar"] {background:var(--sidebar); border-right:1px solid var(--line);}
[data-testid="stSidebar"] h3 {color:var(--ink-3); font-size:0.78rem !important; font-weight:700;
  text-transform:uppercase; letter-spacing:0.06em; margin-top:0.8rem; padding-bottom:0.1rem; border:none;}
[data-testid="stSidebar"] .tg-kb .t {color:var(--navy);}
[data-testid="stSidebar"] [data-testid="stPageLink"] a {border-radius:12px; padding:0.45rem 0.7rem;}
[data-testid="stSidebar"] [data-testid="stPageLink"] a:hover {background:var(--tint);}
[data-testid="stSidebar"] [data-testid="stPageLink"] a[aria-current="page"] {background:var(--tint);}
[data-testid="stSidebar"] [data-testid="stPageLink"] a[aria-current="page"] span {color:var(--accent); font-weight:700;}
.tg-brand {font-family:'Manrope', sans-serif; font-weight:800; font-size:1.35rem; color:var(--navy);
  letter-spacing:-0.02em; margin:0 0 0.6rem 0.3rem; display:flex; align-items:center; gap:0.45rem;}
.tg-brand span {display:inline-flex; width:1.9rem; height:1.9rem; border-radius:50%; background:var(--navy);
  color:#fff; align-items:center; justify-content:center; font-size:0.95rem;}

/* Buttons: pill shapes. Primary = navy, secondary = light grey (as in the template) */
.stButton button, .stDownloadButton button, [data-testid="stFormSubmitButton"] button {border-radius:999px !important;
  font-weight:600;}
.stButton button[kind="secondary"], .stDownloadButton button {background:#EEF1F6; border:1px solid transparent;
  color:var(--navy);}
.stButton button[kind="secondary"]:hover, .stDownloadButton button:hover {background:var(--tint);
  border-color:var(--sky); color:var(--accent);}
.stButton button[kind="primary"] {background:var(--navy); border-color:var(--navy); color:#fff;}
.stButton button[kind="primary"]:hover {background:var(--navy-2); border-color:var(--navy-2);}
/* Sidebar example questions: list rows, like the template's transaction list */
[data-testid="stSidebar"] .stButton button[kind="secondary"] {background:#fff; border:1px solid var(--line);
  border-radius:14px !important; justify-content:flex-start; text-align:left; padding:0.55rem 0.8rem;
  box-shadow:0 1px 2px rgba(14,37,88,0.04); color:var(--ink);}
[data-testid="stSidebar"] .stButton button[kind="secondary"] p {text-align:left;}
[data-testid="stSidebar"] .stButton button[kind="secondary"]:hover {border-color:var(--accent); color:var(--accent);
  background:#fff;}

/* Cards: white, large radius, soft shadow */
[data-testid="stVerticalBlockBorderWrapper"]:has(> div > [class*="st-key-card_"]),
[class*="st-key-card_"] {background:#fff; border-radius:var(--radius);}
[data-testid="stExpander"] details {background:#fff; border:1px solid var(--line) !important; border-radius:var(--radius);}
[data-testid="stExpander"] summary:hover {color:var(--accent);}
.stApp .st-key-panel_input, .stApp .st-key-panel_verify {background:var(--panel); border-color:var(--line) !important;}
.st-key-panel_input input, .st-key-panel_input textarea,
.st-key-panel_input [data-baseweb="select"] > div {background:#fff !important;}
h1, h2, h3 {color:var(--ink); letter-spacing:-0.015em;}
.tg-lede {color:var(--ink-2); font-size:1.02rem; max-width:68ch; margin:-0.4rem 0 1.2rem 0;}
.tg-step {font-weight:600; font-size:1.1rem; color:var(--navy); margin:0.3rem 0 0.2rem 0;}
.tg-step span {display:inline-block; width:1.6rem; height:1.6rem; line-height:1.6rem; text-align:center;
  border-radius:50%; background:var(--navy); color:#fff; font-size:0.85rem; margin-right:0.5rem;}
.tg-help {color:var(--ink-3); font-size:0.88rem; margin:0 0 0.6rem 0; max-width:72ch;}

/* Status chips: pill shaped; icon + word + colour, never colour alone */
.tg-chip {display:inline-flex; align-items:center; gap:0.35rem; padding:0.2rem 0.7rem; border-radius:999px;
  font-size:0.84rem; font-weight:600; border:1px solid currentColor; white-space:nowrap;}
.tg-chip b {font-size:0.95rem;}
.tg-ok {color:var(--ok); background:var(--ok-bg);}  .tg-bad {color:var(--bad); background:var(--bad-bg);}
.tg-unk {color:var(--unk); background:var(--unk-bg);} .tg-rev {color:var(--rev); background:var(--rev-bg);}
.tg-neutral {color:var(--neutral); background:var(--neutral-bg);}

.tg-verdict {display:flex; gap:0.9rem; align-items:flex-start; padding:1rem 1.2rem; border-radius:var(--radius);
  border:1px solid var(--line); border-left:6px solid currentColor; margin:0.6rem 0 0.8rem 0; box-shadow:var(--shadow);}
.tg-verdict .big {font-size:1.25rem; font-weight:700; line-height:1; width:2.3rem; height:2.3rem; flex:none;
  border-radius:50%; display:flex; align-items:center; justify-content:center; background:#fff;
  border:2px solid currentColor;}
.tg-verdict .msg {color:var(--ink); font-weight:600; font-size:1.05rem;}
.tg-verdict .counts {display:flex; flex-wrap:wrap; gap:0.4rem; margin-top:0.55rem;}

.tg-legend {background:#fff; border:1px solid var(--line); border-radius:14px; padding:0.65rem 1rem; display:flex;
  flex-wrap:wrap; gap:0.5rem 1.2rem; color:var(--ink-2); font-size:0.85rem; margin:0.2rem 0 0.8rem 0;}
.tg-legend div {display:flex; gap:0.45rem; align-items:center;}

.tg-card {border-left:5px solid currentColor; padding:0.2rem 0 0.1rem 1rem;}
.tg-card-head {display:flex; gap:0.6rem; align-items:center; flex-wrap:wrap; margin-bottom:0.7rem;}
.tg-claimno {color:var(--ink-3); font-size:0.9rem; font-weight:600;}
.tg-compare {display:grid; grid-template-columns:1fr 1fr; gap:1rem;}
.tg-col-label {color:var(--ink-3); font-size:0.78rem; font-weight:700; text-transform:uppercase;
  letter-spacing:0.04em; margin-bottom:0.35rem;}
.tg-doc {font-family:'Source Serif 4', Georgia, serif; font-size:1.06rem; line-height:1.55; color:var(--ink);
  background:var(--panel); border:1px solid var(--line); border-radius:12px; padding:0.75rem 0.9rem;}
.tg-doc.empty {font-family:'Inter', system-ui, sans-serif; color:var(--ink-3); font-size:0.92rem; background:var(--panel);}
.tg-col-label.policy {color:var(--accent);}
.tg-source {color:var(--ink-2); font-size:0.82rem; margin-top:0.35rem;}
.tg-why {color:var(--ink); margin:0.8rem 0 0.2rem 0; max-width:80ch;}
.tg-why strong {color:var(--ink-2);}

/* "How it works" strip: white cards with circular icons, like the template's quick-action buttons */
.tg-flow {display:flex; align-items:stretch; gap:0.6rem; margin:0 0 1.3rem 0; flex-wrap:wrap;}
.tg-flow div {flex:1 1 150px; background:#fff; border:1px solid var(--line); border-radius:var(--radius);
  padding:0.85rem 0.9rem; box-shadow:var(--shadow);}
.tg-flow div em {display:flex; width:2.3rem; height:2.3rem; border-radius:50%; background:var(--tint);
  align-items:center; justify-content:center; font-style:normal; font-size:1.05rem; margin-bottom:0.5rem;}
.tg-flow div.a2 em {background:var(--navy); color:#fff;}
.tg-flow b {display:block; color:var(--navy); font-size:0.9rem;} .tg-flow span {color:var(--ink-3); font-size:0.82rem;}
.tg-flow i {align-self:center; color:var(--ink-3); font-style:normal; font-weight:700;}

.tg-answer {font-size:1.08rem; line-height:1.6; color:var(--ink); background:#fff; border:1px solid var(--rule);
  border-left:6px solid currentColor; border-radius:var(--radius); padding:0.9rem 1.1rem; margin:0.3rem 0 0.4rem 0;}
.tg-answer .who {display:block; font-size:0.8rem; font-weight:600; color:var(--ink-3); margin-bottom:0.35rem;}
.tg-answer p {color:var(--ink); margin:0;}
.tg-agent {font-size:0.74rem; font-weight:700; letter-spacing:0.06em; color:var(--ink-3); margin-bottom:0.3rem;}
.tg-agent.tg-a2 {color:var(--accent);}
.tg-intercept {display:flex; gap:0.7rem; align-items:center; background:var(--tint); border:1px dashed var(--accent);
  color:var(--navy); border-radius:14px; padding:0.6rem 0.95rem; font-weight:600; margin:0.1rem 0 0.6rem 0;}
.tg-intercept small {display:block; font-weight:400; color:var(--ink-2);}
.tg-held {margin-top:0.5rem;}

/* Chat: each message is a white card; avatars are circles (like the template's initials) */
[data-testid="stChatMessage"] {background:#fff; border:1px solid var(--line); border-radius:20px;
  padding:1rem 1.1rem; box-shadow:var(--shadow); margin-bottom:0.7rem;}
[data-testid="stChatMessage"]:has(.tg-you) {background:var(--tint);
  border-color:var(--sky); box-shadow:none;}
[data-testid="stChatMessage"] [data-testid^="stChatMessageAvatar"] {border-radius:50%; width:2.3rem; height:2.3rem;
  background:var(--tint); color:var(--navy); display:flex; align-items:center; justify-content:center;}
[data-testid="stChatMessage"]:has(.tg-you) [data-testid^="stChatMessageAvatar"] {background:#fff !important;}
[data-testid="stChatInput"] {border-radius:999px;}
[data-testid="stChatInput"] > div {border-radius:999px; border-color:var(--line); background:#fff;
  box-shadow:var(--shadow);}
[data-testid="stBottomBlockContainer"], [data-testid="stBottom"] > div {background:var(--page);}
@media (max-width:720px) {.tg-compare {grid-template-columns:1fr;} .block-container {padding-top:4rem;}}

.tg-mock {background:var(--rev); color:#fff; padding:0.75rem 1.1rem; border-radius:14px; font-weight:600; margin-bottom:0.8rem;}
.tg-stale {background:var(--desk); border:1px dashed var(--ink-3); color:var(--ink-2); padding:0.6rem 0.9rem;
  border-radius:12px; font-size:0.92rem; margin:0.4rem 0;}
.tg-kb {font-size:0.86rem; margin-bottom:0.6rem; color:var(--ink);}
.tg-kb small {color:var(--ink-3);}
</style>
"""


# ---------- design options (team is choosing; the picker in the sidebar switches between them) ----------
# Each option only overrides colours, fonts and a few shapes on top of BASE_CSS. Layout and content are the
# same in all of them, so whichever one is picked, nothing else in the app has to change.
DESIGNS = {
    "classic": {
        "label": "A · Cairo classic",
        "about": "Navy gradient header, white sidebar, white cards on pale grey. Closest to the template.",
        "css": "",
    },
    "navy": {
        "label": "B · Navy sidebar",
        "about": "Dark navy sidebar like the template's presentation pages; light header card with a navy title.",
        "css": """
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:opsz,wght@9..40,400;9..40,500;9..40,600;9..40,700&display=swap');
:root {--page:#F5F7FB; --tint:#EAF1FD; --accent:#2F6BE0; --radius:14px;}
html, body, .stApp, .stMarkdown, input, textarea, button, label, [data-testid="stSidebar"] {
  font-family:'DM Sans', system-ui, sans-serif !important;}
/* Sidebar: navy, white text */
[data-testid="stSidebar"] {background:linear-gradient(180deg, #0B1F4D 0%, #12306E 100%); border-right:none;}
[data-testid="stSidebar"] *, [data-testid="stSidebar"] .stMarkdown p,
[data-testid="stSidebar"] [data-testid="stCaptionContainer"] {color:#D5E0F5;}
[data-testid="stSidebar"] h3 {color:#8FA8D8 !important;}
.tg-brand {color:#fff !important;} .tg-brand span {background:#fff; color:var(--navy) !important;}
[data-testid="stSidebar"] [data-testid="stPageLink"] a:hover,
[data-testid="stSidebar"] [data-testid="stPageLink"] a[aria-current="page"] {background:rgba(255,255,255,0.12);}
[data-testid="stSidebar"] [data-testid="stPageLink"] a[aria-current="page"] span {color:#fff;}
[data-testid="stSidebar"] .stButton button[kind="secondary"] {background:rgba(255,255,255,0.07);
  border:1px solid rgba(255,255,255,0.16); box-shadow:none;}
[data-testid="stSidebar"] .stButton button[kind="secondary"] p {color:#fff;}
[data-testid="stSidebar"] .stButton button[kind="secondary"]:hover {background:rgba(255,255,255,0.16);
  border-color:#fff;}
[data-testid="stSidebar"] [data-testid="stExpander"] details {background:rgba(255,255,255,0.06);
  border-color:rgba(255,255,255,0.16) !important;}
[data-testid="stSidebar"] [data-testid="stExpander"] details * {color:#D5E0F5;}
[data-testid="stSidebar"] [data-baseweb="select"] > div {background:rgba(255,255,255,0.08); border-color:rgba(255,255,255,0.2);}
[data-testid="stSidebar"] .tg-chip {background:#fff;} [data-testid="stSidebar"] .tg-chip * {color:inherit;}
[data-testid="stSidebar"] .tg-ok {color:var(--ok) !important;} [data-testid="stSidebar"] .tg-neutral {color:var(--neutral) !important;}
[data-testid="stSidebar"] .tg-kb .t {color:#fff;}
[data-testid="stSidebar"] [data-testid="stAlert"] * {color:#5C3D00 !important;}
[data-testid="stSidebar"] [data-testid="stCheckbox"] label > div:first-child {background:rgba(255,255,255,0.35);}
/* Header: white card, navy title, sky accent band on the left */
.tg-hero {background:#fff; color:var(--ink); border:1px solid var(--line); border-left:10px solid var(--sky);
  border-radius:var(--radius);}
.tg-hero h1 {color:var(--navy) !important;}
.tg-hero h1 .tg-logo {background:var(--navy); color:#fff;}
.tg-hero p {color:var(--ink-2);} .tg-hero p b {color:var(--navy);}
.tg-hero .tg-pill {background:var(--tint); color:var(--navy); border-color:var(--sky);}
.tg-flow div.a2 {background:var(--navy);} .tg-flow div.a2 b {color:#fff;} .tg-flow div.a2 span {color:#C9D7F2;}
.tg-flow div.a2 em {background:#fff; color:var(--navy);}
[data-testid="stChatMessage"] {border-radius:var(--radius);}
</style>
""",
    },
    "sky": {
        "label": "C · Sky blue",
        "about": "Pale sky-blue page like the template's photo backdrop; big bold title with no box; extra-round cards.",
        "css": """
<style>
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap');
:root {--page:#DCEAF8; --panel:#F4F8FD; --tint:#E8F1FC; --line:#D3E1F1; --radius:24px;
  --shadow:0 2px 6px rgba(14,37,88,0.05), 0 12px 32px rgba(14,37,88,0.08);}
html, body, .stApp, .stMarkdown, input, textarea, button, label, [data-testid="stSidebar"],
h1, h2, h3, .tg-hero h1, .rv-title, .rv-big, .rv-tile .v, .rv-h, .tg-brand {
  font-family:'Plus Jakarta Sans', system-ui, sans-serif !important;}
.stApp {background:linear-gradient(180deg, #CFE2F7 0%, #E6F0FB 420px, #EEF4FB 100%);}
[data-testid="stSidebar"] {background:rgba(255,255,255,0.72); backdrop-filter:blur(8px); border-right:none;}
/* Header: no box, very large navy title like "Banking Reimagined" */
.tg-hero {background:transparent; box-shadow:none; padding:0.6rem 0 1rem 0; color:var(--ink);}
.tg-hero h1 {color:var(--navy) !important; font-size:2.9rem; line-height:1.05; letter-spacing:-0.035em;}
.tg-hero h1 .tg-logo {background:var(--navy); color:#fff; width:3.1rem; height:3.1rem;}
.tg-hero p {color:var(--ink-2); font-size:1.08rem;} .tg-hero p b {color:var(--navy);}
.tg-hero .tg-pill {background:#fff; color:var(--navy); border:none; box-shadow:var(--shadow);}
.tg-flow div {border:none;} .tg-flow div.a2 em, .tg-flow div em {background:var(--navy); color:#fff;}
[data-testid="stChatMessage"] {border:none; border-radius:var(--radius);}
[data-testid="stChatMessage"]:has(.tg-you) {background:var(--navy);}
[data-testid="stChatMessage"]:has(.tg-you) p {color:#fff;}
[data-testid="stChatMessage"]:has(.tg-you) [data-testid^="stChatMessageAvatar"] {background:rgba(255,255,255,0.15) !important; color:#fff;}
[data-testid="stBottomBlockContainer"], [data-testid="stBottom"] > div {background:#EEF4FB;}
.tg-verdict, .rv-card, .rv-tile, .tg-legend, [data-testid="stExpander"] details {border:none !important;}
.stButton button[kind="secondary"] {background:#fff;}
</style>
""",
    },
}
DEFAULT_DESIGN = "classic"


def current_design() -> str:
    """The picked option is kept in session state, so it stays the same on every page. A link can also
    choose one with ?design=navy (handy for screenshots and for showing the team)."""
    asked = st.query_params.get("design")
    if asked in DESIGNS and st.session_state.get("_design_from_url") != asked:
        st.session_state["design_choice"] = asked
        st.session_state["_design_from_url"] = asked
    return st.session_state.setdefault("design_choice", DEFAULT_DESIGN)


def design_picker() -> None:
    """Temporary: lets the team compare the options. Remove it once one is chosen (set DEFAULT_DESIGN)."""
    keys = list(DESIGNS)

    def remember():
        st.session_state["design_choice"] = st.session_state["_design_widget"]

    st.markdown("### Design option")
    st.radio("Design option", keys, index=keys.index(current_design()), key="_design_widget",
             format_func=lambda k: DESIGNS[k]["label"], on_change=remember, label_visibility="collapsed")
    st.caption(DESIGNS[current_design()]["about"])


def apply_base_theme() -> None:
    st.markdown(BASE_CSS + DESIGNS[current_design()]["css"], unsafe_allow_html=True)


def page_nav() -> None:
    """Brand mark and links between the pages (the automatic page list is hidden in
    .streamlit/config.toml, because it would label the main page with its file name, "app")."""
    st.markdown('<div class="tg-brand"><span aria-hidden="true">🛡️</span>TrustGuard</div>', unsafe_allow_html=True)
    try:
        st.page_link("app.py", label="Assistant", icon=":material/chat:")
        st.page_link("pages/reliability.py", label="How reliable is TrustGuard?", icon=":material/verified_user:")
    except StreamlitAPIException:  # page opened on its own (e.g. in tests), not through app.py
        pass
    design_picker()


def reliability_link() -> None:
    """Small link shown under each TrustGuard verdict: the test results are there when an employee is
    deciding whether to trust a warning, without putting statistics in the chat itself."""
    try:
        st.page_link("pages/reliability.py", label="How reliable is TrustGuard? See the test results",
                     icon=":material/insights:")
    except StreamlitAPIException:
        pass
