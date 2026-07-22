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


# Peer39 category palette — use in Plotly color_discrete_map / _sequence
PEER39_CATEGORY_COLORS = {
    "Valid": "#8cba51",     # suitability green
    "GIVT": "#d92d20",      # danger red
    "SIVT": "#E6AF2E",      # marketplace amber
    "Unknown": "#757575",   # platform grey
    "CTV": "#8cba51",
    "Tablet": "#3d85c6",
    "Mobile": "#9fc5e8",
    "Desktop": "#757575",
}
PEER39_SEQUENCE = ["#073763", "#3d85c6", "#8cba51", "#E6AF2E", "#9fc5e8", "#757575", "#B54F6F"]


def style_plotly(fig):
    """Apply the Peer39 look to a Plotly figure (white bg, brand font/colors).

    Usage:  st.plotly_chart(style_plotly(fig), use_container_width=True)
    """
    fig.update_layout(
        paper_bgcolor="#ffffff",
        plot_bgcolor="#ffffff",
        font=dict(family="Libre Franklin, sans-serif", color="#101828"),
        title_font=dict(family="Libre Franklin, sans-serif", color="#073763", size=18),
        legend=dict(bgcolor="rgba(0,0,0,0)"),
        colorway=PEER39_SEQUENCE,
        margin=dict(t=48, r=16, b=16, l=16),
    )
    fig.update_xaxes(gridcolor="#e4e7ec", zerolinecolor="#e4e7ec", linecolor="#d0d5dd")
    fig.update_yaxes(gridcolor="#e4e7ec", zerolinecolor="#e4e7ec", linecolor="#d0d5dd")
    return fig
