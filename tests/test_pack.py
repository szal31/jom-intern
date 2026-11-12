import copy
import json

import pytest

from core.llm import LLMError
from core.pack import build_pack, trim_to_one_page
from tests.test_checker import GOOD, JOB, PROFILE


def scripted(*replies):
    queue = list(replies)
    prompts = []

    def llm(prompt):
        prompts.append(prompt)
        reply = queue.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply if isinstance(reply, str) else json.dumps(reply)

    llm.prompts = prompts
    return llm


def test_untraceable_sentence_is_removed():
    pack = copy.deepcopy(GOOD)
    pack["letter"].append("I led a team of 5 analysts at Acme.")
    llm = scripted(pack, {"untraceable": ["I led a team of 5 analysts at Acme."]})
    result, problems = build_pack(PROFILE, JOB, [], llm=llm)
    assert problems == []
    assert not any("led a team" in p for p in result["letter"])


def test_checker_problem_triggers_one_retry_then_reports():
    bad = copy.deepcopy(GOOD)
    bad["letter"].append("I improved sales by 87%.")
    llm = scripted(bad, {"untraceable": []}, bad, {"untraceable": []})
    result, problems = build_pack(PROFILE, JOB, [], llm=llm)
    assert len(llm.prompts) == 4
    assert "87%" in llm.prompts[2]
    assert any("87" in p for p in problems)


def test_model_failure_propagates():
    with pytest.raises(LLMError):
        build_pack(PROFILE, JOB, [], llm=scripted(RuntimeError("429 quota")))


def test_trim_drops_leadership_then_projects():
    pack = copy.deepcopy(GOOD)
    pack["resume"]["leadership"] = [{"title": "Exco", "dates": "2024", "bullets": ["a", "b"]}]
    pages = iter([3, 2, 1])
    trimmed = trim_to_one_page(pack, lambda p: next(pages))
    assert trimmed["resume"]["leadership"][0]["bullets"] == [] or trimmed["resume"]["leadership"] == []
