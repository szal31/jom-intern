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
