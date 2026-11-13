import json

import pytest

from core.llm import LLMError, ask_json
from core.profile import PROFILE_SECTIONS, empty_profile, extract_profile


def fake(reply):
    calls = []

    def llm(prompt):
        calls.append(prompt)
        return reply

    llm.calls = calls
    return llm


def test_ask_json_parses_fenced_json():
    assert ask_json("p", llm=fake('```json\n{"a": 1}\n```')) == {"a": 1}


def test_ask_json_raises_on_bad_json():
    with pytest.raises(LLMError):
        ask_json("p", llm=fake("not json"))


def test_ask_json_wraps_model_errors():
    def broken(prompt):
        raise RuntimeError("429 quota exceeded")

    with pytest.raises(LLMError):
        ask_json("p", llm=broken)


def test_extract_profile_has_every_section():
    reply = json.dumps({"contact": {"name": "Jane Tan"}, "skills": ["Python"]})
    profile = extract_profile("Jane Tan resume text", llm=fake(reply))
    assert set(PROFILE_SECTIONS) <= set(profile)
    assert profile["contact"]["name"] == "Jane Tan"
    assert profile["projects"] == []


def test_empty_resume_text_skips_the_model():
    llm = fake("{}")
    assert extract_profile("   ", llm=llm) == empty_profile()
    assert llm.calls == []


def test_short_university_names_are_written_in_full():
    from core.profile import full_institution
    assert full_institution("UiTM") == "Universiti Teknologi MARA (UiTM)"
    assert full_institution("UITM Shah Alam") == "Universiti Teknologi MARA (UiTM) Shah Alam"
    assert full_institution("UKM, Bangi") == "Universiti Kebangsaan Malaysia (UKM), Bangi"
    assert full_institution("Universiti Teknologi MARA (UiTM), Tapah") == "Universiti Teknologi MARA (UiTM), Tapah"
    assert full_institution("UMS") == "Universiti Malaysia Sabah (UMS)"
    assert full_institution("Sunway University") == "Sunway University"


def test_full_names_reach_the_resume_and_the_model():
    import copy
    from core.pack import build_pack
    from core.render import resume_html
    from tests.test_checker import GOOD, JOB, PROFILE
    from tests.test_pack import scripted
    profile = copy.deepcopy(PROFILE)
    profile["education"][0]["institution"] = "UPM"
    assert "Universiti Putra Malaysia (UPM)" in resume_html(profile, GOOD)
    llm = scripted(copy.deepcopy(GOOD), {"untraceable": []})
    build_pack(profile, JOB, [], llm=llm)
    assert "Universiti Putra Malaysia (UPM)" in llm.prompts[0]
