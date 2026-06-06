"""
Thin wrapper around google.genai for structured (Pydantic) generation.

google.genai can take a Pydantic model as `response_schema` and return a
validated instance on `response.parsed` — so callers get typed objects with no
JSON parsing or markdown-fence stripping. The blocking SDK call is pushed to a
worker thread so it doesn't stall the bot's event loop.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Type, TypeVar

from google import genai
from google.genai import types
from pydantic import BaseModel

from app.config import settings

log = logging.getLogger(__name__)


def _build_client() -> genai.Client:
    if settings.gemini_backend == "vertex":
        # google.genai reads ADC from GOOGLE_APPLICATION_CREDENTIALS.
        if settings.google_application_credentials:
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = (
                settings.google_application_credentials
            )
        log.info(
            "Gemini: Vertex backend (project=%s, location=%s, model=%s)",
            settings.google_cloud_project,
            settings.vertex_location,
            settings.gemini_model,
        )
        return genai.Client(
            vertexai=True,
            project=settings.google_cloud_project,
            location=settings.vertex_location,
        )
    log.info("Gemini: API-key backend (model=%s)", settings.gemini_model)
    return genai.Client(api_key=settings.gemini_api_key)


_client = _build_client()

T = TypeVar("T", bound=BaseModel)


async def generate_structured(
    prompt: str,
    schema: Type[T],
    *,
    temperature: float = 0.2,
    model: str | None = None,
) -> T:
    """Run Gemini with a Pydantic response schema and return a validated instance."""

    def _call():
        return _client.models.generate_content(
            model=model or settings.gemini_model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=schema,
                temperature=temperature,
            ),
        )

    resp = await asyncio.to_thread(_call)

    parsed = getattr(resp, "parsed", None)
    if isinstance(parsed, schema):
        return parsed
    # Fallback: validate the raw JSON text ourselves.
    return schema.model_validate_json(resp.text)
