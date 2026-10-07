"""Password gate for the app. The password is never in the source: it comes from
Streamlit secrets (.streamlit/secrets.toml locally, the Secrets box on Streamlit
Cloud) or the LEAGUE_PASSWORD environment variable. With no password configured
the app stays locked."""
from __future__ import annotations

import hmac
import os

import streamlit as st


def configured_password() -> str | None:
    try:
        value = st.secrets.get("password")
    except Exception:  # no secrets file at all
        value = None
    return str(value) if value else os.environ.get("LEAGUE_PASSWORD") or None


def password_matches(entered: str, expected: str | None) -> bool:
    return bool(expected) and hmac.compare_digest(entered.encode(), expected.encode())


def require_login() -> None:
    """Show a password page and stop the script until the right password is entered."""
    if st.session_state.get("authenticated"):
        with st.sidebar:
            if st.button("Log out"):
                st.session_state["authenticated"] = False
                st.rerun()
        return

    expected = configured_password()
    st.title("Squash House League Manager")
    if not expected:
        st.error("No password is configured, so the app is locked. Set `password` in the app's secrets.")
        st.stop()
    with st.form("login"):
        entered = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Enter")
    if submitted:
        if password_matches(entered, expected):
            st.session_state["authenticated"] = True
            st.rerun()
        st.error("Wrong password.")
    st.stop()
