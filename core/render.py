"""Word and PDF files for a pack. Plain one-column layout, no Word needed."""
import html
import io
from datetime import date

import docx
from docx.shared import Pt
from fpdf import FPDF

# shortcut: PDFs use the built-in Helvetica (Latin-1), so non-Latin names print as "?"; bundle a Unicode font if a student needs one.
LATIN1 = str.maketrans({"’": "'", "‘": "'", "“": '"', "”": '"', "–": "-", "—": "-", "•": "-", "…": "..."})


def _latin(text: str) -> str:
    return (text or "").translate(LATIN1).encode("latin-1", "replace").decode("latin-1")


def availability(profile: dict) -> str:
    window = profile.get("window") or {}
    if not (window.get("start") and window.get("end")):
        return ""
    weeks = f"{window['weeks']}-week " if window.get("weeks") else ""
    return f"Available for a {weeks}internship, {window['start'].strip().title()} to {window['end'].strip().title()}."


def _contact_line(profile: dict) -> str:
    contact = profile.get("contact") or {}
    keys = ("location", "phone", "email", "linkedin", "github")
    return " | ".join(contact[k] for k in keys if contact.get(k))


def _resume_blocks(profile: dict, pack: dict) -> list[tuple[str, object]]:
    """The resume as (kind, content) blocks shared by Word and PDF."""
    resume = pack["resume"]
    summary = " ".join(p for p in (resume.get("summary", ""), availability(profile)) if p)
    blocks = [("name", (profile.get("contact") or {}).get("name", "")), ("contact", _contact_line(profile)), ("text", summary)]
    education = [
        {"title": e.get("institution", ""), "dates": e.get("dates", ""), "bullets": [" | ".join(x for x in (e.get("qualification"), e.get("grade")) if x)]}
        for e in profile.get("education", [])
    ]
    sections = [("EDUCATION", education), ("EXPERIENCE", resume.get("experience", [])), ("SKILLS", resume.get("skills", [])),
                ("PROJECTS", resume.get("projects", [])), ("LEADERSHIP & ACTIVITIES", resume.get("leadership", []))]
    for heading, items in sections:
        if not items:
            continue
        blocks.append(("heading", heading))
        for item in items:
            if isinstance(item, str):
                blocks.append(("text", item))
            else:
                blocks.append(("entry", (item.get("title", ""), item.get("dates", ""))))
                blocks += [("bullet", b) for b in item.get("bullets", []) if b]
    blocks += [("heading", "REFERENCES"), ("text", "References available upon request.")]
    return blocks


def _letter_lines(profile: dict, job: dict, pack: dict) -> list[str]:
    contact = profile.get("contact") or {}
    today = date.today()
    header = [contact.get("name", ""), contact.get("location", ""), contact.get("phone", ""), contact.get("email", ""), "",
              f"{today.day} {today:%B %Y}", "", "Hiring Manager", job.get("company", ""), job.get("address", ""), "", "Dear Hiring Manager,", ""]
    body = []
    for paragraph in pack["letter"]:
        body += [paragraph, ""]
    return [line for line in header if line is not None] + body + ["Sincerely,", "", contact.get("name", "")]


def resume_docx(profile: dict, pack: dict) -> bytes:
    document = docx.Document()
    document.styles["Normal"].font.size = Pt(10)
    for kind, content in _resume_blocks(profile, pack):
        if kind == "name":
            document.add_heading(content, level=1)
        elif kind == "heading":
            document.add_heading(content, level=2)
        elif kind == "entry":
            run = document.add_paragraph().add_run(f"{content[0]}    {content[1]}".strip())
            run.bold = True
        elif kind == "bullet":
            document.add_paragraph(content, style="List Bullet")
        elif content:
            document.add_paragraph(content)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def resume_pdf(profile: dict, pack: dict) -> tuple[bytes, int]:
    pdf = FPDF(format="A4")
    pdf.set_margins(15, 12, 15)
    pdf.set_auto_page_break(True, margin=12)
    pdf.add_page()
    width = pdf.epw
    for kind, content in _resume_blocks(profile, pack):
        if kind == "name":
            pdf.set_font("Helvetica", "B", 15)
            pdf.cell(width, 7, _latin(content), align="C", new_x="LMARGIN", new_y="NEXT")
        elif kind == "contact":
            pdf.set_font("Helvetica", "", 9)
            pdf.multi_cell(width, 4.5, _latin(content), align="C", new_x="LMARGIN", new_y="NEXT")
        elif kind == "heading":
            pdf.ln(1.5)
            pdf.set_font("Helvetica", "B", 10)
            pdf.cell(width, 5, _latin(content), border="B", new_x="LMARGIN", new_y="NEXT")
            pdf.ln(0.5)
        elif kind == "entry":
            pdf.set_font("Helvetica", "B", 9.5)
            pdf.cell(width * 0.75, 4.8, _latin(content[0]))
            pdf.set_font("Helvetica", "", 9.5)
            pdf.cell(width * 0.25, 4.8, _latin(content[1]), align="R", new_x="LMARGIN", new_y="NEXT")
        elif kind == "bullet":
            pdf.set_font("Helvetica", "", 9.5)
            pdf.set_x(pdf.l_margin + 3)
            pdf.multi_cell(width - 3, 4.5, _latin(f"- {content}"), new_x="LMARGIN", new_y="NEXT")
        elif content:
            pdf.set_font("Helvetica", "", 9.5)
            pdf.multi_cell(width, 4.5, _latin(content), new_x="LMARGIN", new_y="NEXT")
    return bytes(pdf.output()), pdf.page


def letter_docx(profile: dict, job: dict, pack: dict) -> bytes:
    document = docx.Document()
    document.styles["Normal"].font.size = Pt(11)
    for line in _letter_lines(profile, job, pack):
        document.add_paragraph(line)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def letter_pdf(profile: dict, job: dict, pack: dict) -> bytes:
    pdf = FPDF(format="A4")
    pdf.set_margins(22, 20, 22)
    pdf.add_page()
    pdf.set_font("Helvetica", "", 11)
    for line in _letter_lines(profile, job, pack):
        pdf.multi_cell(pdf.epw, 5.5, _latin(line), new_x="LMARGIN", new_y="NEXT")
    return bytes(pdf.output())


def _mark(text: str, marked) -> str:
    """Escape text and wrap each line to check in <mark>."""
    safe = html.escape(text or "")
    for line in sorted(marked, key=len, reverse=True):
        escaped = html.escape(line)
        if escaped and escaped in safe:
            safe = safe.replace(escaped, f"<mark>{escaped}</mark>", 1)
    return safe


def resume_html(profile: dict, pack: dict, marked=frozenset()) -> str:
    """An on-screen sheet of the resume, from the same blocks the PDF uses."""
    parts = []
    for kind, content in _resume_blocks(profile, pack):
        if kind == "name":
            parts.append(f"<h4>{html.escape(content)}</h4>")
        elif kind == "contact":
            parts.append(f'<p class="jom-sheet-contact">{html.escape(content)}</p>')
        elif kind == "heading":
            parts.append(f"<h5>{html.escape(content)}</h5>")
        elif kind == "entry":
            parts.append(f'<p class="jom-sheet-entry"><b>{html.escape(content[0])}</b><span>{html.escape(content[1])}</span></p>')
        elif kind == "bullet":
            parts.append(f'<p class="jom-sheet-bullet">{_mark(content, marked)}</p>')
        elif content:
            parts.append(f"<p>{_mark(content, marked)}</p>")
    return f'<div class="jom-sheet">{"".join(parts)}</div>'


def letter_html(profile: dict, job: dict, pack: dict, marked=frozenset()) -> str:
    """An on-screen sheet of the cover letter."""
    lines = "".join(f"<p>{_mark(line, marked)}</p>" if line else '<p class="jom-sheet-gap"></p>' for line in _letter_lines(profile, job, pack))
    return f'<div class="jom-sheet jom-sheet-letter">{lines}</div>'
