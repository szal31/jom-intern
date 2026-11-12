import copy

from core.checker import check_pack

PROFILE = {
    "contact": {"name": "Jane Tan", "phone": "012-345 6789"},
    "summary": "",
    "education": [{"institution": "UiTM", "qualification": "BSc Mathematics", "dates": "2025 to 2027", "grade": "CGPA 3.70"}],
    "experience": [{"title": "Part-time Tutor", "dates": "2024 to 2025", "bullets": ["Tutored 8 students"]}],
    "projects": [{"title": "Sales Dashboard", "dates": "2026", "tools": "Power BI", "bullets": ["Built a report on 12,000 rows, cutting errors by 15%"]}],
    "skills": ["Analytics: Power BI, Excel", "Programming: Python, SQL"],
    "leadership": [],
    "languages": ["English"],
    "stories": [],
    "window": {"start": "15 March 2027", "end": "4 July 2027", "weeks": "14 to 16", "locations": "Kuala Lumpur"},
}
JOB = {"company": "Acme Malaysia", "role": "Data Analyst Intern", "posting_text": "3 month role at Level 9.", "address": "Level 9, Menara Acme"}
GOOD = {
    "resume": {
        "summary": "Mathematics student focused on data.",
        "skills": ["Analytics: Power BI, Excel"],
        "experience": [{"title": "Part-time Tutor", "dates": "2024 to 2025", "bullets": ["Tutored 8 students"]}],
        "projects": [{"title": "Sales Dashboard", "dates": "2026", "bullets": ["Built a report on 12,000 rows"]}],
        "leadership": [],
    },
    "letter": [
        "I am applying for the Data Analyst Intern position at Acme Malaysia. I can intern for 14 to 16 weeks, from 15 March to 4 July 2027.",
        "My dashboard cut errors by 15%.",
    ],
}


def pack_with_letter(*extra):
    pack = copy.deepcopy(GOOD)
    pack["letter"] += list(extra)
    return pack


def has(problems, word):
    return any(word.lower() in p.lower() for p in problems)


def test_clean_pack_passes():
    assert check_pack(GOOD, PROFILE, JOB, ["Zenith"]) == []


def test_other_company_fails():
    assert has(check_pack(pack_with_letter("I admire Zenith."), PROFILE, JOB, ["Zenith"]), "Zenith")


def test_other_company_with_accent_and_curly_apostrophe_fails():
    assert has(check_pack(pack_with_letter("I admire L’Oreal."), PROFILE, JOB, ["L'Oréal"]), "Oréal")


def test_accented_job_company_is_its_own():
    job = dict(JOB, company="Nestlé Malaysia")
    pack = copy.deepcopy(GOOD)
    pack["letter"][0] = pack["letter"][0].replace("Acme Malaysia", "Nestle Malaysia")
    assert check_pack(pack, PROFILE, job, ["Nestlé"]) == []


def test_letter_must_name_company_and_role():
    pack = copy.deepcopy(GOOD)
    pack["letter"] = ["I can intern from 15 March to 4 July 2027."]
    problems = check_pack(pack, PROFILE, JOB, [])
    assert has(problems, "company") and has(problems, "role")


def test_invented_number_fails():
    assert has(check_pack(pack_with_letter("I improved sales by 87%."), PROFILE, JOB, []), "87")


def test_percent_only_matches_percent():
    assert has(check_pack(pack_with_letter("I raised accuracy by 8%."), PROFILE, JOB, []), "8%")


def test_number_from_posting_passes():
    assert check_pack(pack_with_letter("I read the 3 month posting."), PROFILE, JOB, []) == []


def test_date_outside_window_fails():
    assert has(check_pack(pack_with_letter("I can start on 18 January 2027."), PROFILE, JOB, []), "18 January 2027")


def test_month_inside_window_passes():
    assert check_pack(pack_with_letter("I saw the April 2027 intake."), PROFILE, JOB, []) == []


def test_wrong_duration_fails():
    assert has(check_pack(pack_with_letter("I am available for a 6-month internship."), PROFILE, JOB, []), "duration")


def test_ic_number_fails():
    assert has(check_pack(pack_with_letter("IC 040101-14-1234"), PROFILE, JOB, []), "IC")


def test_invented_title_and_skill_fail():
    pack = copy.deepcopy(GOOD)
    pack["resume"]["experience"] = [{"title": "Data Scientist, Petronas", "dates": "2026", "bullets": []}]
    pack["resume"]["skills"] = ["Cloud: AWS"]
    problems = check_pack(pack, PROFILE, JOB, [])
    assert has(problems, "Petronas") and has(problems, "AWS")
