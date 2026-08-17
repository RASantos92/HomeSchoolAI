"""Color theme picker for the student-facing app.

Swaps a handful of CSS colors (background, sidebar, headings, buttons, and
Streamlit's own chrome) rather than a full Streamlit theme, since that would
require a config.toml change and an app restart. Choice is shown as a labeled
sidebar dropdown and saved via services/theme.py so it's remembered next time
the app is opened.

Streamlit's header bar and BaseWeb widgets (selectboxes, their dropdown
popovers) follow the browser/OS light-dark preference on their own, separate
from the app body - if we only recolor .stApp we get a mismatched page (e.g.
a dark header over a light body). Every rule below is scoped explicitly so
the whole page - including the popover, which Streamlit renders in a portal
outside the sidebar's DOM subtree - matches the chosen palette.
"""
import streamlit as st

from services import theme as theme_service

THEMES = {
    "Dark": {"bg": "#161A23", "sidebar_bg": "#1E2430", "text": "#E8EAED", "accent": "#5B8DEF", "border": "#333B48"},
    "Light": {"bg": "#FFFFFF", "sidebar_bg": "#F0F2F6", "text": "#31333F", "accent": "#FF4B4B", "border": "#D5D7DE"},
    "Ocean": {"bg": "#0F2A2E", "sidebar_bg": "#153338", "text": "#E4F4F1", "accent": "#2FBFA6", "border": "#24484D"},
    "Forest": {"bg": "#1B2A1A", "sidebar_bg": "#223522", "text": "#E6F0E3", "accent": "#7CB342", "border": "#33472F"},
    "Sunset": {"bg": "#FFF3E0", "sidebar_bg": "#FFE0B2", "text": "#5D2E00", "accent": "#FB8C00", "border": "#F0C08A"},
}


def render_theme_picker():
    """Renders the "Color Theme" dropdown in the sidebar and applies it.
    Call once, near the top of main_page.py."""
    if "theme_name" not in st.session_state:
        st.session_state["theme_name"] = theme_service.load_theme()

    names = list(THEMES.keys())
    choice = st.sidebar.selectbox(
        "Color Theme",
        options=names,
        index=names.index(st.session_state["theme_name"]),
        key="theme_picker",
    )

    if choice != st.session_state["theme_name"]:
        st.session_state["theme_name"] = choice
        theme_service.save_theme(choice)

    _apply_theme(THEMES[choice])


def _apply_theme(colors):
    st.markdown(
        f"""
        <style>
        .stApp, [data-testid="stHeader"], [data-testid="stToolbar"] {{
            background-color: {colors['bg']} !important;
        }}
        .stApp {{
            color: {colors['text']} !important;
        }}
        .stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp h5, .stApp h6,
        .stApp p, .stApp li, .stApp .stMarkdown, section[data-testid="stSidebar"] label {{
            color: {colors['text']} !important;
        }}
        section[data-testid="stSidebar"] {{
            background-color: {colors['sidebar_bg']} !important;
        }}
        .stButton > button {{
            background-color: {colors['accent']} !important;
            color: #FFFFFF !important;
            border: none !important;
        }}
        div[data-baseweb="select"] > div {{
            background-color: {colors['sidebar_bg']} !important;
            color: {colors['text']} !important;
            border-color: {colors['border']} !important;
        }}
        div[data-baseweb="popover"] ul, div[data-baseweb="popover"] li {{
            background-color: {colors['sidebar_bg']} !important;
            color: {colors['text']} !important;
        }}
        .stApp a {{
            color: {colors['accent']} !important;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )
