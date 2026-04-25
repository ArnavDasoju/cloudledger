"""CloudLedger — seven screens, one linear flow."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st

st.set_page_config(
    page_title="CloudLedger",
    page_icon="$",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Palette: cream, white, blue, dark-blue ──────────────────────────────────

st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600&display=swap');

.stApp {
    background: #F5F1E8 !important;
    font-family: 'Inter', system-ui, sans-serif;
}

#MainMenu {visibility: hidden;}
footer {visibility: hidden;}
header {visibility: hidden;}

/* Hide sidebar completely */
[data-testid="stSidebar"] { display: none !important; }
[data-testid="collapsedControl"] { display: none !important; }

.block-container {
    padding: 24px 32px 80px 32px;
    max-width: 960px;
}

h1, h2, h3, h4, h5 {
    font-weight: 500 !important;
    color: #1E3A8A !important;
}

p, li, span, div {
    color: #1E3A8A;
}

hr {
    border-color: rgba(30, 58, 138, 0.15) !important;
    margin: 20px 0 !important;
}

/* Buttons */
.stButton > button[kind="primary"],
.stButton > button[data-testid="stBaseButton-primary"] {
    background: #1E3A8A !important;
    color: #FFFFFF !important;
    border: none !important;
    border-radius: 8px !important;
    font-weight: 500 !important;
    font-size: 14px !important;
    padding: 10px 24px !important;
}
.stButton > button[kind="primary"]:hover,
.stButton > button[data-testid="stBaseButton-primary"]:hover {
    box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.3) !important;
}

.stButton > button[kind="secondary"],
.stButton > button[data-testid="stBaseButton-secondary"] {
    background: #FFFFFF !important;
    color: #1E3A8A !important;
    border: 1px solid #1E3A8A !important;
    border-radius: 8px !important;
    font-weight: 500 !important;
}
.stButton > button[kind="secondary"]:hover,
.stButton > button[data-testid="stBaseButton-secondary"]:hover {
    border: 2px solid #3B82F6 !important;
}

.stButton > button:disabled {
    opacity: 0.3 !important;
    cursor: not-allowed !important;
}

/* Download button */
.stDownloadButton > button {
    background: #1E3A8A !important;
    color: #FFFFFF !important;
    border: none !important;
    border-radius: 8px !important;
    font-weight: 500 !important;
}

/* File uploader */
section[data-testid="stFileUploader"] {
    border: 1px dashed rgba(30, 58, 138, 0.3) !important;
    border-radius: 10px;
    background: #FFFFFF;
}

/* Scrollbar */
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: rgba(30, 58, 138, 0.2); border-radius: 3px; }

/* Spinner */
.stSpinner > div { border-top-color: #3B82F6 !important; }
</style>
""",
    unsafe_allow_html=True,
)

# ── State ────────────────────────────────────────────────────────────────────

if "screen" not in st.session_state:
    st.session_state["screen"] = 0

SCREENS = [
    ("Upload", None),
    ("Bill Arrives", None),
    ("Ingestion", None),
    ("Variance", None),
    ("Root Causes", None),
    ("Close Packet", None),
    ("Engineering", None),
]

screen = st.session_state["screen"]
pipeline_done = st.session_state.get("pipeline_done", False)

# ── Tab strip (screens 1-6 only, after pipeline) ────────────────────────────

if pipeline_done and screen >= 1:
    tab_html = '<div style="display:flex;gap:4px;margin-bottom:24px">'
    for i in range(1, 7):
        label = SCREENS[i][0]
        if i == screen:
            border = "2px solid #3B82F6"
            weight = "500"
        else:
            border = "1px solid rgba(30, 58, 138, 0.2)"
            weight = "400"
        dot = '<span style="color:#3B82F6;margin-right:4px">&#8226;</span>' if i < screen else ""
        tab_html += (
            f'<div style="background:#FFFFFF;border:{border};border-radius:8px;'
            f'padding:6px 14px;font-size:12px;font-weight:{weight};color:#1E3A8A;cursor:default">'
            f'{dot}{i}. {label}</div>'
        )
    tab_html += "</div>"
    st.markdown(tab_html, unsafe_allow_html=True)

# ── Render active screen ────────────────────────────────────────────────────

if screen == 0:
    from app.screens.upload import render
    render()
elif screen == 1:
    from app.screens.bill_arrives import render
    render()
elif screen == 2:
    from app.screens.ingestion import render
    render()
elif screen == 3:
    from app.screens.variance_detected import render
    render()
elif screen == 4:
    from app.screens.root_causes import render
    render()
elif screen == 5:
    from app.screens.close_packet import render
    render()
elif screen == 6:
    from app.screens.engineering_view import render
    render()

# ── Back / Next buttons (screens 1-6 only) ──────────────────────────────────

if pipeline_done and screen >= 1:
    st.markdown("---")
    col_back, col_spacer, col_next = st.columns([1, 3, 1])

    with col_back:
        if screen > 1:
            if st.button("Back", use_container_width=True):
                st.session_state["screen"] = screen - 1
                st.rerun()
        else:
            st.button("Back", disabled=True, use_container_width=True)

    with col_next:
        if screen < 6:
            if st.button("Next", type="primary", use_container_width=True):
                st.session_state["screen"] = screen + 1
                st.rerun()
        else:
            st.button("Next", disabled=True, use_container_width=True, type="primary")
