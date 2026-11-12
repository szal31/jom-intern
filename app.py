"""Internship Pack: a tailored, checked resume and cover letter for each internship."""
import json
import os
from datetime import date

import streamlit as st

from core import db
from core.checker import check_pack
from core.jobs import load_jobs, recommend
from core.llm import LLMError
from core.pack import build_pack, trim_to_one_page
from core.profile import empty_profile, extract_profile
from core.render import letter_docx, letter_pdf, resume_docx, resume_pdf
from core.resume_text import read_resume
from core.tracker import tracker_xlsx

SECRETS = ["GEMINI_API_KEY", "SUPABASE_URL", "SUPABASE_ANON_KEY", "SUPABASE_SERVICE_KEY", "ADMIN_EMAIL"]
STATUSES = ["Ready", "Applied", "Interview", "Rejected", "Offer"]
PRIVACY = """**Before you start**
- This is a pilot for up to 10 students, run by Sanad.
- Your profile, the resumes and letters you make, and your tracker are stored in a private database. Only you can see them in the app.
- As the database owner, Sanad can technically read the data. He will only look at yours if you ask him for help.
- Your details are sent to Google's Gemini AI to write your documents. On the free tier, Google may use what's sent to improve its products.
- You can delete everything, including your account, at any time from **My account**."""

st.set_page_config(page_title="Internship Pack", page_icon="📄")

try:
    secrets = dict(st.secrets)
except Exception:  # no secrets file yet: fall through to the "not set up" message
    secrets = {}
for name in SECRETS + ["GEMINI_MODEL", "USE_FAKE_LLM"]:
    if name not in os.environ and name in secrets:
        os.environ[name] = str(secrets[name])
missing = [n for n in SECRETS if not os.environ.get(n)]
if missing:
    st.error(f"The app isn't set up yet. Missing settings: {', '.join(missing)}")
    st.stop()

LLM = None
if os.environ.get("USE_FAKE_LLM") == "1":
    from core.fake_llm import fake_llm as LLM

state = st.session_state
if "db" not in state:
    state.db = db.client()
    state.user = None


def login_page():
    st.title("Internship Pack")
    st.write("Turn your resume into a tailored resume and cover letter for each internship.")
    log_in, sign_up = st.tabs(["Log in", "Sign up"])
    with log_in, st.form("login"):
        email, password = st.text_input("Email"), st.text_input("Password", type="password")
        if st.form_submit_button("Log in"):
            try:
                state.user = db.sign_in(state.db, email, password)
                st.rerun()
            except Exception as error:
                st.error(db.friendly_error(error))
    with sign_up:
        seats = db.seats_left(state.db)
        if seats == 0:
            st.info("The pilot is full.")
            return
        st.caption(f"{seats} of 10 places left.")
        with st.form("signup"):
            email, password = st.text_input("Email"), st.text_input("Password (8+ characters)", type="password")
            if st.form_submit_button("Create account"):
                try:
                    result = db.sign_up(state.db, email, password)
                    if result.session:
                        state.user = result.user
                        st.rerun()
                    st.success("Account created. Check your email to confirm it, then log in.")
                except Exception as error:
                    st.error(db.friendly_error(error))


def consent_page(record):
    st.title("Welcome")
    st.markdown(PRIVACY)
    if st.checkbox("I understand and agree") and st.button("Continue"):
        db.save_profile(state.db, state.user.id, (record or {}).get("data") or empty_profile(), consent=True)
        st.rerun()


def edit_items(label, items, fields, key):
    """Edit a list of entries; bullets are one per line."""
    st.subheader(label)
    result = []
    for i, item in enumerate(items):
        with st.expander(item.get(fields[0]) or f"{label} {i + 1}", expanded=not item.get(fields[0])):
            entry = {f: st.text_input(f.title(), item.get(f, ""), key=f"{key}{i}{f}") for f in fields}
            if "bullets" in item or key in ("exp", "proj", "lead"):
                entry["bullets"] = [b for b in st.text_area("Bullets (one per line)", "\n".join(item.get("bullets", [])), key=f"{key}{i}b").splitlines() if b.strip()]
            if not st.checkbox("Remove", key=f"{key}{i}rm"):
                result.append(entry)
    if st.button(f"Add {label.lower()}", key=f"{key}add"):
        result.append({f: "" for f in fields} | ({"bullets": []} if key in ("exp", "proj", "lead") else {}))
    return result


def profile_page(profile):
    st.title("My profile")
    st.caption("Everything in your resume and letters comes from here. Nothing else is added.")
    upload = st.file_uploader("Upload your current resume (PDF or Word) to fill this in", type=["pdf", "docx"])
    if upload and st.button("Read my resume"):
        try:
            text = read_resume(upload.getvalue(), upload.name)
            if not text:
                st.warning("Couldn't read any text from that file. It may be a scanned image. Please fill in the sections below.")
            else:
                with st.spinner("Reading your resume..."):
                    profile = extract_profile(text, llm=LLM)
                db.save_profile(state.db, state.user.id, profile)
                st.rerun()
        except (ValueError, LLMError) as error:
            st.error(str(error))
    contact = profile.get("contact") or {}
    st.subheader("Contact")
    profile["contact"] = {f: st.text_input(f.title(), contact.get(f, ""), key=f"c{f}") for f in ("name", "location", "phone", "email", "linkedin", "github")}
    profile["summary"] = st.text_area("A line about you (optional)", profile.get("summary", ""))
    profile["education"] = edit_items("Education", profile.get("education", []), ["institution", "qualification", "dates", "grade"], "edu")
    profile["experience"] = edit_items("Experience", profile.get("experience", []), ["title", "dates"], "exp")
    profile["projects"] = edit_items("Projects", profile.get("projects", []), ["title", "dates", "tools"], "proj")
    profile["leadership"] = edit_items("Leadership & activities", profile.get("leadership", []), ["title", "dates"], "lead")
    st.subheader("Skills and languages")
    profile["skills"] = [s for s in st.text_area("Skills, one group per line (e.g. Analytics: Power BI, Excel)", "\n".join(profile.get("skills", []))).splitlines() if s.strip()]
    profile["languages"] = [s for s in st.text_area("Languages, one per line", "\n".join(profile.get("languages", []))).splitlines() if s.strip()]
    st.subheader("Your stories")
    st.caption("3 to 5 real experiences for cover letters: a challenge, what you did, what happened.")
    profile["stories"] = edit_items("Story", profile.get("stories", []), ["situation", "action", "result"], "story")
    window = profile.get("window") or {}
    st.subheader("Internship window")
    profile["window"] = {
        "start": st.text_input("Start date (e.g. 15 March 2027)", window.get("start", "")),
        "end": st.text_input("End date (e.g. 4 July 2027)", window.get("end", "")),
        "weeks": st.text_input("Length in weeks (e.g. 14 to 16)", window.get("weeks", "")),
        "locations": st.text_input("Locations, comma separated (e.g. Kuala Lumpur, Selangor)", window.get("locations", "")),
    }
    if st.button("Save profile", type="primary"):
        db.save_profile(state.db, state.user.id, profile)
        st.success("Saved.")


def make_pack(profile, job):
    if db.packs_today(state.db, state.user.id) >= db.PACK_LIMIT_PER_DAY:
        st.warning(f"You've made {db.PACK_LIMIT_PER_DAY} packs today. Come back tomorrow.")
        return
    others = sorted({p["company"] for p in db.list_packs(state.db, state.user.id)} | {j["company"] for j in db.load_job_list(state.db)})
    try:
        with st.spinner("Writing and checking your resume and letter..."):
            pack, problems = build_pack(profile, job, others, llm=LLM)
            pack = trim_to_one_page(pack, lambda p: resume_pdf(profile, p)[1])
            files = {"resume.pdf": resume_pdf(profile, pack)[0], "resume.docx": resume_docx(profile, pack),
                     "letter.pdf": letter_pdf(profile, job, pack), "letter.docx": letter_docx(profile, job, pack),
                     "pack.json": json.dumps({"pack": pack, "job": job}).encode()}
            db.save_pack(state.db, state.user.id, {"company": job["company"], "role": job["role"], "link": job.get("link", "")}, files)
    except LLMError as error:
        db.log_event(state.db, "llm_error", str(error))
        st.error(f"{error} Nothing was saved, and this didn't count towards today's limit.")
        return
    if problems:
        db.log_event(state.db, "checker", "; ".join(problems))
        st.warning("Saved, but please fix these before using it (My packs → Edit):\n- " + "\n- ".join(problems))
    else:
        st.success("Done. Find it under My packs.")


def internships_page(profile):
    st.title("Internships")
    if not (profile.get("contact") or {}).get("name"):
        st.info("Fill in your profile first.")
        return
    recommended, own = st.tabs(["Recommended", "Paste my own"])
    with recommended:
        picks = recommend(db.load_job_list(state.db), profile, date.today())
        if not picks:
            st.write("No recommended internships right now. Paste your own instead.")
        for i, job in enumerate(picks):
            with st.expander(f"{job['company']}: {job['role']} ({job['location']})"):
                st.write(job["posting_text"][:800])
                st.link_button("Open posting", job["link"]) if job["link"] else None
                if st.button("Make my pack", key=f"rec{i}"):
                    make_pack(profile, {k: job[k] for k in ("company", "role", "link", "posting_text")} | {"address": job["location"]})
    with own, st.form("own"):
        job = {"company": st.text_input("Company"), "role": st.text_input("Role (exact title)"), "link": st.text_input("Link (optional)"),
               "address": st.text_input("Office address (optional)"), "posting_text": st.text_area("Paste the job description")}
        if st.form_submit_button("Make my pack"):
            if not (job["company"] and job["role"] and job["posting_text"]):
                st.error("Company, role and job description are needed.")
            else:
                make_pack(profile, job)


def packs_page(profile):
    st.title("My packs")
    packs = db.list_packs(state.db, state.user.id)
    if not packs:
        st.write("No packs yet. Make one under Internships.")
    for row in packs:
        with st.expander(f"{row['company']}: {row['role']} ({row['created_at'][:10]})"):
            files = row.get("files") or {}
            columns = st.columns(4)
            for column, name in zip(columns, ("resume.pdf", "resume.docx", "letter.pdf", "letter.docx")):
                if name in files:
                    column.download_button(name, db.download(state.db, files[name]), file_name=f"{row['company']} {name}", key=f"{row['id']}{name}")
            status = st.selectbox("Status", STATUSES, STATUSES.index(row["status"]) if row["status"] in STATUSES else 0, key=f"s{row['id']}")
            notes = st.text_input("Notes", row.get("notes") or "", key=f"n{row['id']}")
            if st.button("Save status", key=f"save{row['id']}"):
                db.update_pack(state.db, row["id"], status=status, notes=notes)
                st.rerun()
            if "pack.json" in files and st.toggle("Edit letter", key=f"edit{row['id']}"):
                saved = json.loads(db.download(state.db, files["pack.json"]))
                pack, job = saved["pack"], saved["job"]
                pack["letter"] = [p for p in st.text_area("Letter paragraphs (blank line between)", "\n\n".join(pack["letter"]), height=300, key=f"l{row['id']}").split("\n\n") if p.strip()]
                problems = check_pack(pack, profile, job, [])
                for problem in problems:
                    st.warning(problem)
                if st.checkbox("I've checked this and it's true", key=f"ok{row['id']}") and st.button("Save edited letter", key=f"sl{row['id']}"):
                    for name, data in {"letter.pdf": letter_pdf(profile, job, pack), "letter.docx": letter_docx(profile, job, pack),
                                       "pack.json": json.dumps({"pack": pack, "job": job}).encode()}.items():
                        state.db.storage.from_("packs").upload(files[name], data, {"upsert": "true"})
                    st.success("Saved.")


def tracker_page():
    st.title("Tracker")
    packs = db.list_packs(state.db, state.user.id)
    st.dataframe([{k: p.get(k) for k in ("company", "role", "status", "notes", "link")} | {"made": p["created_at"][:10]} for p in packs], use_container_width=True)
    st.download_button("Download as Excel", tracker_xlsx(packs), file_name="internship_tracker.xlsx")


def account_page():
    st.title("My account")
    st.markdown(PRIVACY)
    st.subheader("Delete my data")
    if st.text_input("Type DELETE to remove your profile, packs, files and account") == "DELETE" and st.button("Delete everything"):
        db.delete_my_data(state.db, db.service_client(), state.user.id)
        state.user = None
        st.rerun()


def admin_page():
    st.title("Admin")
    admin = db.service_client()
    accounts = db.admin_accounts(admin)
    st.metric("Accounts", f"{len(accounts)} of 10")
    for account in accounts:
        left, right = st.columns([4, 1])
        left.write(f"{account['email']} (joined {account['created_at']})")
        if account["email"] != os.environ["ADMIN_EMAIL"] and right.button("Delete", key=f"del{account['id']}"):
            db.admin_delete_account(admin, account["id"])
            st.rerun()
    stats = db.admin_stats(admin)
    st.subheader("Packs per student per day")
    st.dataframe(stats["usage"], use_container_width=True)
    st.subheader("Recent errors and checker failures")
    st.dataframe(stats["events"], use_container_width=True)
    st.subheader("Weekly job list")
    upload = st.file_uploader("Upload jobs_export.csv", type="csv")
    if upload and st.button("Replace job list"):
        try:
            rows = load_jobs(upload.getvalue())
            db.replace_jobs(admin, rows)
            st.success(f"Loaded {len(rows)} jobs.")
        except ValueError as error:
            st.error(str(error))


if not state.user:
    login_page()
    st.stop()

record = db.load_profile(state.db, state.user.id)
if not record or not record.get("consent_at"):
    consent_page(record)
    st.stop()

profile = record["data"] or empty_profile()
pages = ["My profile", "Internships", "My packs", "Tracker", "My account"] + (["Admin"] if state.user.email == os.environ["ADMIN_EMAIL"] else [])
page = st.sidebar.radio("Go to", pages)
if st.sidebar.button("Log out"):
    db.sign_out(state.db)
    state.user = None
    st.rerun()

if page == "My profile":
    profile_page(profile)
elif page == "Internships":
    internships_page(profile)
elif page == "My packs":
    packs_page(profile)
elif page == "Tracker":
    tracker_page()
elif page == "My account":
    account_page()
else:
    admin_page()
