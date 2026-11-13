"""In-memory stand-in for core.db, so the app can be clicked through in tests."""
from types import SimpleNamespace

from core import db


def install_fake_db(monkeypatch):
    for name, value in {"GEMINI_API_KEY": "x", "SUPABASE_URL": "x", "SUPABASE_ANON_KEY": "x", "SUPABASE_SERVICE_KEY": "x",
                        "ADMIN_EMAIL": "admin@example.com", "USE_FAKE_LLM": "1"}.items():
        monkeypatch.setenv(name, value)
    store = {"profiles": {}, "packs": [], "files": {}, "usage": 0}
    user = SimpleNamespace(id="u1", email="student@example.com")

    def save_pack(_db, user_id, meta, files):
        row = {"id": f"p{len(store['packs'])}", "user_id": user_id, "status": "Ready", "notes": "", "created_at": "2026-11-12T00:00:00", **meta}
        row["files"] = {name: f"{user_id}/{row['id']}/{name}" for name in files}
        store["files"].update({row["files"][n]: data for n, data in files.items()})
        store["packs"].append(row)
        store["usage"] += 1
        return row

    fakes = {
        "client": lambda: SimpleNamespace(),
        "service_client": lambda: SimpleNamespace(),
        "seats_left": lambda _db: 9,
        "sign_in": lambda _db, email, password: user,
        "sign_out": lambda _db: None,
        "restore": lambda _db, token: user if token == "remembered-token" else (_ for _ in ()).throw(ValueError("Invalid Refresh Token")),
        "session_token": lambda _db: "fresh-token",
        "load_profile": lambda _db, uid: store["profiles"].get(uid),
        "save_profile": lambda _db, uid, data, consent=False: store["profiles"].__setitem__(
            uid, {"data": data, "consent_at": "now" if consent else (store["profiles"].get(uid) or {}).get("consent_at")}),
        "packs_today": lambda _db, uid: store["usage"],
        "save_pack": save_pack,
        "list_packs": lambda _db, uid: list(reversed(store["packs"])),
        "download": lambda _db, path: store["files"][path],
        "update_pack": lambda _db, pid, **fields: next(p for p in store["packs"] if p["id"] == pid).update(fields),
        "log_event": lambda _db, kind, detail: None,
        "load_job_list": lambda _db: [],
    }
    for name, fake in fakes.items():
        monkeypatch.setattr(db, name, fake)
    return store
