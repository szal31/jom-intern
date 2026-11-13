"""Mechanical checks on a pack before a student sees it.

Catches what a script can: other companies' names, dates outside the student's
window, numbers that aren't in their profile or the posting, invented titles
and skills, and ID numbers. Sentence-level truth is checked by verify_pack.
"""
import json
import re
import unicodedata
from difflib import SequenceMatcher

MONTHS = "January February March April May June July August September October November December".split()
ANY_DATE = re.compile(r"\b(?:(\d{1,2}) )?((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*) (20\d\d)\b")
NUMBER = re.compile(r"\d+(?:[.,]\d+)*(\s?(?:%|percent))?")
IC_NUMBER = re.compile(r"\b\d{6}-?\d{2}-?\d{4}\b")
AVAILABILITY = re.compile(r"\b(availab\w*|internship|intern|start\w*)\b", re.I)
MONTHS_LENGTH = re.compile(r"\b(?:\d+|three|four|five|six|twelve)(?:\s*(?:to|-)\s*\d+)?[- ]months?\b", re.I)
WEEKS_LENGTH = re.compile(r"\b(\d+)(?:\s*(?:to|-)\s*(\d+))?[- ]weeks?\b", re.I)
OWN_FACT = re.compile(r"project|course|scholarship|livestream|reviews|certificate", re.I)


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.replace("’", "'"))
    return "".join(c for c in text if not unicodedata.combining(c) and c != "'").casefold()


def contains(text: str, phrase: str) -> bool:
    return bool(phrase.strip()) and re.search(rf"(?<!\w){re.escape(normalize(phrase))}(?!\w)", normalize(text)) is not None


def _numbers(text: str):
    plain, percent = set(), set()
    for match in NUMBER.finditer(text):
        token = match[0].split("%")[0].split(" percent")[0].strip().replace(",", "").rstrip(".")
        (percent if match[1] else plain).add(token)
    return plain, percent


def _facts(profile: dict) -> str:
    return json.dumps({k: v for k, v in profile.items() if k != "contact"}, ensure_ascii=False)


def _parse_day(text: str):
    match = re.search(r"(\d{1,2}) ([A-Za-z]+) (20\d\d)", text or "")
    if not match or match[2][:3].title() not in [m[:3] for m in MONTHS]:
        return None
    return int(match[1]), [m[:3] for m in MONTHS].index(match[2][:3].title()) + 1, int(match[3])


def _resume_lines(resume: dict) -> list[str]:
    lines = [resume.get("summary", ""), *resume.get("skills", [])]
    for section in ("experience", "projects", "leadership"):
        for item in resume.get(section, []):
            lines += [item.get("title", ""), *item.get("bullets", [])]
    return [line for line in lines if line]


def check_pack(pack: dict, profile: dict, job: dict, other_companies: list[str]) -> list[str]:
    facts = _facts(profile)
    allowed, percent = _numbers(facts + json.dumps(job, ensure_ascii=False))
    resume, letter = pack.get("resume", {}), pack.get("letter", [])
    problems = []

    letter_text = "\n".join(letter)
    if letter:
        if not contains(letter_text, job.get("company", "")):
            problems.append(f"Letter doesn't name the company: {job.get('company')}")
        if not contains(letter_text, job.get("role", "")):
            problems.append(f"Letter doesn't name the role: {job.get('role')}")

    for section in ("experience", "projects", "leadership"):
        for item in resume.get(section, []):
            if item.get("title") and normalize(item["title"]) not in normalize(facts):
                problems.append(f"Resume {section} isn't in your profile: {item['title']}")
    for skill in resume.get("skills", []):
        for piece in re.split(r"[,;()]", skill.partition(":")[2] or skill):
            if piece.strip() and normalize(piece.strip()) not in normalize(facts):
                problems.append(f"Skill isn't in your profile: {piece.strip()}")

    window = profile.get("window") or {}
    start, end = _parse_day(window.get("start", "")), _parse_day(window.get("end", ""))
    allowed_weeks = set(re.findall(r"\d+", window.get("weeks", "")))
    others = [c for c in other_companies if c and not contains(job.get("company", ""), c) and not contains(c, job.get("company", ""))]

    for name, lines in (("Resume", _resume_lines(resume)), ("Letter", letter)):
        for line in lines:
            for company in others:
                if contains(line, company) and not (contains(facts, company) and OWN_FACT.search(line)):
                    problems.append(f"{name} names another company: {company}")
            if IC_NUMBER.search(line):
                problems.append(f"{name} contains what looks like an IC number.")
            for match in NUMBER.finditer(line):
                token = match[0].split("%")[0].split(" percent")[0].strip().replace(",", "").rstrip(".")
                if token not in (percent if match[1] else allowed):
                    problems.append(f"{name} has a number not in your profile or the posting: {match[0].strip()}")
            if start and end:
                for day, month, year in ANY_DATE.findall(line):
                    month_no = [m[:3] for m in MONTHS].index(month[:3]) + 1
                    key = (int(year), month_no, int(day) if day else None)
                    in_months = (start[2], start[1]) <= (key[0], key[1]) <= (end[2], end[1])
                    exact = key[2] is not None and (key == (start[2], start[1], start[0]) or key == (end[2], end[1], end[0]))
                    if key[0] in (start[2], end[2]) and not (exact or (key[2] is None and in_months)):
                        problems.append(f"{name} has a date outside your window: {' '.join(p for p in (day, month, year) if p)}")
            if AVAILABILITY.search(line):
                if MONTHS_LENGTH.search(line):
                    problems.append(f"{name} states a duration other than your window: {MONTHS_LENGTH.search(line)[0]}")
                for weeks in WEEKS_LENGTH.finditer(line):
                    if allowed_weeks and {weeks[1], weeks[2] or weeks[1]} - allowed_weeks:
                        problems.append(f"{name} states a duration other than your window: {weeks[0]}")
    return problems


def lines_to_check(pack: dict, profile: dict) -> set[str]:
    """Lines a student should read against their profile: resume lines the AI reworded, and letter sentences that state a fact."""
    originals = [normalize(profile.get("summary") or "")] + [
        normalize(text) for section in ("experience", "projects", "leadership") for item in profile.get(section, []) for text in item.get("bullets", [])
    ] + [normalize(value) for story in profile.get("stories", []) for value in story.values() if isinstance(value, str)]
    resume = pack.get("resume", {})
    flagged = set()
    for line in [resume.get("summary", "")] + [b for section in ("experience", "projects", "leadership") for item in resume.get(section, []) for b in item.get("bullets", [])]:
        if line and not any(SequenceMatcher(None, normalize(line), original).ratio() >= 0.9 for original in originals if original):
            flagged.add(line)
    terms = {term.strip() for group in profile.get("skills", []) for term in group.split(":", 1)[-1].split(",") if len(term.strip()) > 1}
    for paragraph in pack.get("letter", []):
        for sentence in re.split(r"(?<=[.!?])\s+", paragraph):
            if re.search(r"\d", sentence) or any(contains(sentence, term) for term in terms):
                flagged.add(sentence)
    return flagged
