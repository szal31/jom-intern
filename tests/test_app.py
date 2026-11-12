from pathlib import Path

from streamlit.testing.v1 import AppTest


def test_unconfigured_app_explains_instead_of_crashing(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)  # away from a real .streamlit/secrets.toml
    for name in ("GEMINI_API_KEY", "SUPABASE_URL", "SUPABASE_ANON_KEY", "SUPABASE_SERVICE_KEY", "ADMIN_EMAIL"):
        monkeypatch.delenv(name, raising=False)
    app = AppTest.from_file(str(Path(__file__).parent.parent / "app.py")).run(timeout=30)
    assert not app.exception
    assert "isn't set up yet" in app.error[0].value


def test_full_flow_with_fakes(monkeypatch):
    """Login, profile, pack and tracker against an in-memory stand-in for Supabase."""
    from tests.fake_db import install_fake_db

    store = install_fake_db(monkeypatch)
    app = AppTest.from_file("../app.py").run(timeout=30)
    assert not app.exception
    app.text_input[0].input("student@example.com")
    app.text_input[1].input("secret123")
    app.button[0].click().run(timeout=30)
    assert not app.exception
    assert "Welcome" in app.title[0].value

    app.checkbox[0].check().run(timeout=30)
    by_label(app.button, "Continue").click().run(timeout=30)
    assert app.title[0].value == "My profile"

    by_label(app.text_input, "Name").input("Test Student")
    by_label(app.text_input, "Start date (e.g. 15 March 2027)").input("15 March 2027")
    by_label(app.text_input, "End date (e.g. 4 July 2027)").input("4 July 2027")
    by_label(app.button, "Save profile").click().run(timeout=30)
    assert store["profiles"]["u1"]["data"]["contact"]["name"] == "Test Student"

    app.sidebar.radio[0].set_value("Internships").run(timeout=30)
    by_label(app.text_input, "Company").input("Acme Malaysia")
    by_label(app.text_input, "Role (exact title)").input("Data Analyst Intern")
    by_label(app.text_area, "Paste the job description").input("SQL and Power BI reporting.")
    [b for b in app.button if b.label == "Make my pack"][-1].click().run(timeout=60)
    assert not app.exception
    assert len(store["packs"]) == 1
    assert store["files"]["u1/p0/resume.pdf"].startswith(b"%PDF")

    app.sidebar.radio[0].set_value("Tracker").run(timeout=30)
    assert not app.exception
    assert app.get("download_button")


def by_label(widgets, label):
    return next(w for w in widgets if w.label == label)

