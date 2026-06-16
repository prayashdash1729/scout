"""
Job-source registry.

Each source (LinkedIn, Naukri, Google/Jina) is wrapped in a `SourceAdapter` with
a uniform interface — `gather(user)` to discover candidates and `fetch_content`
to render one job's description. The hunt orchestrator just iterates the adapters
a user has selected; adding a new board is "drop in a module + register here",
with no changes to hunt.py.

A source's *availability* is the operator-level switch (env/Settings). A user's
*selection* (User.enabled_sources, empty = all available) narrows that per hunt;
a `/hunt <names>` argument overrides it for a single run.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Awaitable, Callable

from app.config import settings
from app.db.models import User
from app.schemas import JobCandidate
from app.services import jina, linkedin, naukri

log = logging.getLogger(__name__)

GatherFn = Callable[[User], Awaitable[list[JobCandidate]]]
FetchFn = Callable[[JobCandidate], Awaitable[str]]


@dataclass(frozen=True)
class SourceAdapter:
    name: str                       # registry key / candidate.origin
    label: str                      # human label for the bot UI
    _available: Callable[[], bool]  # operator-level switch (Settings)
    _gather: GatherFn
    _fetch: FetchFn

    def available(self) -> bool:
        return self._available()

    async def gather(self, user: User) -> list[JobCandidate]:
        cands = await self._gather(user)
        for c in cands:
            c.origin = self.name  # stamp origin so JD-fetch dispatches correctly
        return cands

    async def fetch_content(self, cand: JobCandidate) -> str:
        return await self._fetch(cand)


# ── helpers ───────────────────────────────────────────────────────────────
def _flatten(results) -> list[JobCandidate]:
    out: list[JobCandidate] = []
    for r in results:
        if isinstance(r, Exception):
            log.warning("source search task failed: %s", r)
            continue
        out.extend(r)
    return out


async def _board_gather(search_fn, user: User) -> list[JobCandidate]:
    """Board sources search per role×city; fan those out concurrently."""
    tasks = [
        search_fn(role, city)
        for role in user.target_roles
        for city in user.target_cities
    ]
    return _flatten(await asyncio.gather(*tasks, return_exceptions=True))


async def _linkedin_gather(user: User) -> list[JobCandidate]:
    return await _board_gather(linkedin.search, user)


async def _naukri_gather(user: User) -> list[JobCandidate]:
    return await _board_gather(naukri.search, user)


# Google/Jina keyword templates (supplementary, recency-biased).
_QUERY_TEMPLATES = [
    "{role} jobs in {city} {month} {year}",
    "entry level {role} jobs in {city}",
    "{role} fresher jobs in {city} {year}",
    "{role} jobs in {city} site:wellfound.com",
    "{role} jobs in {city} site:instahyre.com",
    "{role} jobs in {city}",
]


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


async def _jina_gather(user: User) -> list[JobCandidate]:
    now = datetime.now(timezone.utc)
    queries = build_queries(user, now)
    return _flatten(await asyncio.gather(*(jina.search(q) for q in queries), return_exceptions=True))


# ── registry ──────────────────────────────────────────────────────────────
REGISTRY: list[SourceAdapter] = [
    SourceAdapter(
        "linkedin", "LinkedIn",
        lambda: settings.linkedin_enabled, _linkedin_gather, linkedin.fetch_jd,
    ),
    SourceAdapter(
        "naukri", "Naukri",
        lambda: settings.naukri_enabled, _naukri_gather, naukri.fetch_jd,
    ),
    SourceAdapter(
        "jina", "Google/Jina",
        lambda: settings.jina_enabled, _jina_gather, lambda c: jina.read(c.url),
    ),
]

_BY_NAME = {s.name: s for s in REGISTRY}


def by_name(name: str) -> SourceAdapter | None:
    return _BY_NAME.get(name)


def available() -> list[SourceAdapter]:
    """Sources the operator has switched on (env/Settings)."""
    return [s for s in REGISTRY if s.available()]


def resolve(user: User, override: list[str] | None = None) -> list[SourceAdapter]:
    """
    Which adapters to use for a hunt: the user's selection (or a one-off
    override) intersected with what's available. Empty selection = all available;
    an empty intersection also falls back to all available.
    """
    avail = available()
    if override:
        sel = {n.strip().lower() for n in override}
    else:
        sel = {n.strip().lower() for n in (user.enabled_sources or [])}
    if not sel:
        return avail
    chosen = [s for s in avail if s.name in sel]
    return chosen or avail
