"""Write a tailored resume and cover letter from a student's own profile."""
import json
import re

from core.checker import check_pack
from core.llm import LLMError, ask_json
from core.profile import clean_items, clean_lines, with_full_institutions

STYLE = (
    "Write in plain, formal English. No adverbs, no em dashes, active voice with the student as the subject, "
    "specific facts instead of praise. Never mention certificates."
)


def write_pack(profile: dict, job: dict, llm=None, problems=None) -> dict:
    fix = f"\nA previous draft had these problems; avoid them:\n- " + "\n- ".join(problems) if problems else ""
    prompt = (
        "You tailor an internship application. Use ONLY facts from the PROFILE. Never invent employers, skills, "
        "numbers, dates or achievements. You may select, reorder and lightly reword the profile's own lines.\n"
        f"{STYLE}\n"
        "Return JSON: {\"resume\": {\"summary\": str, \"skills\": [\"Label: items\"], \"experience\": [{\"title\", \"dates\", \"bullets\"}], "
        "\"projects\": [3 or 4 most relevant, {\"title\", \"dates\", \"bullets\"}], \"leadership\": [{\"title\", \"dates\", \"bullets\"}]}, "
        "\"letter\": [5 paragraphs: the exact role and company plus who the student is and their availability window; "
        "skills tied to what this team does; soft skills from the student's stories; why this company; thanks and interview request]}.\n"
        "Titles must be copied exactly from the profile. The letter must name the company and the exact role. "
        "The resume summary must not mention citizenship or availability dates: the app adds availability itself."
        f"{fix}\n\nPROFILE:\n{json.dumps(profile, ensure_ascii=False)}\n\nJOB:\n{json.dumps(job, ensure_ascii=False)}"
    )
    return clean_pack(ask_json(prompt, llm=llm))


def clean_pack(raw: dict) -> dict:
    """Coerce the model's reply into the pack shape, dropping anything malformed."""
    resume = raw.get("resume") if isinstance(raw.get("resume"), dict) else {}
    summary = resume.get("summary")
    return {
        "resume": {
            "summary": summary if isinstance(summary, str) else "",
            "skills": clean_lines(resume.get("skills")),
            **{section: [i for i in clean_items(resume.get(section)) if i.get("title")] for section in ("experience", "projects", "leadership")},
        },
        "letter": clean_lines(raw.get("letter")),
    }


def verify_pack(pack: dict, profile: dict, llm=None) -> list[str]:
    prompt = (
        "Check every resume bullet, the summary and every letter sentence against the PROFILE. "
        "Return JSON {\"untraceable\": [exact sentences or bullets that state a fact not supported by the profile]}. "
        "Opinions and polite phrases are fine.\n\n"
        f"PROFILE:\n{json.dumps(profile, ensure_ascii=False)}\n\nPACK:\n{json.dumps(pack, ensure_ascii=False)}"
    )
    return [s for s in ask_json(prompt, llm=llm).get("untraceable", []) if isinstance(s, str) and s.strip()]


def _norm(text: str) -> str:
    return " ".join(re.sub(r"[^\w\s]", " ", text).casefold().split())


def _drop(pack: dict, flagged: list[str]) -> tuple[dict, list[str]]:
    """Remove flagged lines, matching loosely; return the flags that matched nothing."""
    targets = {_norm(f): f for f in flagged if _norm(f)}
    found = set()

    def hit(text):
        match = next((t for t in targets if t == _norm(text) or (len(t) > 15 and t in _norm(text))), None)
        if match:
            found.add(match)
        return match

    resume = pack["resume"]
    for section in ("experience", "projects", "leadership"):
        for item in resume.get(section, []):
            item["bullets"] = [b for b in item.get("bullets", []) if not hit(b)]
    if resume.get("summary") and hit(resume["summary"]):
        resume["summary"] = ""
    letter = []
    for paragraph in pack["letter"]:
        kept = " ".join(s for s in re.split(r"(?<=[.!?])\s+", paragraph) if not hit(s))
        if kept.strip():
            letter.append(kept)
    pack["letter"] = letter
    return pack, [targets[t] for t in targets if t not in found]


def build_pack(profile: dict, job: dict, other_companies: list[str], llm=None, step=lambda message: None) -> tuple[dict, list[str]]:
    """Write, verify and check, retrying once with the problems; `step` hears each stage for a progress display."""
    profile = with_full_institutions(profile)  # so the letter names "Universiti Teknologi MARA (UiTM)", not just "UiTM"
    problems = None
    for attempt in range(2):
        step("Writing your resume and letter" if attempt == 0 else "Fixing what the check found")
        pack = write_pack(profile, job, llm=llm, problems=problems)
        step("Checking every line against your profile")
        pack, missed = _drop(pack, verify_pack(pack, profile, llm=llm))
        problems = check_pack(pack, profile, job, other_companies) + [f"A flagged line couldn't be removed: {m}" for m in missed]
        if not problems:
            return pack, []
    return pack, problems


def rewrite_paragraph(paragraph: str, profile: dict, job: dict, how: str, llm=None) -> str:
    """Rewrite one letter paragraph as the student asks, still only from their profile."""
    profile = with_full_institutions(profile)
    prompt = (
        "Rewrite this one cover letter paragraph. Use ONLY facts from the PROFILE. Never add employers, skills, numbers, "
        f"dates or achievements.\n{STYLE}\nInstruction: {how.strip() or 'make it clearer and more specific to this job'}\n"
        "Return JSON {\"paragraph\": str}.\n\n"
        f"PARAGRAPH:\n{paragraph}\n\nPROFILE:\n{json.dumps(profile, ensure_ascii=False)}\n\nJOB:\n{json.dumps(job, ensure_ascii=False)}"
    )
    text = ask_json(prompt, llm=llm).get("paragraph")
    if not isinstance(text, str) or not text.strip():
        raise LLMError("The AI didn't return a paragraph. Please try again.")
    return text.strip()


def trim_to_one_page(pack: dict, page_count) -> dict:
    """Trim leadership first, then the last projects, until page_count(pack) is 1."""
    resume = pack["resume"]
    while page_count(pack) > 1:
        bulleted = [item for item in resume.get("leadership", []) if item.get("bullets")]
        if bulleted:
            bulleted[-1]["bullets"].pop()
        elif resume.get("leadership"):
            resume["leadership"].pop()
        elif len(resume.get("projects", [])) > 1:
            resume["projects"].pop()
        else:
            break
    return pack
