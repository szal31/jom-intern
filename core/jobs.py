"""Sanad's weekly internship list, and the picks shown to each student."""
import csv
import io
from datetime import date, timedelta

JOB_COLUMNS = ["company", "role", "link", "location", "posting_text", "date_found", "company_type"]
MAX_AGE_DAYS = 30


def load_jobs(csv_bytes: bytes) -> list[dict]:
    reader = csv.DictReader(io.StringIO(csv_bytes.decode("utf-8-sig")))
    missing = [c for c in JOB_COLUMNS if c not in (reader.fieldnames or [])]
    if missing:
        raise ValueError(f"The job list is missing columns: {', '.join(missing)}")
    return [{c: (row.get(c) or "").strip() for c in JOB_COLUMNS} for row in reader if (row.get("company") or "").strip()]


def recommend(jobs: list[dict], profile: dict, today: date) -> list[dict]:
    wanted = [p.strip().lower() for p in ((profile.get("window") or {}).get("locations") or "").split(",") if p.strip()]
    cutoff = today - timedelta(days=MAX_AGE_DAYS)
    picks = []
    for job in jobs:
        try:
            if date.fromisoformat(job["date_found"]) < cutoff:
                continue
        except ValueError:
            continue
        place = job["location"].lower()
        if wanted and "remote" not in place and not any(w in place for w in wanted):
            continue
        picks.append(job)
    return sorted(picks, key=lambda j: j["company_type"] or "9")
