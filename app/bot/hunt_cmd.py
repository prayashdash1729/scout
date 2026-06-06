"""
/hunt — run a full hunt for the requesting user and push new matches as
approval cards. Enforces rate limits and prevents overlapping runs.
"""

from __future__ import annotations

import logging

from telegram import Update
from telegram.error import BadRequest
from telegram.ext import CommandHandler, ContextTypes

from app.bot import texts
from app.bot.access import require_access
from app.bot.keyboards import approval_keyboard
from app.db import repo
from app.services import hunt as hunt_service

log = logging.getLogger(__name__)

# Guard against a user firing /hunt again while one is mid-flight.
_running: set[int] = set()


@require_access
async def hunt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    tg = update.effective_user
    user = await repo.get_user(tg.id)
    if user is None or not user.is_onboarded:
        await update.message.reply_text("Set up your profile first — send /start.")
        return

    if tg.id in _running:
        await update.message.reply_text("⏳ A hunt is already running. Hang tight.")
        return

    ok, why = repo.hunt_gate(user)
    if not ok:
        await update.message.reply_text(f"🚦 {why}")
        return

    await repo.record_hunt(tg.id)
    _running.add(tg.id)

    status = await update.message.reply_text("🚀 Starting hunt…")

    async def progress(msg: str) -> None:
        try:
            await status.edit_text(msg)
        except BadRequest:
            pass  # ignore "message is not modified"

    try:
        stats = await hunt_service.run_hunt(user, progress=progress)
    except Exception as e:  # noqa: BLE001
        log.exception("hunt failed for %s", tg.id)
        await update.message.reply_text(f"❌ Hunt failed: {e}")
        return
    finally:
        _running.discard(tg.id)

    if not stats.new_jobs:
        await update.message.reply_text(
            "No new matching jobs this time. Try again later or widen your "
            "roles/cities with /setroles and /setcities."
        )
        return

    await update.message.reply_text(
        f"📬 {len(stats.new_jobs)} new job(s) to review:"
    )
    for job in stats.new_jobs:
        await update.message.reply_html(
            texts.job_card(job),
            reply_markup=approval_keyboard(job.id),
            disable_web_page_preview=True,
        )


def register(application) -> None:
    application.add_handler(CommandHandler("hunt", hunt))
