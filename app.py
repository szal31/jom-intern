"""Jom Intern!: a tailored, checked resume and cover letter for each internship."""
import html
import json
import os
from pathlib import Path
from datetime import date

import streamlit as st

from core import db
from core.checker import check_pack
from core.jobs import load_jobs, recommend
from core.llm import LLMError
from core.pack import build_pack, trim_to_one_page
from core.profile import empty_profile, extract_profile, merge_profile
from core.render import letter_docx, letter_pdf, resume_docx, resume_pdf
from core.resume_text import read_resume
from core.tracker import tracker_xlsx

SECRETS = ["GEMINI_API_KEY", "SUPABASE_URL", "SUPABASE_ANON_KEY", "SUPABASE_SERVICE_KEY", "ADMIN_EMAIL"]
STATUSES = ["Ready", "Applied", "Interview", "Rejected", "Offer"]
PRIVACY = """**Before you start**
- This is a pilot for up to 10 students, run by Sanad.
- Your profile, the resumes and letters you make, and your tracker are stored in a private database. Only you can see them in the app.
- As the database owner, Sanad can technically read the data, and will only look at yours if you ask for help.
- Your details are sent to Google's Gemini AI to write your documents. On the free tier, Google may use what's sent to improve its products.
- You can delete everything, including your account, at any time from **My account**."""

st.set_page_config(page_title="Jom Intern!", page_icon=":material/work:")
st.html(f"<style>{(Path(__file__).parent / 'assets' / 'jom.css').read_text(encoding='utf-8')}</style>")

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


def is_admin(email):
    return (email or "").casefold() == os.environ["ADMIN_EMAIL"].casefold()


def status_tag(status):
    """Blue applied, yellow interview, red offer: the primaries code the stage and nothing else."""
    kind = status.lower() if status in STATUSES else "ready"
    return f'<span class="jom-status jom-status--{kind}">{html.escape(status)}</span>'


def go_to(page):
    """Button callback: switch the sidebar page before it's drawn."""
    state.page = page


def profile_steps(profile):
    contact, window = profile.get("contact") or {}, profile.get("window") or {}
    return [("Name and email", bool(contact.get("name") and contact.get("email"))),
            ("Education", bool(profile.get("education"))),
            ("Experience or projects", bool(profile.get("experience") or profile.get("projects"))),
            ("At least one story", bool(profile.get("stories"))),
            ("Internship dates", bool(window.get("start") and window.get("end")))]


def login_page():
    st.html('''<div class="jom-band"><h1>Jom Intern!</h1>
      <p>Turn your resume into a tailored resume and cover letter for each internship.</p></div>''')
    seats = db.seats_left(state.db)
    st.html(f'''<div class="jom-cells">
      <div class="jom-cell"><b>{seats}</b><span>places left in the pilot</span></div>
      <div class="jom-cell"><b>{db.PACK_LIMIT_PER_DAY}</b><span>packs a day</span></div>
      <div class="jom-cell"><b>1 page</b><span>resume, plus a cover letter</span></div>
    </div>''')
    log_in, sign_up = st.tabs(["Log in", "Sign up"])
    with log_in, st.form("login"):
        email, password = st.text_input("Email"), st.text_input("Password", type="password")
        if st.form_submit_button("Log in", type="primary"):
            try:
                state.user = db.sign_in(state.db, email, password)
                st.rerun()
            except Exception as error:
                st.error(db.friendly_error(error))
    with sign_up:
        if seats == 0:
            st.info("The pilot is full.")
            return
        st.caption(f"{seats} of 10 places left.")
        with st.form("signup"):
            email, password = st.text_input("Email"), st.text_input("Password (8+ characters)", type="password")
            if st.form_submit_button("Create account", type="primary"):
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


def edit_items(label, section, fields, key, changes):
    """Edit a list of entries in the working profile; bullets are one per line. Add/remove go to `changes`."""
    st.subheader(label)
    v, bulleted = state.profile_version, key in ("exp", "proj", "lead")
    items = state.profile.get(section) or []
    for i, item in enumerate(items):
        with st.expander(item.get(fields[0]) or f"{label} {i + 1}", expanded=not item.get(fields[0])):
            for f in fields:
                item[f] = st.text_input(f.title(), item.get(f, ""), key=f"{key}{v}_{i}{f}")
            if bulleted:
                item["bullets"] = [b for b in st.text_area("Bullets (one per line)", "\n".join(item.get("bullets", [])), key=f"{key}{v}_{i}b").splitlines() if b.strip()]
            if st.button("Remove", key=f"{key}{v}_{i}rm"):
                changes.append(lambda i=i: items.pop(i))
    state.profile[section] = items
    if st.button(f"Add {label.lower()}", key=f"{key}{v}add"):
        changes.append(lambda: items.append({f: "" for f in fields} | ({"bullets": []} if bulleted else {})))


def profile_page():
    profile, v, changes = state.profile, state.profile_version, []
    st.title("My profile")
    st.caption("Everything in your resume and letters comes from here. Nothing else is added.")
    steps = profile_steps(profile)
    done = sum(ok for _, ok in steps)
    st.progress(done / len(steps), text=f"Profile {done} of {len(steps)} done")
    if done < len(steps):
        st.caption("Still to fill in: " + ", ".join(name for name, ok in steps if not ok))
    with st.container(key="uploadbox"):
        upload = st.file_uploader("Upload your current resume (PDF or Word) to fill this in", type=["pdf", "docx"])
        st.caption("Reading a resume replaces the sections it contains. Your stories, internship window and any field the resume leaves out are kept.")
        read = upload and st.button("Read my resume")
    if read:
        try:
            text = read_resume(upload.getvalue(), upload.name)
            if not text:
                st.warning("Couldn't read any text from that file. It may be a scanned image. Please fill in the sections below.")
            else:
                with st.spinner("Reading your resume..."):
                    state.profile = merge_profile(profile, extract_profile(text, llm=LLM))
                db.save_profile(state.db, state.user.id, state.profile)
                state.profile_version += 1
                st.rerun()
        except (ValueError, LLMError) as error:
            st.error(str(error))
    contact = profile.get("contact") or {}
    basics, background, skills, stories, window_tab = st.tabs(["Contact", "Education & experience", "Skills", "Stories", "Internship window"])
    with basics:
        left, right = st.columns(2)
        profile["contact"] = {f: (left if i % 2 == 0 else right).text_input(f.title(), contact.get(f, ""), key=f"c{v}{f}")
                              for i, f in enumerate(("name", "email", "phone", "location", "linkedin", "github"))}
        profile["summary"] = st.text_area("A line about you (optional)", profile.get("summary", ""), key=f"sum{v}")
    with background:
        edit_items("Education", "education", ["institution", "qualification", "dates", "grade"], "edu", changes)
        edit_items("Experience", "experience", ["title", "dates"], "exp", changes)
        edit_items("Projects", "projects", ["title", "dates", "tools"], "proj", changes)
        edit_items("Leadership & activities", "leadership", ["title", "dates"], "lead", changes)
    with skills:
        profile["skills"] = [s for s in st.text_area("Skills, one group per line (e.g. Analytics: Power BI, Excel)", "\n".join(profile.get("skills", [])), key=f"sk{v}", height=180).splitlines() if s.strip()]
        profile["languages"] = [s for s in st.text_area("Languages, one per line", "\n".join(profile.get("languages", [])), key=f"lang{v}").splitlines() if s.strip()]
    with stories:
        st.caption("3 to 5 real experiences for cover letters: a challenge, what you did, what happened.")
        edit_items("Story", "stories", ["situation", "action", "result"], "story", changes)
    window = profile.get("window") or {}
    with window_tab:
        left, right = st.columns(2)
        profile["window"] = {
            "start": left.text_input("Start date (e.g. 15 March 2027)", window.get("start", ""), key=f"ws{v}"),
            "end": right.text_input("End date (e.g. 4 July 2027)", window.get("end", ""), key=f"we{v}"),
            "weeks": left.text_input("Length in weeks (e.g. 14 to 16)", window.get("weeks", ""), key=f"ww{v}"),
            "locations": right.text_input("Locations, comma separated (e.g. Kuala Lumpur, Selangor)", window.get("locations", ""), key=f"wl{v}"),
        }
    if changes:  # applied after every field is read, so nothing typed is lost; new keys stop stale widget values
        for change in changes:
            change()
        state.profile_version += 1
        st.rerun()
    st.caption("Adding or removing an entry doesn't save. Press Save profile when you're done.")
    if st.button("Save profile", type="primary"):
        db.save_profile(state.db, state.user.id, profile)
        st.success("Saved.")


def make_pack(profile, job):
    if db.packs_today(state.db, state.user.id) >= db.PACK_LIMIT_PER_DAY:
        st.warning(f"You've made {db.PACK_LIMIT_PER_DAY} packs today. Come back tomorrow.")
        return False
    others = sorted({p["company"] for p in db.list_packs(state.db, state.user.id)} | {j["company"] for j in db.load_job_list(state.db)})
    try:
        with st.spinner("Writing and checking your resume and letter. This takes about a minute..."):
            pack, problems = build_pack(profile, job, others, llm=LLM)
            pack = trim_to_one_page(pack, lambda p: resume_pdf(profile, p)[1])
            files = {"resume.pdf": resume_pdf(profile, pack)[0], "resume.docx": resume_docx(profile, pack),
                     "letter.pdf": letter_pdf(profile, job, pack), "letter.docx": letter_docx(profile, job, pack),
                     "pack.json": json.dumps({"pack": pack, "job": job}).encode()}
            db.save_pack(state.db, state.user.id, {"company": job["company"], "role": job["role"], "link": job.get("link", ""), "problems": problems}, files)
    except LLMError as error:
        db.log_event(state.db, "llm_error", str(error)[:200])
        st.error(f"{error} Nothing was saved, and this didn't count towards today's limit.")
        return False
    except Exception as error:
        db.log_event(state.db, "pack_error", type(error).__name__)
        st.error("Something went wrong making this pack. Please try again in a minute.")
        return False
    if problems:
        db.log_event(state.db, "checker", f"{len(problems)} problems")  # counts only: problems quote the student's text
        st.warning("Saved, but please fix these before using it (My packs → Edit):\n- " + "\n- ".join(problems))
    else:
        st.success("Done. Your pack is ready.")
    return True


def internships_page(profile):
    st.title("Internships")
    if not (profile.get("contact") or {}).get("name"):
        st.write("Fill in your profile first. Your resume and letters are written only from it.")
        st.button("Go to My profile", on_click=go_to, args=("My profile",), type="primary")
        return
    recommended, own = st.tabs(["Recommended", "Paste my own"])
    with recommended:
        picks = recommend(db.load_job_list(state.db), profile, date.today())
        if not picks:
            st.write("No recommended internships right now. Use the Paste my own tab for any job ad you find.")
        for i, job in enumerate(picks):
            with st.expander(f"**{job['company']}**: {job['role']} ({job['location']})"):
                st.write(job["posting_text"][:800])
                if job["link"]:
                    st.link_button("Open posting", job["link"])
                if st.button("Make my pack", key=f"rec{i}", type="primary") and make_pack(profile, {k: job[k] for k in ("company", "role", "link", "posting_text")} | {"address": job["location"]}):
                    st.button("Open My packs", on_click=go_to, args=("My packs",), key=f"open{i}")
    made = False
    with own, st.form("own"):
        job = {"company": st.text_input("Company"), "role": st.text_input("Role (exact title)"), "link": st.text_input("Link (optional)"),
               "address": st.text_input("Office address (optional)"), "posting_text": st.text_area("Paste the job description")}
        st.caption("Paste the full job ad: the letter uses what the team does.")
        if st.form_submit_button("Make my pack", type="primary"):
            if not (job["company"] and job["role"] and job["posting_text"]):
                st.error("Company, role and job description are needed.")
            else:
                made = make_pack(profile, job)
    if made:  # outside the form: Streamlit allows callbacks only on a form's submit button
        own.button("Open My packs", on_click=go_to, args=("My packs",), key="open_own")


def packs_page(profile):
    st.title("My packs")
    packs = db.list_packs(state.db, state.user.id)
    if not packs:
        st.write("No packs yet. Each internship you pick gets its own resume and cover letter.")
        st.button("Find an internship", on_click=go_to, args=("Internships",), type="primary")
    for row in packs:
        flag = " (needs fixes)" if row.get("problems") else ""
        with st.expander(f"**{row['company']}**: {row['role']}{flag}"):
            st.html(f"{status_tag(row['status'])}<span class='jom-meta'>made {html.escape(row['created_at'][:10])}</span>")
            files = row.get("files") or {}
            for problem in row.get("problems") or []:
                st.warning(problem)
            if st.toggle("Show downloads", key=f"dl{row['id']}"):
                columns = st.columns(4)
                for column, name in zip(columns, ("resume.pdf", "resume.docx", "letter.pdf", "letter.docx")):
                    if name in files:
                        column.download_button(name, db.download(state.db, files[name]), file_name=f"{row['company']} {name}", key=f"{row['id']}{name}")
            status = st.selectbox("Status", STATUSES, STATUSES.index(row["status"]) if row["status"] in STATUSES else 0, key=f"s{row['id']}")
            notes = st.text_input("Notes", row.get("notes") or "", key=f"n{row['id']}")
            if st.button("Save status", key=f"save{row['id']}"):
                db.update_pack(state.db, row["id"], status=status, notes=notes)
                st.rerun()
            if "pack.json" in files and st.toggle("Edit resume and letter", key=f"edit{row['id']}"):
                saved = json.loads(db.download(state.db, files["pack.json"]))
                pack, job = saved["pack"], saved["job"]
                resume = pack["resume"]
                resume["summary"] = st.text_area("Resume summary", resume.get("summary", ""), key=f"rs{row['id']}")
                resume["skills"] = [s for s in st.text_area("Resume skills, one group per line", "\n".join(resume.get("skills", [])), key=f"rk{row['id']}").splitlines() if s.strip()]
                pack["letter"] = [p for p in st.text_area("Letter paragraphs (blank line between)", "\n\n".join(pack["letter"]), height=300, key=f"l{row['id']}").split("\n\n") if p.strip()]
                problems = check_pack(pack, profile, job, [])
                for problem in problems:
                    st.warning(problem)
                if st.checkbox("I've checked this and it's true", key=f"ok{row['id']}") and st.button("Save edits", key=f"sl{row['id']}"):
                    pack = trim_to_one_page(pack, lambda p: resume_pdf(profile, p)[1])
                    for name, data in {"resume.pdf": resume_pdf(profile, pack)[0], "resume.docx": resume_docx(profile, pack),
                                       "letter.pdf": letter_pdf(profile, job, pack), "letter.docx": letter_docx(profile, job, pack),
                                       "pack.json": json.dumps({"pack": pack, "job": job}).encode()}.items():
                        if name in files:
                            state.db.storage.from_("packs").upload(files[name], data, {"upsert": "true"})
                    db.update_pack(state.db, row["id"], problems=problems)
                    st.success("Saved.")


def tracker_page():
    st.title("Tracker")
    packs = db.list_packs(state.db, state.user.id)
    if not packs:
        st.write("Every pack you make is listed here with its status, ready to download as a spreadsheet.")
        st.button("Find an internship", on_click=go_to, args=("Internships",), type="primary", key="tracker_empty")
        return
    st.dataframe([{k: p.get(k) for k in ("company", "role", "status", "notes", "link")} | {"made": p["created_at"][:10]} for p in packs], use_container_width=True)
    st.download_button("Download as Excel", tracker_xlsx(packs), file_name="jom_intern_tracker.xlsx")


def account_page():
    st.title("My account")
    st.markdown(PRIVACY.replace("**Before you start**", "**Your data**").replace(" at any time from **My account**", " at any time, below"))
    st.subheader("Delete my data")
    if st.text_input("Type DELETE to remove your profile, packs, files and account") == "DELETE" and st.button("Delete everything"):
        try:
            db.delete_my_data(state.db, db.service_client(), state.user.id)
        except Exception as error:
            db.log_event(state.db, "delete_error", type(error).__name__)
            st.error("Couldn't finish deleting. Please try again, or ask Sanad to remove your account.")
            return
        state.clear()
        st.rerun()


def admin_page():
    st.title("Admin")
    admin = db.service_client()
    accounts = db.admin_accounts(admin)
    stats = db.admin_stats(admin)
    st.html(f'''<div class="jom-cells">
      <div class="jom-cell"><b>{len(accounts) - 1} of 10</b><span>students signed up</span></div>
      <div class="jom-cell"><b>{sum(row["packs"] for row in stats["usage"])}</b><span>packs made</span></div>
      <div class="jom-cell"><b>{len(stats["events"])}</b><span>recent errors and checker failures</span></div>
    </div>''')
    for account in accounts:
        left, right = st.columns([4, 1])
        left.write(f"{account['email']} (joined {account['created_at']})")
        if not is_admin(account["email"]) and right.checkbox("Delete", key=f"del{account['id']}") and right.button("Confirm", key=f"conf{account['id']}", type="primary"):
            try:
                db.admin_delete_account(admin, account["id"])
                st.rerun()
            except Exception as error:
                st.error(f"Couldn't delete that account: {type(error).__name__}. Try again.")
    st.subheader("Packs per student per day")
    if stats["usage"]:
        st.dataframe(stats["usage"], use_container_width=True)
    else:
        st.write("No packs made yet.")
    st.subheader("Recent errors and checker failures")
    if stats["events"]:
        st.dataframe(stats["events"], use_container_width=True)
    else:
        st.write("No errors or checker failures yet.")
    st.subheader("Weekly job list")
    upload = st.file_uploader("Upload `jobs_export.csv`", type="csv")
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
if state.get("profile_user") != state.user.id:  # working copy for the profile page; other pages use what's saved
    state.profile, state.profile_version, state.profile_user = json.loads(json.dumps(profile)), 0, state.user.id
pages = ["My profile", "Internships", "My packs", "Tracker", "My account"] + (["Admin"] if is_admin(state.user.email) else [])
ICONS = {"My profile": "person", "Internships": "work", "My packs": "folder_open", "Tracker": "table_chart", "My account": "manage_accounts", "Admin": "admin_panel_settings"}
st.sidebar.markdown("### Jom Intern!")
st.sidebar.caption(f"Signed in as {state.user.email}")
page = st.sidebar.radio("Go to", pages, key="page", format_func=lambda p: f":material/{ICONS[p]}: {p}", label_visibility="collapsed")
if st.sidebar.button("Log out"):
    db.sign_out(state.db)
    state.clear()
    st.rerun()

if page == "My profile":
    profile_page()
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
