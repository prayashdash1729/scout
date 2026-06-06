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

    # ── Database ──────────────────────────────────────────
    database_url: str

    # ── Access control & limits ───────────────────────────
    allowed_telegram_ids: list[int] = Field(default_factory=list)
    score_threshold: int = 7
    hunt_cooldown_minutes: int = 30
    max_hunts_per_day: int = 10
    max_links_per_hunt: int = 40
    search_top_k: int = 10
    max_queries_per_hunt: int = 24
    hunt_concurrency: int = 5

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
        return len(self.allowed_telegram_ids) > 0


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
        database_url=os.getenv(
            "DATABASE_URL",
            "postgresql+asyncpg://jobpilot:jobpilot@localhost:5432/jobpilot",
        ),
        allowed_telegram_ids=_split_ids(os.getenv("ALLOWED_TELEGRAM_IDS")),
        score_threshold=int(os.getenv("SCORE_THRESHOLD", "7")),
        hunt_cooldown_minutes=int(os.getenv("HUNT_COOLDOWN_MINUTES", "30")),
        max_hunts_per_day=int(os.getenv("MAX_HUNTS_PER_DAY", "10")),
        max_links_per_hunt=int(os.getenv("MAX_LINKS_PER_HUNT", "40")),
        search_top_k=int(os.getenv("SEARCH_TOP_K", "10")),
        max_queries_per_hunt=int(os.getenv("MAX_QUERIES_PER_HUNT", "24")),
        hunt_concurrency=int(os.getenv("HUNT_CONCURRENCY", "5")),
    )


settings = _load()
