"""
peer39_style.py — Peer39 branding helpers for Streamlit (>= 1.50).

Usage in your app (e.g. app_v2.py), right after st.set_page_config(...):

    from peer39_style import apply_peer39_theme, peer39_header

    apply_peer39_theme()          # inject CSS overrides
    peer39_header()               # optional branded top bar
    # or use Streamlit's native persistent logo:
    #   st.logo("peer39_assets/peer39-logo.png", size="large")

The color palette in .streamlit/config.toml handles base theming;
this module injects peer39_theme.css for full component restyling.
"""

import base64
import os
import streamlit as st

_HERE = os.path.dirname(os.path.abspath(__file__))
_CSS_PATH = os.path.join(_HERE, "peer39_theme.css")
_LOGO_PATH = os.path.join(_HERE, "peer39_assets", "peer39-logo.png")
_LOGO_WHITE_PATH = os.path.join(_HERE, "peer39_assets", "peer39-logo-white.png")


def apply_peer39_theme(css_path: str = _CSS_PATH) -> None:
    """Inject the Peer39 CSS override sheet into the current page."""
    try:
        with open(css_path, "r", encoding="utf-8") as f:
            css = f.read()
    except FileNotFoundError:
        st.warning(f"Peer39 theme CSS not found at {css_path}")
        return
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)


def _img_data_uri(path: str) -> str | None:
    try:
        with open(path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("ascii")
        return f"data:image/png;base64,{b64}"
    except FileNotFoundError:
        return None


def peer39_header(title: str = "Contextual Intelligence", logo_path: str = _LOGO_PATH) -> None:
    """Render a Peer39-branded top bar (logo + kicker) at the top of the page."""
    uri = _img_data_uri(logo_path)
    if uri is None:
        return
    st.markdown(
        f"""
        <div class="p39-appbar">
            <img src="{uri}" alt="Peer39" />
            <span class="p39-appbar-title">{title}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def sidebar_logo(logo_path: str = _LOGO_WHITE_PATH) -> None:
    """Render the white Peer39 wordmark at the top of the (navy) sidebar."""
    uri = _img_data_uri(logo_path)
    if uri is None:
        return
    st.sidebar.markdown(
        f'<div style="padding:4px 0 12px;"><img src="{uri}" style="height:30px;" alt="Peer39"/></div>',
        unsafe_allow_html=True,
    )
