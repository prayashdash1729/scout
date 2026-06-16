"""
Shared HTTP fetcher with an optional ScraperAPI fallback.

Job boards block datacenter IPs aggressively. Locally a direct request often
works; on a cloud server it won't. So `get()` tries a direct request first
(unless configured otherwise) and falls back to ScraperAPI — which rotates
residential IPs, geo-routes by country, and optionally renders JS — whenever the
direct hit fails or looks blocked (403/429/captcha walls).
"""

from __future__ import annotations

import logging
import urllib.parse

import httpx

from app.config import settings

log = logging.getLogger(__name__)

_TIMEOUT = httpx.Timeout(90.0, connect=20.0)
_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

_BLOCK_MARKERS = ("captcha", "recaptcha", "/authwall", "verify you are a human")


def _looks_blocked(status: int, text: str) -> bool:
    if status in (401, 403, 407, 429, 999):  # 999 = LinkedIn's block code
        return True
    head = (text or "")[:1500].lower()
    return any(m in head for m in _BLOCK_MARKERS)


def _scraper_url(target: str, *, render: bool, premium: bool) -> str:
    params = {
        "api_key": settings.scraper_api_key,
        "url": target,
        "country_code": settings.fetch_country,
    }
    if render:
        params["render"] = "true"
    if premium:
        params["premium"] = "true"
    return "https://api.scraperapi.com/?" + urllib.parse.urlencode(params)


async def get(
    url: str,
    *,
    headers: dict | None = None,
    render: bool = False,
    premium: bool = False,
    force_scraper: bool = False,
) -> tuple[int, str]:
    """
    Fetch a URL, returning (status_code, text). Never raises — returns (0, "")
    on total failure so callers can degrade gracefully.
    """
    req_headers = {"User-Agent": _UA, "Accept-Language": "en-US,en;q=0.9"}
    if headers:
        req_headers.update(headers)

    have_scraper = bool(settings.scraper_api_key)
    use_scraper_first = force_scraper or (settings.scraper_first and have_scraper)

    # 1. Direct attempt (unless we're told to lead with the proxy).
    if not use_scraper_first:
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as c:
                r = await c.get(url, headers=req_headers)
            if not _looks_blocked(r.status_code, r.text):
                return r.status_code, r.text
            log.info("Direct fetch looked blocked (%s) for %s", r.status_code, url)
        except Exception as e:  # noqa: BLE001
            log.info("Direct fetch failed for %s: %s", url, e)

    # 2. ScraperAPI fallback.
    if have_scraper:
        try:
            api = _scraper_url(url, render=render, premium=premium)
            async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as c:
                # keep_headers lets boards that need custom headers receive them.
                kh = {**req_headers, "X-ScraperAPI-Keep-Headers": "true"} if headers else req_headers
                r = await c.get(api, headers=kh)
            return r.status_code, r.text
        except Exception as e:  # noqa: BLE001
            log.warning("ScraperAPI fetch failed for %s: %s", url, e)

    return 0, ""
