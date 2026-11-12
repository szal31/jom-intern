# Internship Pack

A Streamlit app that turns a student's resume into a tailored, checked resume and cover letter for each internship, with a personal tracker. Pilot for up to 10 students.

## How it works
- Students sign up (10 accounts maximum), agree to the privacy note, then upload their resume. Gemini reads it into editable sections.
- For each internship (recommended from a weekly list, or pasted), Gemini rewords only the student's own profile text into a resume and a cover letter. A second Gemini pass flags any sentence it can't trace to the profile, and a rule-based checker looks for other companies' names, dates outside the student's window, numbers not in their profile, and invented titles or skills.
- Files are made as Word and one-page PDF, saved privately per student in Supabase, and listed in an Excel-downloadable tracker.

## Setup
1. **Supabase:** create a free project. In the SQL editor, run `supabase/schema.sql`. Under Authentication, keep email sign-up on. Turning off "Confirm email" makes the pilot simpler.
2. **Gemini:** create an API key in Google AI Studio.
3. **Secrets:** create `.streamlit/secrets.toml` (never commit it):
   ```toml
   GEMINI_API_KEY = "..."
   GEMINI_MODEL = "gemini-2.5-flash"
   SUPABASE_URL = "https://<project>.supabase.co"
   SUPABASE_ANON_KEY = "..."
   SUPABASE_SERVICE_KEY = "..."
   ADMIN_EMAIL = "you@example.com"
   ```
4. **Run locally:** `py -3.14 -m venv .venv`, `.venv\Scripts\pip install -r requirements.txt`, `.venv\Scripts\streamlit run app.py`. Add `USE_FAKE_LLM = "1"` to secrets to try it without using Gemini quota.
5. **Deploy:** push to GitHub, create an app on Streamlit Community Cloud with Python 3.14, and paste the same secrets.

## Tests
`.venv\Scripts\python -m pytest -q`
