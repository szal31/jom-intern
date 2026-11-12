"""The one place the app talks to a model, so the model can be swapped later."""
import json
import os
import re


class LLMError(Exception):
    """The model failed, hit its quota, or returned something unusable."""


BUSY = ("503", "504", "429", "UNAVAILABLE", "DEADLINE_EXCEEDED", "RESOURCE_EXHAUSTED")


def gemini(prompt: str, call=None) -> str:
    """GEMINI_MODEL may list backups, comma separated; a busy model falls through to the next."""
    models = [m.strip() for m in os.environ.get("GEMINI_MODEL", "gemini-3.5-flash,gemini-3.5-flash-lite").split(",") if m.strip()]
    if call is None:
        from google import genai

        client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
        call = lambda model: client.models.generate_content(model=model, contents=prompt, config={"response_mime_type": "application/json"}).text
    for i, model in enumerate(models):
        try:
            return call(model) or ""
        except Exception as error:
            if i == len(models) - 1 or not any(code in str(error) for code in BUSY):
                raise
    return ""


def ask_json(prompt: str, llm=None) -> dict:
    llm = llm or gemini
    try:
        reply = llm(prompt)
    except Exception as error:  # quota, network, auth: the student only needs a plain message
        if any(code in str(error) for code in BUSY):
            raise LLMError("Gemini is busy or out of free requests right now. Please try again in a few minutes.") from error
        raise LLMError("The AI service didn't respond. Please try again in a minute.") from error
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", reply.strip())
    try:
        result = json.loads(text)
    except json.JSONDecodeError as error:
        raise LLMError("The AI service returned something unreadable. Please try again.") from error
    if not isinstance(result, dict):
        raise LLMError("The AI service returned something unreadable. Please try again.")
    return result
