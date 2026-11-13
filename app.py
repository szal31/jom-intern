"""Jom Intern!: a tailored, checked resume and cover letter for each internship."""
import copy
import hmac
import html
import json
import os
import time
from pathlib import Path
from datetime import date

import streamlit as st

from core import db, remember
from core.checker import check_pack, lines_to_check
from core.jobs import load_jobs, recommend
from core.llm import LLMError
from core.pack import build_pack, rewrite_paragraph, trim_to_one_page
from core.profile import empty_profile, extract_profile, merge_profile
from core.render import letter_docx, letter_html, letter_pdf, resume_docx, resume_html, resume_pdf
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

st.set_page_config(page_title="Jom Intern!", page_icon=":material/work:", layout="wide")
st.html(f"<style>{(Path(__file__).parent / 'assets' / 'jom.css').read_text(encoding='utf-8')}</style>")

try:
    secrets = dict(st.secrets)
except Exception:  # no secrets file yet: fall through to the "not set up" message
    secrets = {}
for name in SECRETS + ["GEMINI_MODEL", "USE_FAKE_LLM", "INVITE_CODE"]:
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
if not state.user and not state.get("cookie_checked"):  # a reload starts a new session: log back in from the remembered token
    state.cookie_checked = True
    token = remember.read()
    if token:
        try:
            state.user = db.restore(state.db, token)
            state.remember_until = remember.read_until()  # keeps the original 7-day limit, not a fresh one
        except Exception:
            state.forget_cookie = True
SETUP = ["Upload your resume", "Check your details", "Add your stories", "Your internship window"]


def is_admin(email):
    return (email or "").casefold() == os.environ["ADMIN_EMAIL"].casefold()


def status_tag(status):
    """Blue applied, yellow interview, red offer: the primaries code the stage and nothing else."""
    kind = status.lower() if status in STATUSES else "ready"
    return f'<span class="jom-status jom-status--{kind}">{html.escape(status)}</span>'


def go_to(page):
    """Button callback: switch the page before the nav is drawn."""
    state.page = page


def log_out():
    """Clear the session; the next run (the login page) also clears the remembered cookie."""
    state.clear()
    state.cookie_checked, state.forget_cookie = True, True


def profile_steps(profile):
    contact, window = profile.get("contact") or {}, profile.get("window") or {}
    return [("Name and email", bool(contact.get("name") and contact.get("email"))),
            ("Education", bool(profile.get("education"))),
            ("Experience or projects", bool(profile.get("experience") or profile.get("projects"))),
            ("At least one story", bool(profile.get("stories"))),
            ("Internship dates", bool(window.get("start") and window.get("end")))]


def login_page():
    if state.pop("forget_cookie", False):
        remember.clear()
    st.container(key="login").html('''<div class="jom-hero"><h1>Jom Intern!</h1>
      <p>Turn your resume into a tailored resume and cover letter for each internship.</p></div>''')
    log_in, sign_up = st.container(key="loginforms").tabs(["Log in", "Sign up"])
    with log_in, st.form("login"):
        email, password = st.text_input("Email"), st.text_input("Password", type="password")
        keep = st.checkbox("Keep me logged in on this device for 7 days", help="Leave this off on shared or lab computers.")
        if st.form_submit_button("Log in", type="primary"):
            try:
                state.user = db.sign_in(state.db, email, password)
                state.remember_until = time.time() + remember.WEEK if keep else None
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
            invite = st.text_input("Invite code", help="Ask Sanad for the pilot's invite code.") if os.environ.get("INVITE_CODE") else ""
            if st.form_submit_button("Create account", type="primary"):
                if os.environ.get("INVITE_CODE") and not hmac.compare_digest(invite.strip(), os.environ["INVITE_CODE"]):
                    st.error("That invite code isn't right. Ask Sanad for the pilot's code.")
                    return
                try:
                    with st.spinner("Creating your account and sending the confirmation email. This takes about 10 seconds..."):
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


def apply_changes(changes):
    """Add/remove clicks run after every field is read, so nothing typed is lost; new keys stop stale widget values."""
    if changes:
        for change in changes:
            change()
        state.profile_version += 1
        st.rerun()


def upload_box(profile, then_step=None):
    with st.container(key="uploadbox"):
        upload = st.file_uploader("Upload your current resume (PDF or Word) to fill this in", type=["pdf", "docx"])
        st.caption("Reading a resume replaces the sections it contains. Your stories, internship window and any field the resume leaves out are kept.")
        read = upload and st.button("Read my resume", type="primary" if then_step is not None else "secondary")
    if read:
        try:
            text = read_resume(upload.getvalue(), upload.name)
            if not text:
                st.warning("Couldn't read any text from that file. It may be a scanned image. Please fill in the sections yourself.")
            else:
                with st.spinner("Reading your resume..."):
                    state.profile = merge_profile(profile, extract_profile(text, llm=LLM))
                db.save_profile(state.db, state.user.id, state.profile)
                state.profile_version += 1
                if then_step is not None:
                    state.setup_step = then_step
                st.rerun()
        except (ValueError, LLMError) as error:
            st.error(str(error))


def contact_fields(profile, v):
    contact = profile.get("contact") or {}
    left, right = st.columns(2)
    profile["contact"] = {f: (left if i % 2 == 0 else right).text_input(f.title(), contact.get(f, ""), key=f"c{v}{f}")
                          for i, f in enumerate(("name", "email", "phone", "location", "linkedin", "github"))}
    profile["summary"] = st.text_area("A line about you (optional)", profile.get("summary", ""), key=f"sum{v}")


def background_fields(changes):
    edit_items("Education", "education", ["institution", "qualification", "dates", "grade"], "edu", changes)
    edit_items("Experience", "experience", ["title", "dates"], "exp", changes)
    edit_items("Projects", "projects", ["title", "dates", "tools"], "proj", changes)
    edit_items("Leadership & activities", "leadership", ["title", "dates"], "lead", changes)


def skills_fields(profile, v):
    profile["skills"] = [s for s in st.text_area("Skills, one group per line (e.g. Analytics: Power BI, Excel)", "\n".join(profile.get("skills", [])), key=f"sk{v}", height=180).splitlines() if s.strip()]
    profile["languages"] = [s for s in st.text_area("Languages, one per line", "\n".join(profile.get("languages", [])), key=f"lang{v}").splitlines() if s.strip()]


def stories_fields(changes):
    st.caption("3 to 5 real experiences for cover letters: a challenge, what you did, what happened.")
    edit_items("Story", "stories", ["situation", "action", "result"], "story", changes)


def window_fields(profile, v):
    window = profile.get("window") or {}
    left, right = st.columns(2)
    profile["window"] = {
        "start": left.text_input("Start date (e.g. 15 March 2027)", window.get("start", ""), key=f"ws{v}"),
        "end": right.text_input("End date (e.g. 4 July 2027)", window.get("end", ""), key=f"we{v}"),
        "weeks": left.text_input("Length in weeks (e.g. 14 to 16)", window.get("weeks", ""), key=f"ww{v}"),
        "locations": right.text_input("Locations, comma separated (e.g. Kuala Lumpur, Selangor)", window.get("locations", ""), key=f"wl{v}"),
    }


def needs_setup(profile):
    return not profile.get("setup_done") and not state.get("setup_skipped") and not all(ok for _, ok in profile_steps(profile))


def finish_setup(profile):
    profile["setup_done"] = True
    db.save_profile(state.db, state.user.id, profile)
    state.setup_skipped, state.setup_step = True, 0
    st.rerun()


def setup_page():
    """First visit: the profile one step at a time instead of one long form."""
    profile, v, changes = state.profile, state.profile_version, []
    step = state.get("setup_step", 0)
    st.title("Set up your profile")
    st.progress((step + 1) / len(SETUP), text=f"Step {step + 1} of {len(SETUP)}: {SETUP[step]}")
    if step == 0:
        st.write("Start with the resume you already have. We read it into sections you can check on the next step.")
        upload_box(profile, then_step=1)
    elif step == 1:
        st.write("Check what we read, and fill in anything missing. Your resume and letters use only what's here.")
        contact_fields(profile, v)
        background_fields(changes)
        skills_fields(profile, v)
    elif step == 2:
        stories_fields(changes)
    else:
        st.write("Your real internship dates. Letters always state these, whatever a posting asks for.")
        window_fields(profile, v)
    apply_changes(changes)
    row = st.container(horizontal=True, key="setupnav")
    back = forward = skip = row
    if step > 0 and back.button("Back", key="setup_back"):
        db.save_profile(state.db, state.user.id, profile)
        state.setup_step = step - 1
        st.rerun()
    if forward.button("Finish" if step == len(SETUP) - 1 else "Next", type="primary", key="setup_next"):
        if step == len(SETUP) - 1:
            finish_setup(profile)
        db.save_profile(state.db, state.user.id, profile)
        state.setup_step = step + 1
        st.rerun()
    if skip.button("Skip setup", type="tertiary", key="setup_skip"):
        finish_setup(profile)


def profile_page():
    profile, v, changes = state.profile, state.profile_version, []
    st.title("My profile")
    st.caption("Everything in your resume and letters comes from here. Nothing else is added.")
    steps = profile_steps(profile)
    done = sum(ok for _, ok in steps)
    st.progress(done / len(steps), text=f"Profile {done} of {len(steps)} done")
    if done < len(steps):
        st.caption("Still to fill in: " + ", ".join(name for name, ok in steps if not ok))
    upload_box(profile)
    basics, background, skills, stories, window_tab = st.tabs(["Contact", "Education & experience", "Skills", "Stories", "Internship window"])
    with basics:
        contact_fields(profile, v)
    with background:
        background_fields(changes)
    with skills:
        skills_fields(profile, v)
    with stories:
        stories_fields(changes)
    with window_tab:
        window_fields(profile, v)
    apply_changes(changes)
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
        with st.status("Making your pack. This takes up to a minute.", expanded=True) as progress:
            pack, problems = build_pack(profile, job, others, llm=LLM, step=st.write)
            st.write("Fitting your resume on one page")
            pack = trim_to_one_page(pack, lambda p: resume_pdf(profile, p)[1])
            files = {"resume.pdf": resume_pdf(profile, pack)[0], "resume.docx": resume_docx(profile, pack),
                     "letter.pdf": letter_pdf(profile, job, pack), "letter.docx": letter_docx(profile, job, pack),
                     "pack.json": json.dumps({"pack": pack, "job": job}).encode()}
            st.write("Saving your files")
            db.save_pack(state.db, state.user.id, {"company": job["company"], "role": job["role"], "link": job.get("link", ""), "problems": problems}, files)
            progress.update(label="Saved, with things to fix" if problems else "Your pack is ready", state="complete", expanded=False)
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
        st.warning("Saved, but please fix these before using it (My packs, then Open pack, then Edit):\n- " + "\n- ".join(problems))
    else:
        st.success("Done. Your pack is ready.")
    return True


def internships_page(profile):
    st.title("Internships")
    if not (profile.get("contact") or {}).get("name"):
        st.write("Fill in your profile first. Your resume and letters are written only from it.")
        st.button("Go to My profile", on_click=go_to, args=("My profile",), type="primary")
        return
    picks = recommend(db.load_job_list(state.db), profile, date.today())
    if picks:
        recommended, own = st.tabs(["Recommended", "Paste my own"], default="Recommended")
    else:
        st.write("No recommended internships for your locations this week. Paste any job ad you find, from LinkedIn, JobStreet or a company site.")
        recommended, own = None, st.container()
    for i, job in enumerate(picks):
        with recommended, st.expander(f"**{job['company']}**: {job['role']} ({job['location']})"):
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
            if "pack.json" in files and st.toggle("Open pack", key=f"open{row['id']}"):
                pack_view(row, profile)
            if st.toggle("Show downloads", key=f"dl{row['id']}"):
                columns = st.columns(4)
                for column, name in zip(columns, ("resume.pdf", "resume.docx", "letter.pdf", "letter.docx")):
                    if name in files:
                        column.download_button(name, db.download(state.db, files[name]), file_name=f"{row['company']} {name}", key=f"{row['id']}{name}")
            left, right, button = st.columns([1, 2, 1], vertical_alignment="bottom")
            status = left.selectbox("Status", STATUSES, STATUSES.index(row["status"]) if row["status"] in STATUSES else 0, key=f"s{row['id']}")
            notes = right.text_input("Notes", row.get("notes") or "", key=f"n{row['id']}")
            if button.button("Save status", key=f"save{row['id']}"):
                db.update_pack(state.db, row["id"], status=status, notes=notes)
                st.rerun()


def pack_view(row, profile):
    """The pack on screen: resume and letter side by side with lines to check marked, and an editor beside the job ad."""
    key = f"pk{row['id']}"
    if key not in state:  # downloaded once per session; edits live here until saved
        saved = json.loads(db.download(state.db, row["files"]["pack.json"]))
        state[key] = {"pack": saved["pack"], "job": saved["job"], "v": 0,
                      "items": {s: copy.deepcopy(saved["pack"]["resume"].get(s) or []) for s in ("experience", "projects", "leadership")}}
    data = state[key]
    preview, edit = st.tabs(["Preview", "Edit"], key=f"tabs{row['id']}")
    with edit:  # drawn first so the preview shows this run's edits
        edit_pack(row, profile, data)
    with preview:
        pack, job = data["pack"], data["job"]
        marked = lines_to_check(pack, profile)
        st.caption("Highlighted lines were reworded by the AI or state a fact. Read each one against your profile before you send anything.")
        left, right = st.columns(2)
        left.html(resume_html(profile, pack, marked))
        right.html(letter_html(profile, job, pack, marked))


def edit_pack(row, profile, data):
    pack, job, v, rid = data["pack"], data["job"], data["v"], row["id"]
    resume = pack["resume"]
    main, side = st.columns([3, 2], gap="large")
    rewrite = None
    with side:
        st.markdown("**Job ad**")
        st.write(job.get("posting_text") or "No job ad was saved with this pack.")
        if job.get("link"):
            st.link_button("Open posting", job["link"])
    with main:
        resume["summary"] = st.text_area("Resume summary", resume.get("summary", ""), key=f"rs{rid}{v}")
        resume["skills"] = [s for s in st.text_area("Resume skills, one group per line", "\n".join(resume.get("skills", [])), key=f"rk{rid}{v}").splitlines() if s.strip()]
        for section, label in (("experience", "Experience"), ("projects", "Projects"), ("leadership", "Leadership & activities")):
            items = data["items"][section]
            if not items:
                continue
            order = st.multiselect(f"{label} on the resume, in order", list(range(len(items))), default=list(range(len(items))),
                                   format_func=lambda i, items=items: items[i].get("title", ""), key=f"ord{section}{rid}{v}",
                                   help="Remove an entry to leave it out. Remove it and add it back to move it to the end.")
            for i in order:
                items[i]["bullets"] = [b for b in st.text_area(f"{items[i].get('title', '')}: bullets, one per line", "\n".join(items[i].get("bullets", [])),
                                                                key=f"b{section}{i}{rid}{v}").splitlines() if b.strip()]
            resume[section] = [items[i] for i in order]
        st.markdown("**Cover letter**")
        for i, paragraph in enumerate(pack["letter"]):
            pack["letter"][i] = st.text_area(f"Paragraph {i + 1}", paragraph, key=f"lp{i}{rid}{v}", height=120)
            ask, go = st.columns([3, 1], vertical_alignment="bottom")
            how = ask.text_input("How should it change? (optional)", key=f"how{i}{rid}{v}", placeholder="e.g. shorter, or mention my RAG project")
            if go.button("Rewrite", key=f"rw{i}{rid}{v}"):
                rewrite = (i, how)
    if rewrite:
        i, how = rewrite
        try:
            with st.spinner("Rewriting the paragraph..."):
                pack["letter"][i] = rewrite_paragraph(pack["letter"][i], profile, job, how, llm=LLM)
            data["v"] += 1
            st.rerun()
        except LLMError as error:
            st.error(str(error))
    pack["letter"] = [p for p in pack["letter"] if p.strip()]
    problems = check_pack(pack, profile, job, [])
    for problem in problems:
        st.warning(problem)
    if st.checkbox("I've checked this and it's true", key=f"ok{rid}{v}") and st.button("Save edits", key=f"sl{rid}{v}", type="primary"):
        files = row.get("files") or {}
        saved = trim_to_one_page(copy.deepcopy(pack), lambda p: resume_pdf(profile, p)[1])
        for name, content in {"resume.pdf": resume_pdf(profile, saved)[0], "resume.docx": resume_docx(profile, saved),
                              "letter.pdf": letter_pdf(profile, job, saved), "letter.docx": letter_docx(profile, job, saved),
                              "pack.json": json.dumps({"pack": saved, "job": job}).encode()}.items():
            if name in files:
                state.db.storage.from_("packs").upload(files[name], content, {"upsert": "true"})
        db.update_pack(state.db, rid, problems=problems)
        st.success("Saved. Your downloads now have these edits.")


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
    st.caption(f"Signed in as {state.user.email}")
    st.markdown(PRIVACY.replace("**Before you start**", "**Your data**").replace(" at any time from **My account**", " at any time, below"))
    st.subheader("Delete my data")
    if st.text_input("Type DELETE to remove your profile, packs, files and account") == "DELETE" and st.button("Delete everything"):
        try:
            db.delete_my_data(state.db, db.service_client(), state.user.id)
        except Exception as error:
            db.log_event(state.db, "delete_error", type(error).__name__)
            st.error("Couldn't finish deleting. Please try again, or ask Sanad to remove your account.")
            return
        log_out()
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
try:  # the refresh token rotates; keep the browser's copy current so a reload logs straight back in
    token = db.session_token(state.db)
except Exception:
    token = None
if token and state.get("remember_until") and token != state.get("saved_token"):
    remember.write(token, state.remember_until)
    state.saved_token = token
with st.container(key="topbar", horizontal=True, horizontal_alignment="distribute", vertical_alignment="center", wrap=False):
    st.html('<p class="jom-brand">Jom Intern!</p>', width="content")
    if st.button("Log out", key="logout"):
        db.sign_out(state.db)
        log_out()
        st.rerun()
page = st.container(key="nav").radio("Go to", pages, key="page", horizontal=True, width="stretch", label_visibility="collapsed",
                                     format_func=lambda p: f":material/{ICONS[p]}: {p}")

if page == "My profile":
    if needs_setup(state.profile):
        setup_page()
    else:
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
