import copy
import io

import docx
from pypdf import PdfReader

from core.render import letter_docx, letter_pdf, resume_docx, resume_pdf
from tests.test_checker import GOOD, JOB, PROFILE


def docx_text(data):
    return "\n".join(p.text for p in docx.Document(io.BytesIO(data)).paragraphs)


def test_full_profile_is_one_page():
    _, pages = resume_pdf(PROFILE, GOOD)
    assert pages == 1


def test_availability_and_references_on_resume():
    text = docx_text(resume_docx(PROFILE, GOOD))
    assert "15 March 2027 to 4 July 2027" in text
    assert "References available upon request." in text


def test_empty_section_has_no_heading():
    pack = copy.deepcopy(GOOD)
    pack["resume"]["projects"] = []
    assert "PROJECTS" not in docx_text(resume_docx(PROFILE, pack))


def test_accented_company_survives_pdf():
    job = dict(JOB, company="Nestlé Malaysia")
    data = letter_pdf(PROFILE, job, GOOD)
    assert "Nestlé" in PdfReader(io.BytesIO(data)).pages[0].extract_text()
    assert "Nestlé" in docx_text(letter_docx(PROFILE, job, GOOD))


def test_oversized_resume_reports_more_pages():
    pack = copy.deepcopy(GOOD)
    pack["resume"]["projects"] = [{"title": f"P{i}", "dates": "2026", "bullets": ["Built a long thing " * 20] * 3} for i in range(12)]
    _, pages = resume_pdf(PROFILE, pack)
    assert pages > 1
