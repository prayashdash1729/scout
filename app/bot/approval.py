"""
Approval callbacks: the Persist / Discard buttons on each job card update the
job's status in the DB so it's never surfaced to that user again.
"""

from __future__ import annotations

import logging

from telegram import Update
from telegram.error import BadRequest
from telegram.ext import CallbackQueryHandler, ContextTypes

from app.bot.access import is_allowed
from app.bot.keyboards import APPROVAL_PREFIX
from app.db import repo
from app.enums import JobStatus

log = logging.getLogger(__name__)

_ACTIONS = {
    "persist": (JobStatus.PERSISTED, "✅ Persisted"),
    "discard": (JobStatus.DISCARDED, "🗑 Discarded"),
}


async def on_decision(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    tg = update.effective_user
    if tg is None or not is_allowed(tg.id):
        await query.answer("Not authorized.", show_alert=True)
        return

    try:
        _, action, job_id_raw = query.data.split(":")
        job_id = int(job_id_raw)
    except (ValueError, AttributeError):
        await query.answer("Bad action.")
        return

    if action not in _ACTIONS:
        await query.answer("Unknown action.")
        return

    job = await repo.get_job(job_id)
    if job is None:
        await query.answer("Job not found.")
        return
    if job.user_id != tg.id:
        await query.answer("That's not your job.", show_alert=True)
        return

    status, label = _ACTIONS[action]
    await repo.set_job_status(job_id, status)
    await query.answer(label)

    # Drop the buttons and stamp the decision onto the card.
    try:
        original = query.message.text_html or query.message.text or ""
        await query.edit_message_text(
            f"{original}\n\n<b>{label}</b>",
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
    except BadRequest:
        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except BadRequest:
            pass


def register(application) -> None:
    application.add_handler(
        CallbackQueryHandler(on_decision, pattern=f"^{APPROVAL_PREFIX}:")
    )
