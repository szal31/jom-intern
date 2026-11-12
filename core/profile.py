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


def clean_items(items) -> list[dict]:
    """Keep only well-formed entries: dicts with text fields and a list of text bullets."""
    cleaned = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        entry = {k: v if isinstance(v, str) else "" for k, v in item.items() if k != "bullets"}
        if "bullets" in item or "title" in item:
            entry["bullets"] = [b for b in item.get("bullets") or [] if isinstance(b, str) and b.strip()]
        cleaned.append(entry)
    return cleaned


def clean_lines(value) -> list[str]:
    if isinstance(value, str):
        return [value] if value.strip() else []
    return [v for v in value or [] if isinstance(v, str) and v.strip()]


def merge_profile(current: dict, extracted: dict) -> dict:
    """A re-uploaded resume updates what it contains; stories, window and filled fields stay."""
    merged = {**empty_profile(), **current}
    merged["contact"] = {**(current.get("contact") or {}), **{k: v for k, v in (extracted.get("contact") or {}).items() if v}}
    for section in PROFILE_SECTIONS:
        if section not in ("contact", "stories", "window") and extracted.get(section):
            merged[section] = extracted[section]
    return merged


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
        if section in ("education", "experience", "projects", "leadership", "stories"):
            profile[section] = clean_items(value)
        elif section in ("skills", "languages"):
            profile[section] = clean_lines(value)
        elif value and isinstance(value, type(profile[section])):
            profile[section] = value
    return profile
