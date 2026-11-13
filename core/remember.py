"""Keep a student logged in across page reloads with a browser cookie holding their Supabase refresh token."""
import re

import streamlit as st

COOKIE = "jom_session"
WEEK = 7 * 24 * 3600
TOKEN = re.compile(r"^[A-Za-z0-9._-]{8,512}$")


def read() -> str | None:
    token = st.context.cookies.get(COOKIE)
    return token if isinstance(token, str) and TOKEN.match(token) else None


def _set(value: str, max_age: int):
    # shortcut: the cookie is readable by page scripts (Streamlit can't set HttpOnly cookies); move to a server-set cookie if the app ever leaves the pilot
    st.html(f"<script>document.cookie = '{COOKIE}={value}; Max-Age={max_age}; Path=/; SameSite=Strict' + (location.protocol === 'https:' ? '; Secure' : '');</script>",
            unsafe_allow_javascript=True)


def write(token: str):
    if TOKEN.match(token):
        _set(token, WEEK)


def clear():
    _set("", 0)
