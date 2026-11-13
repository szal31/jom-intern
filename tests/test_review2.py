"""Fixes from the whole-system review: checker gaps, invite code, opt-in remembered login."""
import copy
import time

from core.checker import check_pack
from core.pack import build_pack
from tests.test_checker import GOOD, JOB, PROFILE
from tests.test_pack import scripted


def test_invented_dates_and_titles_are_replaced_by_the_profiles_own():
    pack = copy.deepcopy(GOOD)
    pack["resume"]["experience"][0]["dates"] = "Jan 2019 - Dec 2025"
    pack["resume"]["projects"][0]["title"] = "sales dashboard"
    pack["resume"]["projects"].append({"title": "Moon Landing Simulator", "dates": "2024", "bullets": ["Landed it."]})
    result, _ = build_pack(PROFILE, JOB, [], llm=scripted(pack, {"untraceable": []}))
    assert result["resume"]["experience"][0]["dates"] == "2024 to 2025"
    assert result["resume"]["projects"][0]["title"] == "Sales Dashboard"
    assert all(p["title"] != "Moon Landing Simulator" for p in result["resume"]["projects"])


def test_empty_letter_and_bulletless_entry_are_problems():
    pack = copy.deepcopy(GOOD)
    pack["letter"] = []
    pack["resume"]["experience"][0]["bullets"] = []
    problems = check_pack(pack, PROFILE, JOB, [])
    assert any("letter is empty" in p for p in problems)
    assert any("no bullets" in p for p in problems)


def test_students_own_employer_is_never_flagged():
    profile = copy.deepcopy(PROFILE)
    profile["experience"][0]["title"] = "Part-time Tutor, Maybank"
    pack = copy.deepcopy(GOOD)
    pack["resume"]["experience"][0]["title"] = "Part-time Tutor, Maybank"
    assert check_pack(pack, profile, JOB, ["Maybank"]) == []


def test_skill_must_match_a_whole_word():
    profile = copy.deepcopy(PROFILE)
    profile["skills"] = ["Programming: JavaScript"]
    pack = copy.deepcopy(GOOD)
    pack["resume"]["skills"] = ["Programming: Java"]
    assert any("Java" in p for p in check_pack(pack, profile, JOB, []))


def test_job_ad_numbers_are_not_allowed_in_resume_bullets():
    job = dict(JOB, posting_text="Manage 50 client accounts.")
    pack = copy.deepcopy(GOOD)
    pack["resume"]["experience"][0]["bullets"] = ["Tutored 8 students and handled 50 accounts"]
    assert any("50" in p for p in check_pack(pack, PROFILE, job, []))
    letter_ok = copy.deepcopy(GOOD)
    letter_ok["letter"].append("Your team manages 50 client accounts.")
    assert not any("50" in p for p in check_pack(letter_ok, PROFILE, job, []))


def test_remembered_login_expires_seven_days_after_login(monkeypatch):
    from core import remember
    now = time.time()
    monkeypatch.setattr(remember, "_cookies", lambda: {"jom_session": "abcdefgh123", "jom_session_until": str(int(now + 3600))})
    assert remember.read() == "abcdefgh123"
    monkeypatch.setattr(remember, "_cookies", lambda: {"jom_session": "abcdefgh123", "jom_session_until": str(int(now - 1))})
    assert remember.read() is None
