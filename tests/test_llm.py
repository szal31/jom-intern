import pytest

from core.llm import LLMError, ask_json, gemini


def test_busy_model_falls_back_to_the_next(monkeypatch):
    monkeypatch.setenv("GEMINI_MODEL", "a, b")
    tried = []

    def call(model):
        tried.append(model)
        if model == "a":
            raise RuntimeError("503 UNAVAILABLE")
        return "{}"

    assert gemini("p", call=call) == "{}" and tried == ["a", "b"]


def test_other_errors_do_not_fall_back(monkeypatch):
    monkeypatch.setenv("GEMINI_MODEL", "a,b")
    with pytest.raises(RuntimeError):
        gemini("p", call=lambda m: (_ for _ in ()).throw(RuntimeError("400 bad key")))


def test_busy_message_is_plain():
    def busy(_):
        raise RuntimeError("503 UNAVAILABLE {'error': ...}")
    with pytest.raises(LLMError, match="busy") as info:
        ask_json("p", llm=busy)
    assert "{" not in str(info.value)
