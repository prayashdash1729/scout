import os
from dotenv import load_dotenv

load_dotenv()

# ── API Keys ──────────────────────────────────────────────
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
GROQ_API_KEY      = os.getenv("GROQ_API_KEY")
SERP_API_KEY      = os.getenv("SERPAPI_API_KEY")
GEMINI_API_KEY      = os.getenv("GEMINI_API_KEY")
GOOGLE_CLOUD_PROJECT = os.getenv("GOOGLE_CLOUD_PROJECT", "mindful-ship-232907")
TAVILY_API_KEY      = os.getenv("TAVILY_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID")

# ── Your Profile ──────────────────────────────────────────
# CANDIDATE = {
#     "name": "Prayash Dash",
#     "cv_path": "cv/resume.pdf",
#     "target_roles": [
#         "Data Scientist", "ML Engineer", "Junior Data Scientist",
#         "Machine Learning Engineer", "AI Engineer", "NLP Engineer"
#         # TODO: add more role variations
#     ],
#     "target_cities": ["Bangalore", "Gurgaon", "Noida"],
#     "experience_years": 1,
#     "skills": [
#         "Python", "Machine Learning", "Deep Learning", "NLP",
#         "TensorFlow", "PyTorch", "SQL", "pandas", "scikit-learn"
#         # TODO: add skills
#     ],
#     "min_score_to_notify": 7, # TODO: how to decide this?
# }

CANDIDATE = {
    "name": "Vedant Pradhan",
    "cv_path": "cv/resume.pdf",
    "target_roles": [
        "AI Engineer", "Machine Learning Engineer", "Data Scientist"
    ],
    "target_cities": ["Bangalore", "Gurgaon", "Noida", "Pune"],
    "experience_years": 0,
    "skills": [
        "Python", "Machine Learning", "Deep Learning", "NLP",
        "TensorFlow", "PyTorch", "SQL", "pandas", "scikit-learn",
        "LangGraph", "LangChain", "LangSmith", "FastAPI"
    ],
    "min_score_to_notify": 7, # TODO: how to decide this?
}

# ── Job Boards ────────────────────────────────────────────
# These are Tavily search templates.
# {role} and {city} are filled at runtime.
JOB_SEARCH_QUERIES = [
    "{role} jobs in {city} site:linkedin.com",
    "{role} jobs in {city} site:instahyre.com",
    "{role} jobs in {city} site:naukri.com",
    "{role} jobs in {city} site:wellfound.com",
    "{role} jobs {city} India 2026",
]

# ── Memory ────────────────────────────────────────────────
DB_PATH = "memory/jobs.db"

# ── Scoring ───────────────────────────────────────────────
SCORE_THRESHOLD = 7   # jobs below this are auto-discarded silently