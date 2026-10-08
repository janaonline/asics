"""Shared look and feel for the app: Janaagraha logo, the ASICS header, and small styles."""

from pathlib import Path

import streamlit as st

LOGO = Path(__file__).parent / "assets" / "janaagraha-logo.svg"

CSS = """
<style>
:root { --ink: #110f0f; --muted: #6b645e; --line: #e6e1d9; --surface: #f6f4f0; }
.block-container { max-width: 1120px; padding-top: 2.2rem; }
/* ASICS brand bar, shown at the top of every page */
.asics-bar { display: flex; align-items: baseline; justify-content: space-between;
             flex-wrap: wrap; gap: .4rem 1rem; padding-bottom: .85rem;
             border-bottom: 1px solid var(--line); margin-bottom: 1.6rem; }
.asics-word { font-weight: 800; font-size: 1.7rem; letter-spacing: .34em; color: var(--ink);
              line-height: 1; }
.asics-tag { color: var(--muted); font-size: .82rem; letter-spacing: .04em; }
.asics-kicker { color: var(--muted); font-size: .78rem; font-weight: 600;
                letter-spacing: .12em; text-transform: uppercase; margin-bottom: .2rem; }
.asics-title { font-size: 1.9rem; font-weight: 700; color: var(--ink); line-height: 1.2;
               margin: 0 0 .35rem 0; }
.asics-lede { color: var(--muted); font-size: 1rem; margin: 0 0 1.4rem 0; max-width: 46rem; }
/* numbered step marker used on Home */
.asics-step { display: inline-flex; align-items: center; justify-content: center;
              width: 1.9rem; height: 1.9rem; border-radius: 50%; background: var(--ink);
              color: #fff; font-weight: 700; font-size: .95rem; margin-bottom: .6rem; }
.asics-card-title { font-weight: 700; font-size: 1.05rem; color: var(--ink);
                    margin-bottom: .3rem; }
.asics-card-text { color: var(--muted); font-size: .92rem; min-height: 4.6rem; }
.asics-footer { color: var(--muted); font-size: .75rem; line-height: 1.4; }
</style>
"""


def setup_page_chrome() -> None:
    """Logo in the sidebar and the shared styles. Call once per script run."""
    st.logo(str(LOGO), size="large")
    st.markdown(CSS, unsafe_allow_html=True)


VERTICAL = "Parastatal"  # the vertical being worked on; set by app.py


def header(title: str, lede: str = "", kicker: str = "") -> None:
    """The ASICS bar, then the page title and a one-line explanation."""
    st.markdown(
        '<div class="asics-bar"><span class="asics-word">ASICS</span>'
        '<span class="asics-tag">Annual Survey of India\'s City-Systems · '
        f"{VERTICAL} assessment</span></div>"
        + (f'<div class="asics-kicker">{kicker}</div>' if kicker else "")
        + f'<div class="asics-title">{title}</div>'
        + (f'<p class="asics-lede">{lede}</p>' if lede else ""),
        unsafe_allow_html=True,
    )


def step_card(number: int, title: str, text: str) -> None:
    st.markdown(
        f'<div class="asics-step">{number}</div>'
        f'<div class="asics-card-title">{title}</div>'
        f'<div class="asics-card-text">{text}</div>',
        unsafe_allow_html=True,
    )


def sidebar_footer() -> None:
    st.sidebar.markdown(
        f'<div class="asics-footer">ASICS · Janaagraha<br>{VERTICAL} assessment tool</div>',
        unsafe_allow_html=True,
    )
