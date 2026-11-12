import io
from datetime import date

import openpyxl
import pytest

from core.db import friendly_error
from core.jobs import JOB_COLUMNS, load_jobs, recommend
from core.tracker import tracker_xlsx

HEADER = ",".join(JOB_COLUMNS)


def csv(*rows):
    return ("\n".join([HEADER, *rows]) + "\n").encode("utf-8")


def test_missing_column_is_named():
    with pytest.raises(ValueError, match="link"):
        load_jobs(b"company,role\nAcme,Intern\n")


def test_old_jobs_and_other_locations_are_hidden():
    jobs = load_jobs(csv(
        "Acme,Data Intern,https://a,Kuala Lumpur,text,2026-11-01,1 MNC",
        "Old Co,Data Intern,https://b,Kuala Lumpur,text,2026-09-01,1 MNC",
        "Far Co,Data Intern,https://c,Johor Bahru,text,2026-11-01,1 MNC",
        "Home Co,Data Intern,https://d,Remote,text,2026-11-01,3 Smaller",
    ))
    picks = recommend(jobs, {"window": {"locations": "Kuala Lumpur"}}, today=date(2026, 11, 12))
    assert [j["company"] for j in picks] == ["Acme", "Home Co"]


def test_no_location_preference_keeps_everything_recent():
    jobs = load_jobs(csv("Acme,Data Intern,https://a,Penang,text,2026-11-01,2 Large local"))
    assert len(recommend(jobs, {"window": {}}, today=date(2026, 11, 12))) == 1


def test_tracker_has_header_and_rows():
    data = tracker_xlsx([{"company": "Acme", "role": "Intern", "link": "https://a", "created_at": "2026-11-12", "status": "Ready", "notes": ""}])
    sheet = openpyxl.load_workbook(io.BytesIO(data)).active
    assert [c.value for c in sheet[1]] == ["Company", "Role", "Link", "Date made", "Status", "Notes"]
    assert sheet["A2"].value == "Acme"


def test_friendly_errors():
    assert friendly_error(Exception("pilot_full: 10 accounts")) == "The pilot is full."
    assert friendly_error(Exception("Invalid login credentials")) == "Wrong email or password."
    assert "try again" in friendly_error(Exception("something odd")).lower()
