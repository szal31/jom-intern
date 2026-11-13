import copy

import pytest

from core.checker import lines_to_check
from core.llm import LLMError
from core.pack import build_pack, rewrite_paragraph
from core.render import letter_html, resume_html
from tests.test_checker import GOOD, JOB, PROFILE
from tests.test_pack import scripted


def test_build_pack_reports_each_step():
    steps = []
    build_pack(PROFILE, JOB, [], llm=scripted(copy.deepcopy(GOOD), {"untraceable": []}), step=steps.append)
    assert steps == ["Writing your resume and letter", "Checking every line against your profile"]


def test_build_pack_reports_the_retry():
    steps = []
    bad = copy.deepcopy(GOOD)
    bad["letter"].append("I admire Zenith.")
    build_pack(PROFILE, JOB, ["Zenith"], llm=scripted(bad, {"untraceable": []}, copy.deepcopy(GOOD), {"untraceable": []}), step=steps.append)
    assert "Fixing what the check found" in steps


def test_copied_bullet_is_not_flagged_but_reworded_one_is():
    pack = copy.deepcopy(GOOD)
    pack["resume"]["projects"][0]["bullets"] = ["Built a report on 12,000 rows, cutting errors by 15%", "Led quality control for every dashboard"]
    flagged = lines_to_check(pack, PROFILE)
    assert "Built a report on 12,000 rows, cutting errors by 15%" not in flagged
    assert "Led quality control for every dashboard" in flagged


def test_letter_sentences_with_facts_are_flagged_polite_ones_are_not():
    pack = copy.deepcopy(GOOD)
    pack["letter"] = ["Thank you for reading my application. I tutored 8 students. I use Power BI every week."]
    flagged = lines_to_check(pack, PROFILE)
    assert "I tutored 8 students." in flagged
    assert "I use Power BI every week." in flagged
    assert "Thank you for reading my application." not in flagged


def test_resume_preview_escapes_text_and_marks_lines():
    profile = copy.deepcopy(PROFILE)
    profile["contact"]["name"] = "Jane <b>Tan</b>"
    page = resume_html(profile, GOOD, marked={"Tutored 8 students"})
    assert "&lt;b&gt;" in page and "<b>Tan" not in page
    assert "<mark>Tutored 8 students</mark>" in page
    assert "REFERENCES" in page


def test_letter_preview_names_company_and_marks_sentences():
    page = letter_html(PROFILE, JOB, GOOD, marked={"My dashboard cut errors by 15%."})
    assert "Acme Malaysia" in page
    assert "<mark>My dashboard cut errors by 15%.</mark>" in page


def test_rewrite_paragraph_follows_the_instruction():
    llm = scripted({"paragraph": "A shorter paragraph."})
    assert rewrite_paragraph("A long paragraph.", PROFILE, JOB, "make it shorter", llm=llm) == "A shorter paragraph."
    assert "make it shorter" in llm.prompts[0] and "A long paragraph." in llm.prompts[0]


def test_rewrite_paragraph_rejects_an_empty_reply():
    with pytest.raises(LLMError):
        rewrite_paragraph("A paragraph.", PROFILE, JOB, "", llm=scripted({"paragraph": ""}))
