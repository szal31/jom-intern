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


def _text_starts(pdf_bytes):
    import io
    from pypdf import PdfReader
    xs = []
    for page in PdfReader(io.BytesIO(pdf_bytes)).pages:
        page.extract_text(visitor_text=lambda text, cm, tm, *_: xs.append((tm[4], text)) if text.strip() else None)
    return xs


def test_no_line_starts_at_the_right_edge():
    from tests.test_checker import GOOD, JOB, PROFILE
    from core.render import letter_pdf, resume_pdf
    profile = {**PROFILE, "education": [{"institution": "Uni A", "qualification": "BSc", "dates": "2025", "grade": "3.6"},
                                        {"institution": "Uni B", "qualification": "Diploma", "dates": "2022", "grade": "3.6"}]}
    for pdf in (resume_pdf(profile, GOOD)[0], letter_pdf(profile, JOB, GOOD)):
        stray = [t for x, t in _text_starts(pdf) if x > 540]  # A4 is 595pt wide; right margin starts near 553pt
        assert not stray, stray


def _chunks(pdf_bytes):
    import io
    from pypdf import PdfReader
    found = []
    PdfReader(io.BytesIO(pdf_bytes)).pages[0].extract_text(visitor_text=lambda text, cm, tm, *_: found.append((round(tm[5]), tm[4], text)) if text.strip() else None)
    return found


def test_long_project_title_wraps_clear_of_its_date():
    from tests.test_checker import GOOD, PROFILE
    from core.render import resume_pdf
    pack = copy.deepcopy(GOOD)
    title = "Predicting Student Dropout Risk Using Ensemble Machine Learning Models on Ten Years of Malaysian University Records EndWord"
    pack["resume"]["projects"] = [{"title": title, "dates": "Mar 2026 to Jul 2026", "bullets": ["Built it."]}]
    chunks = _chunks(resume_pdf(PROFILE, pack)[0])
    date_y = next(y for y, x, t in chunks if "Mar 2026 to Jul 2026" in t)
    end_y = next(y for y, x, t in chunks if "EndWord" in t)
    assert end_y != date_y  # the title went onto a second line instead of running under the date
