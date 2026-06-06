"""
Profile commands: view (/me), field edits (/setname, /setroles, /setcities,
/setexp), help, and a small /editcv conversation to replace the CV.
"""

from __future__ import annotations

import logging

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import (
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from app.bot import texts
from app.bot.access import require_access
from app.bot.onboarding import _is_pdf, cancel, parse_csv
from app.db import repo
from app.enums import ConvState
from app.services import cv as cv_service

log = logging.getLogger(__name__)


async def _require_user(update: Update):
    user = await repo.get_user(update.effective_user.id)
    if user is None or not user.is_onboarded:
        await update.message.reply_text("You're not set up yet — send /start first.")
        return None
    return user


@require_access
async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_html(texts.HELP)


@require_access
async def me(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = await _require_user(update)
    if user:
        await update.message.reply_html(texts.profile_summary(user))


@require_access
async def set_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _require_user(update):
        return
    name = " ".join(context.args).strip()
    if not name:
        await update.message.reply_text("Usage: /setname Your Name")
        return
    tg = update.effective_user
    await repo.save_profile(tg.id, tg.username, name=name)
    await update.message.reply_text(f"Name updated to {name} ✅")


@require_access
async def set_roles(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _require_user(update):
        return
    roles = parse_csv(" ".join(context.args))
    if not roles:
        await update.message.reply_text("Usage: /setroles AI Engineer, ML Engineer")
        return
    tg = update.effective_user
    await repo.save_profile(tg.id, tg.username, target_roles=roles)
    await update.message.reply_text(f"Target roles updated: {', '.join(roles)} ✅")


@require_access
async def set_cities(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _require_user(update):
        return
    cities = parse_csv(" ".join(context.args))
    if not cities:
        await update.message.reply_text("Usage: /setcities Bangalore, Pune")
        return
    tg = update.effective_user
    await repo.save_profile(tg.id, tg.username, target_cities=cities)
    await update.message.reply_text(f"Target cities updated: {', '.join(cities)} ✅")


@require_access
async def set_exp(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _require_user(update):
        return
    try:
        years = int(float(context.args[0]))
    except (IndexError, ValueError):
        await update.message.reply_text("Usage: /setexp 2")
        return
    tg = update.effective_user
    await repo.save_profile(tg.id, tg.username, experience_years=years)
    await update.message.reply_text(f"Experience updated to {years} yr ✅")


# ── /editcv conversation ──────────────────────────────────────────────────
@require_access
async def editcv_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not await _require_user(update):
        return ConversationHandler.END
    await update.message.reply_text("Send your new CV as a PDF. 📎  (/cancel to abort)")
    return ConvState.EDIT_CV


async def editcv_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not _is_pdf(update.message):
        await update.message.reply_text("Please send a PDF file. 📎")
        return ConvState.EDIT_CV

    await update.effective_chat.send_action(ChatAction.TYPING)
    tg_file = await update.message.document.get_file()
    pdf_bytes = bytes(await tg_file.download_as_bytearray())
    try:
        cv_text = await cv_service.extract_text(pdf_bytes)
    except ValueError as e:
        await update.message.reply_text(f"⚠️ {e}")
        return ConvState.EDIT_CV

    insights = await cv_service.extract_insights(cv_text)
    tg = update.effective_user
    await repo.save_profile(
        tg.id, tg.username, cv_text=cv_text, skills=insights.skills
    )
    await update.message.reply_text(
        f"CV updated ✅ ({len(cv_text)} chars, {len(insights.skills)} skills detected)."
    )
    return ConversationHandler.END


def build_editcv_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CommandHandler("editcv", editcv_start)],
        states={
            ConvState.EDIT_CV: [
                MessageHandler(filters.Document.ALL, editcv_received),
                MessageHandler(filters.TEXT & ~filters.COMMAND, editcv_received),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        name="editcv",
        persistent=False,
    )


def register(application) -> None:
    application.add_handler(CommandHandler("help", help_cmd))
    application.add_handler(CommandHandler("me", me))
    application.add_handler(CommandHandler("profile", me))
    application.add_handler(CommandHandler("setname", set_name))
    application.add_handler(CommandHandler("setroles", set_roles))
    application.add_handler(CommandHandler("setcities", set_cities))
    application.add_handler(CommandHandler("setexp", set_exp))
    application.add_handler(build_editcv_handler())
