"""
Pydantic schemas.

Two jobs here:
  1. Structured-output contracts for Gemini (CVInsights, JobEvaluation) — passed
     directly to google.genai as `response_schema`, so the model is forced to
     return validated JSON (no markdown-fence stripping).
  2. Lightweight transfer objects between layers (SearchHit).
"""

from __future__ import annotations

import re
from typing import Optional

from pydantic import BaseModel, Field, field_validator


# ── Gemini: CV understanding ──────────────────────────────────────────────
class CVInsights(BaseModel):
    """Extracted from the candidate's CV during onboarding."""

    skills: list[str] = Field(
        default_factory=list,
        description="Concrete technical skills/tools found in the CV.",
    )
    suggested_roles: list[str] = Field(
        default_factory=list,
        description="3-6 job titles this candidate should realistically target.",
    )
    experience_years: int = Field(
        0, description="Best estimate of total professional experience in years."
    )
    summary: str = Field(
        "", description="One or two sentences summarising the candidate."
    )


# ── Gemini: per-job evaluation ────────────────────────────────────────────
class JobEvaluation(BaseModel):
    """Gemini's verdict on one rendered page vs the candidate's CV."""

    is_job_posting: bool = Field(
        ..., description="True only if the page is a single concrete job opening."
    )
    score: int = Field(..., description="Fit score 0-10 (10 = perfect fit).", ge=0, le=10)
    reason: str = Field(..., description="2-3 sentence justification of the score.")
    title: str = Field("", description="Clean job title.")
    company: str = Field("", description="Hiring company name.")
    location: str = Field("", description="Job location / city.")
    apply_link: str = Field(
        "", description="Direct apply URL or the canonical job-posting URL."
    )
    posting_date: Optional[str] = Field(
        None, description="Date the job was posted, if stated (ISO YYYY-MM-DD preferred)."
    )
    job_key: str = Field(
        ...,
        description=(
            "Stable unique id for this job as 'companyslug|jobid'. companyslug = "
            "company name lowercased with non-alphanumerics removed. jobid = the "
            "posting id from the URL/page if present, else a short slug of the title."
        ),
    )

    @field_validator("job_key")
    @classmethod
    def _normalise_key(cls, v: str) -> str:
        v = (v or "").strip().lower()
        if "|" not in v:
            v = re.sub(r"[^a-z0-9]+", "", v) + "|unknown"
        company, _, jid = v.partition("|")
        company = re.sub(r"[^a-z0-9]+", "", company) or "unknown"
        jid = re.sub(r"[^a-z0-9]+", "", jid) or "unknown"
        return f"{company}|{jid}"


# ── Internal transfer object ──────────────────────────────────────────────
class JobCandidate(BaseModel):
    """
    A job discovered by a source (LinkedIn / Naukri / Jina) before scoring.

    Board sources (LinkedIn/Naukri) provide a stable `job_key` (e.g.
    'linkedin|4400723087') and metadata up front, so we can dedup against the DB
    *before* spending any fetch/LLM calls. Jina results have job_key=None and the
    key is derived by Gemini after scoring. `content` holds the JD text when the
    source already has it; otherwise it's fetched lazily before scoring.
    """

    source: str = "other"      # display board (linkedin/naukri/wellfound/…) for storage
    origin: str = ""           # registry adapter that produced it (for JD-fetch dispatch)
    url: str
    job_key: Optional[str] = None
    title: str = ""
    company: str = ""
    location: str = ""
    posting_date: Optional[str] = None
    content: str = ""
