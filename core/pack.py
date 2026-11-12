"""Write a tailored resume and cover letter from a student's own profile."""
import json

from core.checker import check_pack
from core.llm import ask_json

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
        "Titles must be copied exactly from the profile. The letter must name the company and the exact role."
        f"{fix}\n\nPROFILE:\n{json.dumps(profile, ensure_ascii=False)}\n\nJOB:\n{json.dumps(job, ensure_ascii=False)}"
    )
    result = ask_json(prompt, llm=llm)
    resume = result.get("resume") or {}
    return {
        "resume": {key: resume.get(key) or ([] if key != "summary" else "") for key in ("summary", "skills", "experience", "projects", "leadership")},
        "letter": [p for p in result.get("letter") or [] if isinstance(p, str) and p.strip()],
    }


def verify_pack(pack: dict, profile: dict, llm=None) -> list[str]:
    prompt = (
        "Check every resume bullet, the summary and every letter sentence against the PROFILE. "
        "Return JSON {\"untraceable\": [exact sentences or bullets that state a fact not supported by the profile]}. "
        "Opinions and polite phrases are fine.\n\n"
        f"PROFILE:\n{json.dumps(profile, ensure_ascii=False)}\n\nPACK:\n{json.dumps(pack, ensure_ascii=False)}"
    )
    return [s for s in ask_json(prompt, llm=llm).get("untraceable", []) if isinstance(s, str) and s.strip()]


def _drop(pack: dict, flagged: list[str]) -> dict:
    flagged = [f.strip() for f in flagged]
    resume = pack["resume"]
    for section in ("experience", "projects", "leadership"):
        for item in resume.get(section, []):
            item["bullets"] = [b for b in item.get("bullets", []) if b.strip() not in flagged]
    if resume.get("summary", "").strip() in flagged:
        resume["summary"] = ""
    letter = []
    for paragraph in pack["letter"]:
        for sentence in flagged:
            paragraph = paragraph.replace(sentence, "").strip()
        if paragraph:
            letter.append(" ".join(paragraph.split()))
    pack["letter"] = letter
    return pack


def build_pack(profile: dict, job: dict, other_companies: list[str], llm=None) -> tuple[dict, list[str]]:
    problems = None
    for _attempt in range(2):
        pack = write_pack(profile, job, llm=llm, problems=problems)
        pack = _drop(pack, verify_pack(pack, profile, llm=llm))
        problems = check_pack(pack, profile, job, other_companies)
        if not problems:
            return pack, []
    return pack, problems


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
