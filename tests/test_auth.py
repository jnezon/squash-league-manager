from streamlit.testing.v1 import AppTest

from auth import password_matches


def test_password_matches():
    assert password_matches("secret", "secret")
    assert not password_matches("Secret", "secret")
    assert not password_matches("", "secret")
    assert not password_matches("anything", None)
    assert not password_matches("", None)


def _login_app(secret):
    script = """
import streamlit as st
from auth import require_login
require_login()
st.write("SECRET CONTENT")
"""
    at = AppTest.from_string(script, default_timeout=20)
    at.secrets["password"] = secret or ""  # override any real local secrets file
    return at.run()


def test_gate_blocks_until_correct_password():
    at = _login_app("hunter2")
    assert not [m for m in at.markdown if "SECRET CONTENT" in m.value]
    at.text_input[0].input("wrong"); at.button[0].click().run()
    assert [e.value for e in at.error] == ["Wrong password."]
    assert not [m for m in at.markdown if "SECRET CONTENT" in m.value]
    at.text_input[0].input("hunter2"); at.button[0].click().run()
    assert [m for m in at.markdown if "SECRET CONTENT" in m.value]


def test_gate_fails_closed_without_a_password(monkeypatch):
    monkeypatch.delenv("LEAGUE_PASSWORD", raising=False)
    at = _login_app(None)
    assert at.error and "locked" in at.error[0].value
    assert not [m for m in at.markdown if "SECRET CONTENT" in m.value]
