"""
Hunt orchestrator: for one user, search job boards, render pages, score them
against the CV, dedup against the DB, and persist new matches as PENDING.

Returns the freshly-created Job rows; the bot layer is responsible for pushing
them to the user for approval. A progress callback lets the bot stream status.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Awaitable, Callable

from app.config import settings
from app.db import repo
from app.db.models import Job, User
from app.enums import JobSource
from app.schemas import SearchHit
from app.services import jina, scorer

log = logging.getLogger(__name__)

# Search query templates. {role}/{city} filled per combo; {month}/{year} make
# queries recency-biased; site: filters target specific boards.
_QUERY_TEMPLATES = [
    "{role} jobs in {city} {month} {year}",
    "entry level {role} jobs in {city}",
    "{role} fresher jobs in {city} {year}",
    "{role} jobs in {city} site:linkedin.com",
    "{role} jobs in {city} site:naukri.com",
    "{role} jobs in {city} site:instahyre.com",
    "{role} jobs in {city} site:wellfound.com",
    "{role} jobs in {city}",
]

ProgressCb = Callable[[str], Awaitable[None]]


@dataclass
class HuntStats:
    queries: int = 0
    links_found: int = 0
    pages_read: int = 0
    evaluated: int = 0
    above_threshold: int = 0
    new_jobs: list[Job] = field(default_factory=list)
    duplicates: int = 0


def build_queries(user: User, now: datetime) -> list[str]:
    month = now.strftime("%B")
    year = str(now.year)
    queries: list[str] = []
    seen: set[str] = set()
    # roles x cities x templates, capped to protect quota.
    for role in user.target_roles:
        for city in user.target_cities:
            for tmpl in _QUERY_TEMPLATES:
                q = tmpl.format(role=role, city=city, month=month, year=year)
                if q not in seen:
                    seen.add(q)
                    queries.append(q)
    return queries[: settings.max_queries_per_hunt]


async def _gather_links(queries: list[str]) -> dict[str, SearchHit]:
    """Run searches concurrently and dedup hits by URL."""
    results = await asyncio.gather(*(jina.search(q) for q in queries))
    by_url: dict[str, SearchHit] = {}
    for hits in results:
        for hit in hits:
            if hit.url not in by_url:
                by_url[hit.url] = hit
            elif not by_url[hit.url].content and hit.content:
                by_url[hit.url] = hit
    return by_url


async def run_hunt(
    user: User, progress: ProgressCb | None = None
) -> HuntStats:
    async def say(msg: str) -> None:
        log.info("[hunt:%s] %s", user.id, msg)
        if progress:
            await progress(msg)

    now = datetime.now(timezone.utc)
    today = now.strftime("%Y-%m-%d")
    stats = HuntStats()

    queries = build_queries(user, now)
    stats.queries = len(queries)
    await say(f"🔎 Searching {len(queries)} queries across your roles & cities…")

    by_url = await _gather_links(queries)
    # Cap total pages we'll read+score this run.
    hits = list(by_url.values())[: settings.max_links_per_hunt]
    stats.links_found = len(hits)
    await say(f"📄 Found {len(by_url)} unique links — evaluating top {len(hits)}…")

    sem = asyncio.Semaphore(settings.hunt_concurrency)

    async def process(hit: SearchHit):
        async with sem:
            content = hit.content
            if not content:
                content = await jina.read(hit.url)
            if not content:
                return None
            stats.pages_read += 1
            try:
                ev = await scorer.evaluate(
                    user.cv_text or "",
                    hit.url,
                    content,
                    today=today,
                    target_roles=user.target_roles,
                    target_cities=user.target_cities,
                )
            except Exception as e:  # noqa: BLE001
                log.warning("scoring failed for %s: %s", hit.url, e)
                return None
            stats.evaluated += 1
            return hit, ev

    results = await asyncio.gather(*(process(h) for h in hits))

    for item in results:
        if not item:
            continue
        hit, ev = item
        if not ev.is_job_posting or ev.score < settings.score_threshold:
            continue
        stats.above_threshold += 1
        # Dedup against everything this user has already been shown/decided.
        if await repo.job_key_exists(user.id, ev.job_key):
            stats.duplicates += 1
            continue
        source = JobSource.from_url(ev.apply_link or hit.url).value
        job = await repo.create_job(user.id, ev, url=hit.url, source=source)
        stats.new_jobs.append(job)

    await say(
        f"✅ {stats.above_threshold} matched (≥{settings.score_threshold}), "
        f"{stats.duplicates} already seen, {len(stats.new_jobs)} new to review."
    )
    return stats
