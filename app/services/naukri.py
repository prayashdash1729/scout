"""
Naukri source — currently DISABLED (NAUKRI_ENABLED defaults to false).

Naukri's guest JSON API (`/jobapi/v3/search`) returns 406 "recaptcha required"
on a direct hit, and ScraperAPI refuses naukri.com as a protected domain even
with premium/ultra_premium (verified 2026-06). Its HTML page is a JS shell with
no embedded job data. So there's no reliable no-login path today.

The search/fetch implementation below is left in place (and fails safe, returning
nothing) so the source activates the moment a working fetch path exists — e.g. a
Naukri-capable proxy, an official API, or session cookies. Flip NAUKRI_ENABLED=true
to try it.
"""

from __future__ import annotations

import logging
import urllib.parse

from app.config import settings
from app.enums import JobSource
from app.schemas import JobCandidate
from app.services import fetch

log = logging.getLogger(__name__)

_SEARCH = "https://www.naukri.com/jobapi/v3/search"
_HEADERS = {
    "appid": "109",
    "systemid": "109",
    "Accept": "application/json",
    "Referer": "https://www.naukri.com/",
}


def _placeholder(job: dict, kind: str) -> str:
    for ph in job.get("placeholders") or []:
        if ph.get("type") == kind:
            return ph.get("label", "")
    return ""


async def search(role: str, city: str) -> list[JobCandidate]:
    if not settings.naukri_enabled:
        return []

    url = _SEARCH + "?" + urllib.parse.urlencode(
        {
            "noOfResults": "20",
            "urlType": "search_by_keyword",
            "searchType": "adv",
            "keyword": role,
            "location": city,
            "sort": "f",  # freshness
        }
    )
    # Naukri needs premium proxy + forwarded headers; still often blocked.
    status, body = await fetch.get(url, headers=_HEADERS, premium=True, force_scraper=True)
    if status != 200 or not body.strip().startswith("{"):
        log.warning("Naukri source unavailable (status=%s) for %s/%s", status, role, city)
        return []

    import json

    try:
        data = json.loads(body)
    except Exception:  # noqa: BLE001
        return []

    out: list[JobCandidate] = []
    for job in data.get("jobDetails", []) or []:
        jid = str(job.get("jobId") or "").strip()
        if not jid:
            continue
        url = job.get("jdURL") or ""
        if url and url.startswith("/"):
            url = "https://www.naukri.com" + url
        out.append(
            JobCandidate(
                source=JobSource.NAUKRI.value,
                url=url,
                job_key=f"naukri|{jid}",
                title=job.get("title", ""),
                company=job.get("companyName", ""),
                location=_placeholder(job, "location"),
                posting_date=job.get("footerPlaceholderLabel"),
            )
        )
    return out


async def fetch_jd(candidate: JobCandidate) -> str:
    if not settings.naukri_enabled or not candidate.url:
        return ""
    status, html = await fetch.get(candidate.url, premium=True, force_scraper=True)
    if status != 200 or not html:
        return ""
    from app.services.linkedin import _html_to_text  # reuse the HTML→text helper

    return _html_to_text(html)
