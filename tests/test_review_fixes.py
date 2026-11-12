import copy
from types import SimpleNamespace

from streamlit.testing.v1 import AppTest

from core import db
from core.pack import build_pack, clean_pack
from core.profile import empty_profile, merge_profile
from tests.fake_db import install_fake_db
from tests.test_checker import GOOD, JOB, PROFILE
from tests.test_pack import scripted


def by_label(widgets, label):
    return next(w for w in widgets if w.label == label)


def logged_in_app(monkeypatch, profile=None):
    store = install_fake_db(monkeypatch)
    store["profiles"]["u1"] = {"data": profile or empty_profile(), "consent_at": "now"}
    app = AppTest.from_file("../app.py").run(timeout=30)
    app.text_input[0].input("student@example.com")
    app.text_input[1].input("secret123")
    app.button[0].click().run(timeout=30)
    return app, store


def test_add_story_shows_inputs(monkeypatch):
    app, _ = logged_in_app(monkeypatch)
    by_label(app.button, "Add story").click().run(timeout=30)
    assert any(w.label == "Situation" for w in app.text_input)


def test_extracted_contact_shows_after_profile_changes(monkeypatch):
    app, store = logged_in_app(monkeypatch)
    profile = empty_profile()
    profile["contact"] = {"name": "From Resume"}
    store["profiles"]["u1"]["data"] = profile
    app.session_state["profile_version"] = app.session_state["profile_version"] + 1
    app.session_state["profile"] = profile
    app.run(timeout=30)
    assert by_label(app.text_input, "Name").value == "From Resume"


def test_reupload_keeps_stories_window_and_edits():
    current = copy.deepcopy(PROFILE)
    current["stories"] = [{"situation": "Budget", "action": "Showed numbers", "result": "Stayed in budget"}]
    extracted = empty_profile()
    extracted["contact"] = {"name": "Jane Tan", "email": "new@example.com"}
    extracted["projects"] = [{"title": "New Project", "dates": "2026", "tools": "", "bullets": ["x"]}]
    merged = merge_profile(current, extracted)
    assert merged["stories"] == current["stories"]
    assert merged["window"] == current["window"]
    assert merged["contact"]["phone"] == "012-345 6789"
    assert merged["contact"]["email"] == "new@example.com"
    assert merged["projects"][0]["title"] == "New Project"
    assert merged["experience"] == current["experience"]


def test_flagged_line_with_different_punctuation_is_still_removed():
    pack = copy.deepcopy(GOOD)
    pack["letter"].append("I led a team of 5 analysts.")
    llm = scripted(pack, {"untraceable": ["i led a team of 5 analysts"]})
    result, problems = build_pack(PROFILE, JOB, [], llm=llm)
    assert not any("led a team" in p for p in result["letter"])


def test_flagged_line_that_cannot_be_found_is_reported():
    flag = {"untraceable": ["Something not in the pack at all"]}
    llm = scripted(copy.deepcopy(GOOD), flag, copy.deepcopy(GOOD), flag)
    _, problems = build_pack(PROFILE, JOB, [], llm=llm)
    assert any("couldn't be removed" in p for p in problems)


def test_clean_pack_fixes_bad_shapes():
    raw = {"resume": {"summary": 5, "skills": "Python, SQL", "experience": ["just a string"], "projects": [{"title": "P", "bullets": None}]},
           "letter": "One paragraph only."}
    pack = clean_pack(raw)
    assert pack["letter"] == ["One paragraph only."]
    assert pack["resume"]["skills"] == ["Python, SQL"]
    assert pack["resume"]["experience"] == []
    assert pack["resume"]["projects"][0]["bullets"] == []
    assert pack["resume"]["summary"] == ""


def test_all_files_lists_the_whole_user_folder():
    folders = {"u1": [{"name": "p0"}, {"name": "orphan"}], "u1/p0": [{"name": "resume.pdf"}], "u1/orphan": [{"name": "letter.pdf"}]}
    storage = SimpleNamespace(from_=lambda bucket: SimpleNamespace(list=lambda path: folders.get(path, [])))
    assert sorted(db.all_files(SimpleNamespace(storage=storage), "u1")) == ["u1/orphan/letter.pdf", "u1/p0/resume.pdf"]


def test_my_packs_downloads_nothing_until_asked(monkeypatch):
    app, store = logged_in_app(monkeypatch)
    calls = []
    store["packs"] = [{"id": "p0", "company": "Acme", "role": "Intern", "status": "Ready", "notes": "", "created_at": "2026-11-12", "files": {"resume.pdf": "u1/p0/resume.pdf"}}]
    store["files"]["u1/p0/resume.pdf"] = b"%PDF"
    monkeypatch.setattr(db, "download", lambda _db, path: calls.append(path) or store["files"][path])
    app.sidebar.radio[0].set_value("My packs").run(timeout=30)
    assert calls == []


def test_admin_email_match_ignores_case(monkeypatch):
    app, _ = logged_in_app(monkeypatch)
    monkeypatch.setenv("ADMIN_EMAIL", "Student@Example.com")
    app.run(timeout=30)
    assert "Admin" in app.sidebar.radio[0].options


def test_remove_story_keeps_the_right_one(monkeypatch):
    profile = empty_profile()
    profile["stories"] = [{"situation": "First", "action": "", "result": ""}, {"situation": "Second", "action": "", "result": ""}]
    app, _ = logged_in_app(monkeypatch, profile)
    [b for b in app.button if b.label == "Remove"][0].click().run(timeout=30)
    assert [w.value for w in app.text_input if w.label == "Situation"] == ["Second"]
