"""
Access control: an optional allowlist gate applied before any handler runs real
work. Empty allowlist => open (true multi-user). Non-empty => only the listed
Telegram IDs and/or usernames are served; everyone else is politely turned away.
"""

from __future__ import annotations

import functools
import logging

from telegram import Update
from telegram.ext import ContextTypes

from app.config import settings

log = logging.getLogger(__name__)


def is_allowed(user_id: int, username: str | None = None) -> bool:
    """Allow if access is open, or the user matches the ID or username allowlist."""
    if not settings.access_is_restricted:
        return True
    if user_id in settings.allowed_telegram_ids:
        return True
    if username and username.lower() in settings.allowed_telegram_usernames:
        return True
    return False


def require_access(handler):
    """Decorator for (update, context) handlers enforcing the allowlist."""

    @functools.wraps(handler)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *a, **kw):
        user = update.effective_user
        if user is None or not is_allowed(user.id, user.username):
            if update.effective_message:
                await update.effective_message.reply_text(
                    "🔒 This bot is private. Ask the owner to add your "
                    "Telegram username or ID."
                )
            log.info(
                "Rejected access for user_id=%s username=%s",
                getattr(user, "id", None),
                getattr(user, "username", None),
            )
            return None
        return await handler(update, context, *a, **kw)

    return wrapper
