"""A student's tracker as an Excel file."""
import io

import openpyxl

COLUMNS = [("Company", "company"), ("Role", "role"), ("Link", "link"), ("Date made", "created_at"), ("Status", "status"), ("Notes", "notes")]


def tracker_xlsx(rows: list[dict]) -> bytes:
    book = openpyxl.Workbook()
    sheet = book.active
    sheet.title = "Applications"
    sheet.append([title for title, _ in COLUMNS])
    for row in rows:
        sheet.append([str(row.get(key) or "")[:10] if key == "created_at" else row.get(key) or "" for _, key in COLUMNS])
    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()
