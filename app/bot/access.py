"""
Access control: an optional allowlist gate applied before any handler runs real
work. Empty allowlist => open (true multi-user). Non-empty => only those
Telegram IDs are served; everyone else is politely turned away.
"""

from __future__ import annotations

import functools
import logging

from telegram import Update
from telegram.ext import ContextTypes

from app.config import settings

log = logging.getLogger(__name__)


def is_allowed(user_id: int) -> bool:
    if not settings.access_is_restricted:
        return True
    return user_id in settings.allowed_telegram_ids


def require_access(handler):
    """Decorator for (update, context) handlers enforcing the allowlist."""

    @functools.wraps(handler)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *a, **kw):
        user = update.effective_user
        if user is None or not is_allowed(user.id):
            if update.effective_message:
                await update.effective_message.reply_text(
                    "🔒 This bot is private. Ask the owner to add your Telegram ID."
                )
            log.info("Rejected access for user_id=%s", getattr(user, "id", None))
            return None
        return await handler(update, context, *a, **kw)

    return wrapper
