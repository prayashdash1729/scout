"""User-facing message templates and small formatting helpers."""

from __future__ import annotations

import html

from app.db.models import Job, User

HELP = (
    "<b>Scout</b> — your job-hunting agent\n\n"
    "<b>Commands</b>\n"
    "/start – onboard or review your profile\n"
    "/me – show your saved profile\n"
    "/hunt – search, score &amp; surface new matching jobs\n"
    "      (one-off: <code>/hunt linkedin</code> to use just one source)\n"
    "/sources – choose which job sources your hunts use\n"
    "/setname &lt;name&gt;\n"
    "/setroles role1, role2, …\n"
    "/setcities city1, city2, …\n"
    "/setexp &lt;years&gt;\n"
    "/editcv – upload a new CV PDF\n"
    "/cancel – abort the current step\n"
    "/help – this message"
)


def _esc(s: str) -> str:
    return html.escape(s or "")


def profile_summary(user: User) -> str:
    roles = ", ".join(user.target_roles) or "—"
    cities = ", ".join(user.target_cities) or "—"
    skills = ", ".join(user.skills[:15]) or "—"
    cv_state = f"{len(user.cv_text)} chars" if user.cv_text else "not set"
    return (
        f"<b>Your profile</b>\n"
        f"• Name: {_esc(user.name or '—')}\n"
        f"• Experience: {user.experience_years} yr\n"
        f"• Target roles: {_esc(roles)}\n"
        f"• Target cities: {_esc(cities)}\n"
        f"• Skills: {_esc(skills)}\n"
        f"• CV: {cv_state}\n\n"
        f"Edit anything with /setroles, /setcities, /setexp, /setname, /editcv.\n"
        f"Run /hunt when you're ready."
    )


def job_card(job: Job) -> str:
    date = f"🗓 {_esc(job.posting_date)}\n" if job.posting_date else ""
    link = job.apply_link or job.url
    return (
        f"<b>[{job.score}/10] {_esc(job.title) or 'Job'}</b>\n"
        f"🏢 {_esc(job.company) or '—'}  •  📍 {_esc(job.location) or '—'}\n"
        f"{date}"
        f"🔗 <a href=\"{_esc(link)}\">Open posting</a>\n"
        f"💬 {_esc(job.reason)}"
    )
