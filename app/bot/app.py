"""
Builds and runs the Telegram Application (long polling).

Handler registration order:
  1. Onboarding conversation (/start + states)
  2. /editcv conversation + profile commands
  3. /hunt
  4. approval button callbacks
DB tables are created in post_init before polling begins.
"""

from __future__ import annotations

import logging

from telegram import BotCommand, Update
from telegram.ext import Application, ContextTypes

from app.bot import approval, hunt_cmd, onboarding, profile
from app.config import settings
from app.db.base import init_models
from app.logging_conf import setup_logging

log = logging.getLogger(__name__)

_COMMANDS = [
    BotCommand("start", "Onboard or review your profile"),
    BotCommand("hunt", "Search & surface new matching jobs"),
    BotCommand("me", "Show your saved profile"),
    BotCommand("setroles", "Set target roles"),
    BotCommand("setcities", "Set target cities"),
    BotCommand("setexp", "Set years of experience"),
    BotCommand("setname", "Set your name"),
    BotCommand("editcv", "Upload a new CV"),
    BotCommand("help", "Show help"),
    BotCommand("cancel", "Abort the current step"),
]


async def _post_init(application: Application) -> None:
    await init_models()
    await application.bot.set_my_commands(_COMMANDS)
    log.info("DB ready, commands registered. Bot is up.")


async def _on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    log.exception("Unhandled error", exc_info=context.error)


def build_application() -> Application:
    application = (
        Application.builder()
        .token(settings.telegram_bot_token)
        .post_init(_post_init)
        .build()
    )

    # 1. Onboarding (/start conversation)
    application.add_handler(onboarding.build_onboarding_handler())
    # 2. Profile commands + /editcv conversation
    profile.register(application)
    # 3. /hunt
    hunt_cmd.register(application)
    # 4. Approval buttons
    approval.register(application)

    application.add_error_handler(_on_error)
    return application


def main() -> None:
    setup_logging()
    if settings.access_is_restricted:
        log.info(
            "Access restricted to %d id(s) + %d username(s).",
            len(settings.allowed_telegram_ids),
            len(settings.allowed_telegram_usernames),
        )
    else:
        log.info(
            "Access is OPEN (multi-user). Set ALLOWED_TELEGRAM_IDS or "
            "ALLOWED_TELEGRAM_USERNAMES to lock down."
        )

    application = build_application()
    # drop_pending_updates: don't replay a backlog of stale commands after downtime.
    application.run_polling(
        allowed_updates=Update.ALL_TYPES, drop_pending_updates=True
    )


if __name__ == "__main__":
    main()
