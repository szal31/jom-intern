"""Turn an uploaded resume into plain text."""
import io

import docx
from pypdf import PdfReader


def read_resume(data: bytes, filename: str) -> str:
    name = filename.lower()
    if name.endswith(".pdf"):
        reader = PdfReader(io.BytesIO(data))
        return "\n".join(page.extract_text() or "" for page in reader.pages).strip()
    if name.endswith(".docx"):
        return "\n".join(p.text for p in docx.Document(io.BytesIO(data)).paragraphs).strip()
    raise ValueError("Upload a PDF or Word file")
