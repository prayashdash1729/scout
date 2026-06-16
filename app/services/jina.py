"""
Jina integration.

  • search(query)  -> s.jina.ai : Google-backed search returning result links.
                      We request JSON; results often already include page content,
                      which lets us skip a separate reader call (saves quota).
  • read(url)      -> r.jina.ai : render a single page to clean markdown text.

Both are bearer-authenticated with JINA_API_KEY and run over a shared async
httpx client.
"""

from __future__ import annotations

import logging

import httpx

from app.config import settings
from app.enums import JobSource
from app.schemas import JobCandidate

log = logging.getLogger(__name__)

SEARCH_URL = "https://s.jina.ai/"
READER_URL = "https://r.jina.ai/"

_TIMEOUT = httpx.Timeout(60.0, connect=15.0)


def _headers(extra: dict | None = None) -> dict:
    h = {
        "Authorization": f"Bearer {settings.jina_api_key}",
        "Accept": "application/json",
    }
    if extra:
        h.update(extra)
    return h


async def search(query: str, top_k: int | None = None) -> list[JobCandidate]:
    """Return up to `top_k` candidates for a query. Empty list on failure."""
    top_k = top_k or settings.search_top_k
    params = {"q": query, "count": str(top_k), "gl": "in", "hl": "en"}
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(SEARCH_URL, params=params, headers=_headers())
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:  # noqa: BLE001 — keep the hunt alive on any failure
        log.warning("Jina search failed for %r: %s", query, e)
        return []

    items = data.get("data", []) if isinstance(data, dict) else []
    hits: list[JobCandidate] = []
    for item in items[:top_k]:
        url = item.get("url") or item.get("link") or ""
        if not url:
            continue
        hits.append(
            JobCandidate(
                source=JobSource.from_url(url).value,
                url=url,
                job_key=None,  # derived by Gemini after scoring
                title=item.get("title", ""),
                content=item.get("content", "") or "",
            )
        )
    return hits


async def read(url: str) -> str:
    """Render a page to text via Jina reader. Empty string on failure."""
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as client:
            resp = await client.get(
                READER_URL + url,
                headers=_headers({"X-Return-Format": "markdown"}),
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:  # noqa: BLE001
        log.warning("Jina reader failed for %s: %s", url, e)
        return ""

    if isinstance(data, dict):
        return data.get("data", {}).get("content", "") or ""
    return ""
