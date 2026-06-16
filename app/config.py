"""
Central configuration. All settings come from environment / .env and are
validated through a single Pydantic model so the rest of the app can rely on
correct types and fail fast on a bad config.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv
from pydantic import BaseModel, Field, field_validator, model_validator

load_dotenv()


def _resolve_path(p: str | None) -> str | None:
    """Make a credentials path absolute if it exists relative to the cwd."""
    if not p:
        return None
    return os.path.abspath(p) if os.path.exists(p) else p


def _split_ids(raw: str | None) -> list[int]:
    if not raw:
        return []
    out: list[int] = []
    for part in raw.replace(";", ",").split(","):
        part = part.strip()
        if part:
            out.append(int(part))
    return out


def _split_usernames(raw: str | None) -> list[str]:
    if not raw:
        return []
    out: list[str] = []
    for part in raw.replace(";", ",").split(","):
        # Usernames are case-insensitive; normalise and drop a leading '@'.
        part = part.strip().lstrip("@").lower()
        if part:
            out.append(part)
    return out


class Settings(BaseModel):
    # ── Telegram ──────────────────────────────────────────
    telegram_bot_token: str
    telegram_bot_username: str = ""

    # ── Gemini (google.genai) ─────────────────────────────
    # backend: "vertex" => service-account auth via Vertex AI; "api" => GEMINI_API_KEY
    gemini_backend: str = "vertex"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    google_cloud_project: str | None = None
    vertex_location: str = "us-central1"
    google_application_credentials: str | None = None

    # ── Jina (search + reader) ────────────────────────────
    jina_api_key: str

    # ── Job sources ───────────────────────────────────────
    scraper_api_key: str | None = None
    fetch_country: str = "in"          # ScraperAPI country_code for geo-routing
    scraper_first: bool = False        # try ScraperAPI before a direct hit
    jina_enabled: bool = True
    linkedin_enabled: bool = True
    naukri_enabled: bool = False       # blocked by anti-bot; off until viable
    # LinkedIn guest-API filters (see app/services/linkedin.py)
    linkedin_tpr: str = "r604800"      # posted within: r86400=24h, r604800=7d
    linkedin_experience: str = "1,2,3"  # f_E: 1 intern,2 entry,3 associate,...
    linkedin_job_type: str = "F"        # f_JT: F full-time, C contract, I intern
    linkedin_pages: int = 2            # pages of 10 cards per role×city query

    # ── Database ──────────────────────────────────────────
    database_url: str

    # ── Access control & limits ───────────────────────────
    allowed_telegram_ids: list[int] = Field(default_factory=list)
    allowed_telegram_usernames: list[str] = Field(default_factory=list)
    score_threshold: int = 7
    hunt_cooldown_minutes: int = 30
    max_hunts_per_day: int = 10
    max_links_per_hunt: int = 40
    search_top_k: int = 10
    max_queries_per_hunt: int = 24
    hunt_concurrency: int = 3  # keep low: Vertex gemini-2.5-flash quota is tight

    @field_validator("database_url")
    @classmethod
    def _normalise_db_url(cls, v: str) -> str:
        # Accept a plain postgres:// URL and upgrade it to the asyncpg driver.
        if v.startswith("postgresql://"):
            return v.replace("postgresql://", "postgresql+asyncpg://", 1)
        if v.startswith("postgres://"):
            return v.replace("postgres://", "postgresql+asyncpg://", 1)
        return v

    @model_validator(mode="after")
    def _check_gemini_backend(self) -> "Settings":
        if self.gemini_backend == "vertex":
            if not self.google_cloud_project:
                raise ValueError("GEMINI_BACKEND=vertex requires GOOGLE_CLOUD_PROJECT")
            if not self.google_application_credentials:
                raise ValueError(
                    "GEMINI_BACKEND=vertex requires GOOGLE_APPLICATION_CREDENTIALS"
                )
        elif self.gemini_backend == "api":
            if not self.gemini_api_key:
                raise ValueError("GEMINI_BACKEND=api requires GEMINI_API_KEY")
        else:
            raise ValueError("GEMINI_BACKEND must be 'vertex' or 'api'")
        return self

    @property
    def access_is_restricted(self) -> bool:
        return bool(self.allowed_telegram_ids or self.allowed_telegram_usernames)


def _load() -> Settings:
    return Settings(
        telegram_bot_token=os.environ["TELEGRAM_BOT_TOKEN"],
        telegram_bot_username=os.getenv("TELEGRAM_BOT_USERNAME", ""),
        gemini_backend=os.getenv("GEMINI_BACKEND", "vertex").strip().lower(),
        gemini_api_key=os.getenv("GEMINI_API_KEY", ""),
        gemini_model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
        google_cloud_project=os.getenv("GOOGLE_CLOUD_PROJECT"),
        vertex_location=os.getenv("VERTEX_LOCATION", "us-central1"),
        google_application_credentials=_resolve_path(
            os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        ),
        jina_api_key=os.environ["JINA_API_KEY"],
        scraper_api_key=os.getenv("SCRAPER_API_KEY") or None,
        fetch_country=os.getenv("FETCH_COUNTRY", "in"),
        scraper_first=os.getenv("SCRAPER_FIRST", "false").strip().lower() == "true",
        jina_enabled=os.getenv("JINA_ENABLED", "true").strip().lower() == "true",
        linkedin_enabled=os.getenv("LINKEDIN_ENABLED", "true").strip().lower() == "true",
        naukri_enabled=os.getenv("NAUKRI_ENABLED", "false").strip().lower() == "true",
        linkedin_tpr=os.getenv("LINKEDIN_TPR", "r604800"),
        linkedin_experience=os.getenv("LINKEDIN_EXPERIENCE", "1,2,3"),
        linkedin_job_type=os.getenv("LINKEDIN_JOB_TYPE", "F"),
        linkedin_pages=int(os.getenv("LINKEDIN_PAGES", "2")),
        database_url=os.getenv(
            "DATABASE_URL",
            "postgresql+asyncpg://jobpilot:jobpilot@localhost:5432/jobpilot",
        ),
        allowed_telegram_ids=_split_ids(os.getenv("ALLOWED_TELEGRAM_IDS")),
        allowed_telegram_usernames=_split_usernames(
            os.getenv("ALLOWED_TELEGRAM_USERNAMES")
        ),
        score_threshold=int(os.getenv("SCORE_THRESHOLD", "7")),
        hunt_cooldown_minutes=int(os.getenv("HUNT_COOLDOWN_MINUTES", "30")),
        max_hunts_per_day=int(os.getenv("MAX_HUNTS_PER_DAY", "10")),
        max_links_per_hunt=int(os.getenv("MAX_LINKS_PER_HUNT", "40")),
        search_top_k=int(os.getenv("SEARCH_TOP_K", "10")),
        max_queries_per_hunt=int(os.getenv("MAX_QUERIES_PER_HUNT", "24")),
        hunt_concurrency=int(os.getenv("HUNT_CONCURRENCY", "3")),
    )


settings = _load()
