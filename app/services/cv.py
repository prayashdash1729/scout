"""
CV handling: extract text from an uploaded PDF, and have Gemini distil skills +
suggested target roles during onboarding.
"""

from __future__ import annotations

import asyncio
import io
import logging

import PyPDF2

from app.schemas import CVInsights
from app.services.gemini import generate_structured

log = logging.getLogger(__name__)

MIN_CV_CHARS = 100


def _extract_text_sync(pdf_bytes: bytes) -> str:
    reader = PyPDF2.PdfReader(io.BytesIO(pdf_bytes))
    return "\n".join((page.extract_text() or "") for page in reader.pages).strip()


async def extract_text(pdf_bytes: bytes) -> str:
    """Pull raw text from a PDF. Raises ValueError if it's too short/image-only."""
    text = await asyncio.to_thread(_extract_text_sync, pdf_bytes)
    if len(text) < MIN_CV_CHARS:
        raise ValueError(
            "Couldn't read enough text from that PDF — it may be image-based. "
            "Please send a text-based PDF."
        )
    return text


_INSIGHTS_PROMPT = """\
You are a career assistant. Read the candidate's CV below and extract a concise
profile. Be realistic about the roles a candidate at this level can target.

## CV
{cv}

Return the skills found, 3-6 realistic target job titles, the best estimate of
total years of professional experience, and a one-line summary.
"""


async def extract_insights(cv_text: str) -> CVInsights:
    prompt = _INSIGHTS_PROMPT.format(cv=cv_text[:20000])
    return await generate_structured(prompt, CVInsights, temperature=0.3)
