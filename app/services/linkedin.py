"""
LinkedIn source via the public **guest** jobs endpoints (no login).

  • search(role, city) -> guest `seeMoreJobPostings/search` returns HTML job
    cards (10/page) carrying a stable jobPosting id, title, company, location,
    and posting date. We paginate `start` and apply freshness/experience/job-type
    filters — this is what gives fresh, relevant postings that plain web search
    can't.
  • fetch_jd(candidate) -> guest `jobPosting/<id>` returns the full description.

The stable id yields a rock-solid job_key ('linkedin|<id>'), so jobs dedup
cleanly and we can skip already-seen ones before any fetch/LLM spend.
"""

from __future__ import annotations

import logging
import re
import urllib.parse

from bs4 import BeautifulSoup

from app.config import settings
from app.enums import JobSource
from app.schemas import JobCandidate
from app.services import fetch

log = logging.getLogger(__name__)

_SEARCH = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
_JD = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/"

_PAGE_SIZE = 10


def _search_url(role: str, city: str, start: int) -> str:
    params = {
        "keywords": role,
        "location": f"{city}, India",
        "f_TPR": settings.linkedin_tpr,
        "f_E": settings.linkedin_experience,
        "f_JT": settings.linkedin_job_type,
        "sortBy": "DD",  # newest first
        "start": start,
    }
    return _SEARCH + "?" + urllib.parse.urlencode(params)


def _clean_url(href: str) -> str:
    # Drop tracking query params; keep the canonical /jobs/view/<slug>-<id>.
    return (href or "").split("?")[0].strip()


def _parse_cards(html: str) -> list[JobCandidate]:
    soup = BeautifulSoup(html, "html.parser")
    out: list[JobCandidate] = []
    for card in soup.select("div.base-card, li div.base-search-card"):
        urn = card.get("data-entity-urn", "")
        m = re.search(r"jobPosting:(\d+)", urn)
        if not m:
            continue
        job_id = m.group(1)

        link_el = card.select_one("a.base-card__full-link") or card.find("a", href=True)
        url = _clean_url(link_el["href"]) if link_el and link_el.has_attr("href") else ""

        title_el = card.select_one("span.sr-only") or card.select_one(
            "h3.base-search-card__title"
        )
        company_el = card.select_one("h4.base-search-card__subtitle a") or card.select_one(
            "h4.base-search-card__subtitle"
        )
        loc_el = card.select_one("span.job-search-card__location")
        time_el = card.find("time")

        out.append(
            JobCandidate(
                source=JobSource.LINKEDIN.value,
                url=url or f"https://www.linkedin.com/jobs/view/{job_id}",
                job_key=f"linkedin|{job_id}",
                title=title_el.get_text(strip=True) if title_el else "",
                company=company_el.get_text(strip=True) if company_el else "",
                location=loc_el.get_text(strip=True) if loc_el else "",
                posting_date=(time_el.get("datetime") if time_el else None),
            )
        )
    return out


async def search(role: str, city: str) -> list[JobCandidate]:
    """Paginated guest search for one role×city. Empty list on failure."""
    found: dict[str, JobCandidate] = {}
    for page in range(max(1, settings.linkedin_pages)):
        url = _search_url(role, city, page * _PAGE_SIZE)
        status, html = await fetch.get(url)
        if status != 200 or not html:
            log.info("LinkedIn search stop (status=%s) %s/%s p%d", status, role, city, page)
            break
        cards = _parse_cards(html)
        if not cards:
            break
        for c in cards:
            found[c.job_key] = c
        if len(cards) < _PAGE_SIZE:
            break  # last page
    return list(found.values())


def _html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = soup.get_text(separator=" ", strip=True)
    return re.sub(r"\s+", " ", text).strip()


async def fetch_jd(candidate: JobCandidate) -> str:
    """Fetch the full job description for a candidate via the guest endpoint."""
    job_id = (candidate.job_key or "").split("|")[-1]
    if not job_id.isdigit():
        return ""
    status, html = await fetch.get(_JD + job_id)
    if status != 200 or not html:
        return ""
    return _html_to_text(html)
