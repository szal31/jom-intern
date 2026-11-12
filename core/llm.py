"""The one place the app talks to a model, so the model can be swapped later."""
import json
import os
import re


class LLMError(Exception):
    """The model failed, hit its quota, or returned something unusable."""


def gemini(prompt: str) -> str:
    from google import genai

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    response = client.models.generate_content(
        model=os.environ.get("GEMINI_MODEL", "gemini-3.5-flash"),
        contents=prompt,
        config={"response_mime_type": "application/json"},
    )
    return response.text or ""


def ask_json(prompt: str, llm=None) -> dict:
    llm = llm or gemini
    try:
        reply = llm(prompt)
    except Exception as error:  # quota, network, auth: the student only needs a plain message
        raise LLMError(f"The AI service didn't respond: {error}") from error
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", reply.strip())
    try:
        result = json.loads(text)
    except json.JSONDecodeError as error:
        raise LLMError("The AI service returned something unreadable. Please try again.") from error
    if not isinstance(result, dict):
        raise LLMError("The AI service returned something unreadable. Please try again.")
    return result
