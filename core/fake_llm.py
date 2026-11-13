"""A stand-in model for local testing (USE_FAKE_LLM=1), so building the app spends no Gemini quota."""
import json


def fake_llm(prompt: str) -> str:
    if prompt.startswith("Extract this resume"):
        return json.dumps({
            "contact": {"name": "Test Student", "email": "test@example.com"},
            "education": [{"institution": "UiTM", "qualification": "BSc Mathematics", "dates": "2025 to 2027", "grade": "CGPA 3.50"}],
            "projects": [{"title": "Sales Dashboard", "dates": "2026", "tools": "Power BI", "bullets": ["Built a sales report in Power BI"]}],
            "skills": ["Analytics: Power BI, Excel"],
        })
    if prompt.startswith("Check every resume bullet"):
        return json.dumps({"untraceable": []})
    if prompt.startswith("Rewrite this one"):
        return json.dumps({"paragraph": "I built a sales report in Power BI, and I would bring that care to this team."})
    job = json.loads(prompt.rsplit("JOB:\n", 1)[1])
    return json.dumps({
        "resume": {"summary": "Mathematics student who builds clear reports.", "skills": ["Analytics: Power BI, Excel"], "experience": [],
                   "projects": [{"title": "Sales Dashboard", "dates": "2026", "bullets": ["Built a sales report in Power BI"]}], "leadership": []},
        "letter": [f"I am applying for the {job['role']} position at {job['company']}.", "I built a sales report in Power BI.",
                   "I work well in a team.", f"I would like to learn at {job['company']}.", "Thank you for considering my application."],
    })
