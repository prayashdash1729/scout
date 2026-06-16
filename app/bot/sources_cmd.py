"""
/sources — let a user choose which job sources their hunts use.

Shows one toggle per available source; tapping persists the change
(User.enabled_sources). An empty selection means "all available sources".
At least one source must stay enabled.
"""

from __future__ import annotations

import logging

from telegram import Update
from telegram.error import BadRequest
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes

from app.bot import keyboards
from app.bot.access import is_allowed, require_access
from app.db import repo
from app.services import sources

log = logging.getLogger(__name__)

_INTRO = (
    "<b>Job sources</b>\n"
    "Tap to toggle which sources your /hunt uses. "
    "All enabled = broadest search.\n"
    "Tip: <code>/hunt linkedin</code> runs a single hunt on just that source."
)


@require_access
async def sources_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = await repo.get_user(update.effective_user.id)
    if user is None or not user.is_onboarded:
        await update.message.reply_text("Set up your profile first — send /start.")
        return
    avail = sources.available()
    await update.message.reply_html(
        _INTRO, reply_markup=keyboards.sources_keyboard(avail, user.enabled_sources or [])
    )


async def on_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    tg = update.effective_user
    if tg is None or not is_allowed(tg.id, tg.username):
        await query.answer("Not authorized.", show_alert=True)
        return

    try:
        _, _, name = query.data.split(":")
    except ValueError:
        await query.answer("Bad action.")
        return

    user = await repo.get_user(tg.id)
    if user is None:
        await query.answer("Send /start first.", show_alert=True)
        return

    avail_names = [s.name for s in sources.available()]
    if name not in avail_names:
        await query.answer("That source isn't available.", show_alert=True)
        return

    # Empty selection means "all"; materialise it before toggling one off.
    current = set(user.enabled_sources or avail_names)
    if name in current:
        current.discard(name)
    else:
        current.add(name)

    if not current:
        await query.answer("Keep at least one source enabled.", show_alert=True)
        return

    # Persist in registry order; store [] when everything is on (the default).
    new = [n for n in avail_names if n in current]
    user = await repo.set_enabled_sources(tg.id, [] if set(new) == set(avail_names) else new)

    await query.answer("Updated ✅")
    try:
        await query.edit_message_reply_markup(
            reply_markup=keyboards.sources_keyboard(
                sources.available(), user.enabled_sources or []
            )
        )
    except BadRequest:
        pass


def register(application) -> None:
    application.add_handler(CommandHandler("sources", sources_cmd))
    application.add_handler(
        CallbackQueryHandler(on_toggle, pattern=f"^{keyboards.SOURCE_PREFIX}:")
    )
