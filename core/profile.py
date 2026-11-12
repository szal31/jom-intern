"""A student's profile: the only source of facts for their resume and letters."""
import json

from core.llm import ask_json

PROFILE_SECTIONS = ["contact", "summary", "education", "experience", "projects", "skills", "leadership", "languages", "stories", "window"]
DICT_SECTIONS = {"contact", "window"}
TEXT_SECTIONS = {"summary"}

SHAPE = {
    "contact": {"name": "", "location": "", "phone": "", "email": "", "linkedin": "", "github": ""},
    "summary": "",
    "education": [{"institution": "", "qualification": "", "dates": "", "grade": ""}],
    "experience": [{"title": "", "dates": "", "bullets": [""]}],
    "projects": [{"title": "", "dates": "", "tools": "", "bullets": [""]}],
    "skills": ["Label: item, item"],
    "leadership": [{"title": "", "dates": "", "bullets": [""]}],
    "languages": ["English (fluent)"],
    "stories": [{"situation": "", "action": "", "result": ""}],
    "window": {"start": "", "end": "", "weeks": "", "locations": ""},
}


def empty_profile() -> dict:
    return {s: {} if s in DICT_SECTIONS else "" if s in TEXT_SECTIONS else [] for s in PROFILE_SECTIONS}


def extract_profile(resume_text: str, llm=None) -> dict:
    profile = empty_profile()
    if not resume_text.strip():
        return profile
    prompt = (
        "Extract this resume into JSON with exactly these keys and shapes:\n"
        f"{json.dumps(SHAPE)}\n"
        "Copy wording and numbers exactly as written. Leave a field empty or a list empty when the resume "
        "doesn't say it. Never add anything that isn't in the resume. Leave 'stories' and 'window' empty.\n\n"
        f"RESUME:\n{resume_text}"
    )
    extracted = ask_json(prompt, llm=llm)
    for section in PROFILE_SECTIONS:
        value = extracted.get(section)
        if value and isinstance(value, type(profile[section])):
            profile[section] = value
    return profile
