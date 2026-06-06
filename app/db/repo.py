"""
Repository layer — all DB access goes through these async functions so the bot
and services never touch sessions directly.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select, update

from app.config import settings
from app.db.base import Session
from app.db.models import Job, User
from app.enums import JobStatus
from app.schemas import JobEvaluation


# ── Users ─────────────────────────────────────────────────────────────────
async def get_user(user_id: int) -> User | None:
    async with Session() as s:
        return await s.get(User, user_id)


async def ensure_user(user_id: int, username: str | None, name: str | None) -> User:
    """Fetch the user, creating a bare row if absent. Refreshes username."""
    async with Session() as s:
        user = await s.get(User, user_id)
        if user is None:
            user = User(id=user_id, username=username, name=name)
            s.add(user)
        else:
            if username:
                user.username = username
        await s.commit()
        await s.refresh(user)
        return user


async def save_profile(
    user_id: int,
    username: str | None,
    *,
    name: str | None = None,
    cv_text: str | None = None,
    skills: list[str] | None = None,
    target_roles: list[str] | None = None,
    target_cities: list[str] | None = None,
    experience_years: int | None = None,
) -> User:
    """Upsert the profile fields that are provided (None = leave unchanged)."""
    async with Session() as s:
        user = await s.get(User, user_id)
        if user is None:
            user = User(id=user_id, username=username)
            s.add(user)
        if username:
            user.username = username
        if name is not None:
            user.name = name
        if cv_text is not None:
            user.cv_text = cv_text
        if skills is not None:
            user.skills = skills
        if target_roles is not None:
            user.target_roles = target_roles
        if target_cities is not None:
            user.target_cities = target_cities
        if experience_years is not None:
            user.experience_years = experience_years
        await s.commit()
        await s.refresh(user)
        return user


# ── Rate limiting ───────────────────────────────────────────────────────────
def hunt_gate(user: User) -> tuple[bool, str]:
    """Pure check (no DB write): may this user hunt right now?"""
    now = datetime.now(timezone.utc)
    today = now.date()

    used_today = user.hunts_today if user.hunt_day == today else 0
    if used_today >= settings.max_hunts_per_day:
        return False, f"Daily limit reached ({settings.max_hunts_per_day} hunts/day). Try tomorrow."

    if user.last_hunt_at is not None:
        last = user.last_hunt_at
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        elapsed_min = (now - last).total_seconds() / 60
        if elapsed_min < settings.hunt_cooldown_minutes:
            wait = int(settings.hunt_cooldown_minutes - elapsed_min) + 1
            return False, f"Cooling down — try again in ~{wait} min."
    return True, ""


async def record_hunt(user_id: int) -> None:
    """Stamp a hunt for rate-limit accounting."""
    now = datetime.now(timezone.utc)
    today = now.date()
    async with Session() as s:
        user = await s.get(User, user_id)
        if user is None:
            return
        if user.hunt_day == today:
            user.hunts_today = (user.hunts_today or 0) + 1
        else:
            user.hunt_day = today
            user.hunts_today = 1
        user.last_hunt_at = now
        await s.commit()


# ── Jobs ──────────────────────────────────────────────────────────────────
async def job_key_exists(user_id: int, job_key: str) -> bool:
    async with Session() as s:
        row = await s.scalar(
            select(Job.id).where(Job.user_id == user_id, Job.job_key == job_key)
        )
        return row is not None


async def create_job(
    user_id: int, ev: JobEvaluation, url: str, source: str
) -> Job:
    """Persist a freshly surfaced job as PENDING. Returns the stored row."""
    async with Session() as s:
        job = Job(
            user_id=user_id,
            job_key=ev.job_key,
            title=ev.title[:512],
            company=ev.company[:512],
            location=ev.location[:255],
            url=url,
            apply_link=ev.apply_link or url,
            source=source,
            score=ev.score,
            reason=ev.reason,
            posting_date=ev.posting_date,
            status=JobStatus.PENDING.value,
        )
        s.add(job)
        await s.commit()
        await s.refresh(job)
        return job


async def get_job(job_id: int) -> Job | None:
    async with Session() as s:
        return await s.get(Job, job_id)


async def set_job_status(job_id: int, status: JobStatus) -> Job | None:
    async with Session() as s:
        job = await s.get(Job, job_id)
        if job is None:
            return None
        job.status = status.value
        job.decided_at = datetime.now(timezone.utc)
        await s.commit()
        await s.refresh(job)
        return job


async def count_jobs_by_status(user_id: int, status: JobStatus) -> int:
    from sqlalchemy import func as _func

    async with Session() as s:
        return await s.scalar(
            select(_func.count(Job.id)).where(
                Job.user_id == user_id, Job.status == status.value
            )
        ) or 0
