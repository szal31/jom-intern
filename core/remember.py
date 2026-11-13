"""Keep a student logged in across page reloads, only when they tick "Keep me logged in", for 7 days from login."""
import re
import time

import streamlit as st

COOKIE, UNTIL = "jom_session", "jom_session_until"
WEEK = 7 * 24 * 3600
TOKEN = re.compile(r"^[A-Za-z0-9._-]{8,512}$")


def _cookies():
    return st.context.cookies


def read_until() -> float | None:
    """When the remembered login runs out (seconds since 1970), or None if there is none."""
    try:
        return float(_cookies().get(UNTIL))
    except (TypeError, ValueError):
        return None


def read() -> str | None:
    token, until = _cookies().get(COOKIE), read_until()
    if isinstance(token, str) and TOKEN.match(token) and until and until > time.time():
        return token
    return None


def _set(name: str, value: str, max_age: int):
    # shortcut: the cookie is readable by page scripts (Streamlit can't set HttpOnly cookies); move to a server-set cookie if the app ever leaves the pilot
    st.html(f"<script>document.cookie = '{name}={value}; Max-Age={max_age}; Path=/; SameSite=Strict' + (location.protocol === 'https:' ? '; Secure' : '');</script>",
            unsafe_allow_javascript=True)


def write(token: str, until: float):
    """Save the latest refresh token; the expiry stays fixed at 7 days from login however often the token rotates."""
    max_age = int(until - time.time())
    if TOKEN.match(token) and max_age > 0:
        _set(COOKIE, token, max_age)
        _set(UNTIL, str(int(until)), max_age)


def clear():
    _set(COOKIE, "", 0)
    _set(UNTIL, "", 0)
