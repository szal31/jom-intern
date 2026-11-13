"""Supabase: accounts, each student's own rows (row-level security) and files."""
import os
from datetime import date, datetime, timezone

from supabase import create_client

PACK_LIMIT_PER_DAY = 10


def friendly_error(error: Exception) -> str:
    text = str(error)
    if "pilot_full" in text or "Database error saving new user" in text:
        return "The pilot is full."
    if "Invalid login credentials" in text:
        return "Wrong email or password."
    if "already registered" in text:
        return "That email already has an account. Log in instead."
    if "For security purposes" in text:  # same email again within 60 seconds: the first request already made the account and sent the email
        return "We've already sent your confirmation email. Check your inbox and spam folder, click the link, then log in here."
    if "rate limit exceeded" in text.lower():
        return "Too many sign-ups in the last hour. Please try again in an hour."
    return "Something went wrong. Please try again in a minute."


def client():
    return create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_ANON_KEY"])


def service_client():
    """Admin-only client that bypasses row-level security. Never used for student pages."""
    return create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])


def seats_left(db) -> int:
    return int(db.rpc("pilot_seats_left").execute().data)


def sign_up(db, email: str, password: str):
    return db.auth.sign_up({"email": email, "password": password})


def sign_in(db, email: str, password: str):
    return db.auth.sign_in_with_password({"email": email, "password": password}).user


def restore(db, refresh_token: str):
    """Swap a remembered refresh token for a fresh session; returns the user."""
    return db.auth.refresh_session(refresh_token).user


def session_token(db) -> str | None:
    """The current refresh token, which rotates whenever the session refreshes."""
    session = db.auth.get_session()
    return session.refresh_token if session else None


def sign_out(db):
    db.auth.sign_out()


def load_profile(db, user_id: str) -> dict | None:
    rows = db.table("profiles").select("data, consent_at").eq("user_id", user_id).execute().data
    return rows[0] if rows else None


def save_profile(db, user_id: str, data: dict, consent: bool = False):
    row = {"user_id": user_id, "data": data}
    if consent:
        row["consent_at"] = datetime.now(timezone.utc).isoformat()
    db.table("profiles").upsert(row).execute()


def packs_today(db, user_id: str) -> int:
    rows = db.table("usage").select("packs").eq("user_id", user_id).eq("day", date.today().isoformat()).execute().data
    return rows[0]["packs"] if rows else 0


def save_pack(db, user_id: str, meta: dict, files: dict[str, bytes]) -> dict:
    """Upload the pack's files, record it, and count it towards today's limit."""
    row = db.table("packs").insert({"user_id": user_id, "status": "Ready", **meta}).execute().data[0]
    paths = {}
    for name, data in files.items():
        path = f"{user_id}/{row['id']}/{name}"
        db.storage.from_("packs").upload(path, data, {"upsert": "true"})
        paths[name] = path
    db.table("packs").update({"files": paths}).eq("id", row["id"]).execute()
    db.table("usage").upsert({"user_id": user_id, "day": date.today().isoformat(), "packs": packs_today(db, user_id) + 1}).execute()
    return {**row, "files": paths}


def list_packs(db, user_id: str) -> list[dict]:
    return db.table("packs").select("*").eq("user_id", user_id).order("created_at", desc=True).execute().data


def download(db, path: str) -> bytes:
    return db.storage.from_("packs").download(path)


def update_pack(db, pack_id: str, **fields):
    db.table("packs").update(fields).eq("id", pack_id).execute()


def log_event(db, kind: str, detail: str):
    try:
        db.table("events").insert({"kind": kind, "detail": detail[:500]}).execute()
    except Exception:
        pass  # logging must never break a student's page


def all_files(db, user_id: str) -> list[str]:
    """Every file in the student's folder, including ones no pack row points to."""
    bucket = db.storage.from_("packs")
    return [f"{user_id}/{folder['name']}/{f['name']}" for folder in bucket.list(user_id) for f in bucket.list(f"{user_id}/{folder['name']}")]


def _erase(db, admin, user_id: str):
    """Files first, then rows, then the account: a failure part-way leaves nothing orphaned behind a live row."""
    files = all_files(admin, user_id)
    if files:
        admin.storage.from_("packs").remove(files)
    for table in ("packs", "usage", "profiles"):
        db.table(table).delete().eq("user_id", user_id).execute()
    admin.auth.admin.delete_user(user_id)


def delete_my_data(db, admin, user_id: str):
    """Remove the student's files, rows and account."""
    _erase(db, admin, user_id)


def admin_stats(admin) -> dict:
    usage = admin.table("usage").select("user_id, day, packs").execute().data
    events = admin.table("events").select("kind, detail, created_at").order("created_at", desc=True).limit(50).execute().data
    return {"usage": usage, "events": events}


def admin_accounts(admin) -> list[dict]:
    return [{"id": u.id, "email": u.email, "created_at": str(u.created_at)[:10]} for u in admin.auth.admin.list_users()]


def admin_delete_account(admin, user_id: str):
    _erase(admin, admin, user_id)


def load_job_list(db) -> list[dict]:
    return db.table("jobs").select("*").execute().data


def replace_jobs(admin, rows: list[dict]):
    admin.table("jobs").delete().neq("company", "").execute()
    if rows:
        admin.table("jobs").insert(rows).execute()
