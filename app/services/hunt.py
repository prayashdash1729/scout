"""
Hunt orchestrator: for one user, gather job candidates from every enabled
source (LinkedIn guest API, Naukri, Jina/Google), dedup, fetch each job's full
description, score it against the CV with Gemini, dedup against the DB, and
persist new matches as PENDING.

Board sources (LinkedIn/Naukri) hand us a stable job_key up front, so we drop
already-seen jobs *before* spending any JD-fetch or LLM calls. Jina hits have no
key until Gemini produces one, so they're deduped after scoring.

Returns the freshly-created Job rows; the bot layer pushes them for approval.
A progress callback lets the bot stream status.
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
from app.schemas import JobCandidate, JobEvaluation
from app.services import jina, linkedin, naukri, scorer

log = logging.getLogger(__name__)

# Jina/Google keyword templates (supplementary to the board sources).
_QUERY_TEMPLATES = [
    "{role} jobs in {city} {month} {year}",
    "entry level {role} jobs in {city}",
    "{role} fresher jobs in {city} {year}",
    "{role} jobs in {city} site:wellfound.com",
    "{role} jobs in {city} site:instahyre.com",
    "{role} jobs in {city}",
]

ProgressCb = Callable[[str], Awaitable[None]]


@dataclass
class HuntStats:
    candidates: int = 0
    pre_deduped: int = 0       # board jobs skipped as already-seen before scoring
    fetched: int = 0
    evaluated: int = 0
    above_threshold: int = 0
    duplicates: int = 0        # deduped after scoring (mostly Jina)
    new_jobs: list[Job] = field(default_factory=list)
    by_source: dict = field(default_factory=dict)


def build_queries(user: User, now: datetime) -> list[str]:
    month, year = now.strftime("%B"), str(now.year)
    queries, seen = [], set()
    for role in user.target_roles:
        for city in user.target_cities:
            for tmpl in _QUERY_TEMPLATES:
                q = tmpl.format(role=role, city=city, month=month, year=year)
                if q not in seen:
                    seen.add(q)
                    queries.append(q)
    return queries[: settings.max_queries_per_hunt]


async def _gather_candidates(user: User, now: datetime, stats: HuntStats) -> list[JobCandidate]:
    """Fan out across all enabled sources concurrently, then dedup."""
    tasks: list[tuple[str, Awaitable[list[JobCandidate]]]] = []

    if settings.linkedin_enabled:
        for role in user.target_roles:
            for city in user.target_cities:
                tasks.append(("linkedin", linkedin.search(role, city)))
    if settings.naukri_enabled:
        for role in user.target_roles:
            for city in user.target_cities:
                tasks.append(("naukri", naukri.search(role, city)))
    if settings.jina_enabled:
        for q in build_queries(user, now):
            tasks.append(("jina", jina.search(q)))

    results = await asyncio.gather(*(t[1] for t in tasks), return_exceptions=True)

    # Dedup: by stable job_key when present, else by URL.
    by_key: dict[str, JobCandidate] = {}
    for (src, _), res in zip(tasks, results):
        if isinstance(res, Exception):
            log.warning("%s source failed: %s", src, res)
            continue
        stats.by_source[src] = stats.by_source.get(src, 0) + len(res)
        for cand in res:
            dedup_key = cand.job_key or f"url::{cand.url}"
            existing = by_key.get(dedup_key)
            if existing is None:
                by_key[dedup_key] = cand
            elif not existing.content and cand.content:
                by_key[dedup_key] = cand
    return list(by_key.values())


async def _fetch_content(cand: JobCandidate) -> str:
    if cand.content:
        return cand.content
    if cand.source == JobSource.LINKEDIN.value:
        return await linkedin.fetch_jd(cand)
    if cand.source == JobSource.NAUKRI.value:
        return await naukri.fetch_jd(cand)
    return await jina.read(cand.url)


async def run_hunt(user: User, progress: ProgressCb | None = None) -> HuntStats:
    async def say(msg: str) -> None:
        log.info("[hunt:%s] %s", user.id, msg)
        if progress:
            await progress(msg)

    now = datetime.now(timezone.utc)
    today = now.strftime("%Y-%m-%d")
    stats = HuntStats()

    srcs = [s for s, on in [("LinkedIn", settings.linkedin_enabled),
                            ("Naukri", settings.naukri_enabled),
                            ("Google/Jina", settings.jina_enabled)] if on]
    await say(f"🔎 Searching {', '.join(srcs)} across your roles & cities…")

    candidates = await _gather_candidates(user, now, stats)
    stats.candidates = len(candidates)
    src_breakdown = ", ".join(f"{k}:{v}" for k, v in stats.by_source.items())
    await say(f"📥 {len(candidates)} unique candidates ({src_breakdown}).")

    # Pre-filter: drop board jobs we've already shown this user, before any spend.
    fresh: list[JobCandidate] = []
    for cand in candidates:
        if cand.job_key and await repo.job_key_exists(user.id, cand.job_key):
            stats.pre_deduped += 1
            continue
        fresh.append(cand)
    fresh = fresh[: settings.max_links_per_hunt]
    await say(
        f"🆕 {len(fresh)} to evaluate "
        f"({stats.pre_deduped} already seen, capped at {settings.max_links_per_hunt})…"
    )

    sem = asyncio.Semaphore(settings.hunt_concurrency)

    async def process(cand: JobCandidate):
        async with sem:
            content = await _fetch_content(cand)
            if not content:
                return None
            stats.fetched += 1
            try:
                ev = await scorer.evaluate(
                    user.cv_text or "",
                    cand.url,
                    content,
                    today=today,
                    target_roles=user.target_roles,
                    target_cities=user.target_cities,
                )
            except Exception as e:  # noqa: BLE001
                log.warning("scoring failed for %s: %s", cand.url, e)
                return None
            stats.evaluated += 1
            return cand, ev

    results = await asyncio.gather(*(process(c) for c in fresh))

    for item in results:
        if not item:
            continue
        cand, ev = item
        if not ev.is_job_posting or ev.score < settings.score_threshold:
            continue
        stats.above_threshold += 1

        # Prefer the source's stable key; fall back to Gemini's derived key.
        job_key = cand.job_key or ev.job_key
        if await repo.job_key_exists(user.id, job_key):
            stats.duplicates += 1
            continue

        # Trust source metadata where Gemini left blanks.
        ev.job_key = job_key
        ev.company = ev.company or cand.company
        ev.title = ev.title or cand.title
        ev.location = ev.location or cand.location
        ev.posting_date = ev.posting_date or cand.posting_date
        apply_link = ev.apply_link or cand.url
        source = cand.source if cand.source != JobSource.OTHER.value else (
            JobSource.from_url(apply_link).value
        )

        job = await repo.create_job(user.id, ev, url=cand.url, source=source)
        stats.new_jobs.append(job)

    await say(
        f"✅ {stats.above_threshold} matched (≥{settings.score_threshold}), "
        f"{stats.duplicates} dup, {len(stats.new_jobs)} new to review."
    )
    return stats
