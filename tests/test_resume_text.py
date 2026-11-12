import io

import docx
import pytest
from fpdf import FPDF

from core.resume_text import read_resume


def pdf_bytes(text=None):
    pdf = FPDF()
    pdf.add_page()
    if text:
        pdf.set_font("Helvetica", size=12)
        pdf.cell(0, 10, text)
    return bytes(pdf.output())


def test_reads_pdf_text():
    assert "Jane Tan" in read_resume(pdf_bytes("Jane Tan, Mathematics"), "cv.pdf")


def test_reads_docx_text():
    document = docx.Document()
    document.add_paragraph("Jane Tan, Mathematics")
    buffer = io.BytesIO()
    document.save(buffer)
    assert "Jane Tan" in read_resume(buffer.getvalue(), "CV.DOCX")


def test_rejects_other_file_types():
    with pytest.raises(ValueError, match="Upload a PDF or Word file"):
        read_resume(b"\x89PNG", "photo.png")


def test_pdf_without_text_layer_returns_empty():
    assert read_resume(pdf_bytes(), "scan.pdf") == ""
