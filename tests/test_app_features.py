import time

from streamlit.testing.v1 import AppTest

from core import remember
from core.profile import empty_profile
from tests.fake_db import install_fake_db
from tests.test_checker import PROFILE


def by_label(widgets, label):
    return next(w for w in widgets if w.label == label)


def start(monkeypatch, profile=None, cookie=None):
    store = install_fake_db(monkeypatch)
    if profile is not None:
        store["profiles"]["u1"] = {"data": profile, "consent_at": "now"}
    monkeypatch.setattr(remember, "read", lambda: cookie)
    monkeypatch.setattr(remember, "read_until", lambda: time.time() + 3600 if cookie else None)
    return AppTest.from_file("../app.py").run(timeout=30), store


def log_in(app, keep=False):
    app.text_input[0].input("student@example.com")
    app.text_input[1].input("secret123")
    if keep:
        app.checkbox[0].check()
    app.button[0].click().run(timeout=30)


def html_of(app):
    return " ".join(str(h.proto.body) for h in app.get("html"))


def test_remembered_session_logs_straight_back_in(monkeypatch):
    app, _ = start(monkeypatch, profile=dict(PROFILE, setup_done=True), cookie="remembered-token")
    assert not app.exception
    assert app.title[0].value == "My profile"


def test_stale_cookie_shows_the_login_page_and_clears_it(monkeypatch):
    app, _ = start(monkeypatch, cookie="expired-token")
    assert not app.exception
    assert any(b.label == "Log in" for b in app.button)
    assert "Max-Age=0" in html_of(app)


def test_keep_me_logged_in_writes_the_cookie_only_when_ticked(monkeypatch):
    app, _ = start(monkeypatch, profile=dict(PROFILE, setup_done=True))
    log_in(app)
    assert "jom_session=" not in html_of(app)
    app, _ = start(monkeypatch, profile=dict(PROFILE, setup_done=True))
    log_in(app, keep=True)
    assert "jom_session=fresh-token" in html_of(app)


def test_sign_up_needs_the_invite_code_when_one_is_set(monkeypatch):
    from core import db
    app, _ = start(monkeypatch)
    monkeypatch.setenv("INVITE_CODE", "JOM2027")
    calls = []
    monkeypatch.setattr(db, "sign_up", lambda _db, email, password: calls.append(email) or type("R", (), {"session": None})())
    app.run(timeout=30)
    app.tabs[1].text_input[0].input("friend@example.com")
    app.tabs[1].text_input[1].input("secret123")
    app.tabs[1].text_input[2].input("wrong")
    by_label(app.button, "Create account").click().run(timeout=30)
    assert calls == [] and any("invite code" in e.value for e in app.error)
    app.tabs[1].text_input[2].input("JOM2027")
    by_label(app.button, "Create account").click().run(timeout=30)
    assert calls == ["friend@example.com"]


def test_nav_is_at_the_top_not_in_a_sidebar(monkeypatch):
    app, _ = start(monkeypatch, profile=dict(PROFILE, setup_done=True))
    log_in(app)
    assert not app.sidebar.radio
    assert app.radio(key="page").value == "My profile"
    assert any(b.label == "Log out" for b in app.button)


def test_guided_setup_walks_the_steps(monkeypatch):
    app, store = start(monkeypatch, profile=empty_profile())
    log_in(app)
    assert "Step 1 of 4" in app.get("progress")[0].proto.text
    by_label(app.button, "Next").click().run(timeout=30)
    assert "Step 2 of 4" in app.get("progress")[0].proto.text
    by_label(app.text_input, "Name").input("Jane Tan")
    by_label(app.button, "Next").click().run(timeout=30)
    assert store["profiles"]["u1"]["data"]["contact"]["name"] == "Jane Tan"
    by_label(app.button, "Next").click().run(timeout=30)
    by_label(app.button, "Finish").click().run(timeout=30)
    assert store["profiles"]["u1"]["data"]["setup_done"] is True
    assert app.title[0].value == "My profile"


def test_making_a_pack_shows_progress_then_preview_and_rewrite(monkeypatch):
    app, store = start(monkeypatch, profile=dict(PROFILE, setup_done=True))
    log_in(app)
    app.radio(key="page").set_value("Internships").run(timeout=30)
    assert not app.tabs  # nothing recommended: the paste form shows straight away
    by_label(app.text_input, "Company").input("Acme Malaysia")
    by_label(app.text_input, "Role (exact title)").input("Data Analyst Intern")
    by_label(app.text_area, "Paste the job description").input("SQL reporting.")
    [b for b in app.button if b.label == "Make my pack"][-1].click().run(timeout=60)
    assert not app.exception
    assert app.status[0].label in ("Your pack is ready", "Saved, with things to fix")

    app.radio(key="page").set_value("My packs").run(timeout=30)
    app.toggle(key="openp0").set_value(True).run(timeout=30)
    assert not app.exception
    assert html_of(app).count("jom-sheet") >= 2
    app.button(key="rw0p00").click().run(timeout=30)
    assert not app.exception
    assert app.text_area(key="lp0p01").value.startswith("I built a sales report in Power BI")


def test_recommended_tab_shows_when_there_are_jobs(monkeypatch):
    app, _ = start(monkeypatch, profile=dict(PROFILE, setup_done=True))
    job = {"company": "Acme", "role": "Data Intern", "link": "", "location": "Kuala Lumpur", "posting_text": "SQL.",
           "date_found": "2026-11-10", "company_type": "1 MNC"}
    monkeypatch.setattr("core.db.load_job_list", lambda _db: [job])
    log_in(app)
    app.radio(key="page").set_value("Internships").run(timeout=30)
    assert [t.label for t in app.tabs] == ["Recommended", "Paste my own"]


def test_repeat_signup_says_the_email_was_already_sent(monkeypatch):
    """A second click while the first sign-up is still sending hits Supabase's 60-second limit; the account and email already exist."""
    from core import db
    from core.db import friendly_error
    error = Exception("For security purposes, you can only request this after 47 seconds.")
    assert "already sent" in friendly_error(error)
    assert "hour" in friendly_error(Exception("email rate limit exceeded"))
    app, _ = start(monkeypatch)
    monkeypatch.setattr(db, "sign_up", lambda _db, email, password: (_ for _ in ()).throw(error))
    app.tabs[1].text_input[0].input("friend@example.com")
    app.tabs[1].text_input[1].input("secret123")
    by_label(app.button, "Create account").click().run(timeout=30)
    assert any("already sent" in e.value for e in app.error)
