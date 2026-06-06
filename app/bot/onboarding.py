"""
Onboarding conversation for /start.

Flow (new user):  name → CV upload → confirm roles → cities → experience → save.
Returning user:   show saved profile and the edit commands, then end.
"""

from __future__ import annotations

import logging

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from app.bot import texts
from app.bot.access import is_allowed
from app.bot.keyboards import ROLES_ACCEPT, accept_roles_keyboard
from app.db import repo
from app.enums import ConvState
from app.services import cv as cv_service

log = logging.getLogger(__name__)


def parse_csv(text: str) -> list[str]:
    return [p.strip() for p in (text or "").replace("\n", ",").split(",") if p.strip()]


def _is_pdf(message) -> bool:
    doc = message.document
    if not doc:
        return False
    name = (doc.file_name or "").lower()
    return doc.mime_type == "application/pdf" or name.endswith(".pdf")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    tg = update.effective_user
    if tg is None or not is_allowed(tg.id):
        await update.effective_message.reply_text(
            "🔒 This bot is private. Ask the owner to add your Telegram ID."
        )
        return ConversationHandler.END

    user = await repo.ensure_user(tg.id, tg.username, tg.full_name)

    # Returning, fully-onboarded user → show profile, offer edits, end.
    if user.is_onboarded:
        await update.message.reply_html(
            f"👋 Welcome back, {user.name or tg.first_name}!\n\n"
            + texts.profile_summary(user)
        )
        return ConversationHandler.END

    context.user_data.clear()
    await update.message.reply_text(
        "👋 Hi! Let's set up your job-hunting profile.\n\nFirst — what's your name?"
    )
    return ConvState.NAME


async def got_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["name"] = update.message.text.strip()
    await update.message.reply_text(
        f"Nice to meet you, {context.user_data['name']}!\n\n"
        "Now upload your CV as a PDF (tap the 📎 and send the file)."
    )
    return ConvState.CV


async def got_cv(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not _is_pdf(update.message):
        await update.message.reply_text("Please send your CV as a PDF file. 📎")
        return ConvState.CV

    await update.effective_chat.send_action(ChatAction.TYPING)
    tg_file = await update.message.document.get_file()
    pdf_bytes = bytes(await tg_file.download_as_bytearray())

    try:
        cv_text = await cv_service.extract_text(pdf_bytes)
    except ValueError as e:
        await update.message.reply_text(f"⚠️ {e}")
        return ConvState.CV

    context.user_data["cv_text"] = cv_text
    await update.message.reply_text("📑 Got your CV — analysing it…")
    await update.effective_chat.send_action(ChatAction.TYPING)

    insights = await cv_service.extract_insights(cv_text)
    context.user_data["skills"] = insights.skills
    context.user_data["suggested_roles"] = insights.suggested_roles
    context.user_data["exp_guess"] = insights.experience_years

    skills = ", ".join(insights.skills[:12]) or "—"
    suggested = ", ".join(insights.suggested_roles) or "—"
    await update.message.reply_html(
        f"Here's what I found:\n"
        f"• <b>Skills</b>: {skills}\n"
        f"• <b>Suggested roles</b>: {suggested}\n\n"
        "Send the <b>target roles</b> you want to hunt for (comma-separated), "
        "or tap the button to use my suggestions.",
        reply_markup=accept_roles_keyboard(),
    )
    return ConvState.ROLES


async def roles_accept(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    roles = context.user_data.get("suggested_roles", [])
    context.user_data["target_roles"] = roles
    await query.edit_message_reply_markup(reply_markup=None)
    await query.message.reply_text(
        "Using suggested roles ✅\n\nNow send your target cities (comma-separated), "
        "e.g. Bangalore, Pune, Gurgaon."
    )
    return ConvState.CITIES


async def roles_typed(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    roles = parse_csv(update.message.text)
    if not roles:
        await update.message.reply_text("Please send at least one role.")
        return ConvState.ROLES
    context.user_data["target_roles"] = roles
    await update.message.reply_text(
        "Got it. Now send your target cities (comma-separated), "
        "e.g. Bangalore, Pune, Gurgaon."
    )
    return ConvState.CITIES


async def got_cities(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    cities = parse_csv(update.message.text)
    if not cities:
        await update.message.reply_text("Please send at least one city.")
        return ConvState.CITIES
    context.user_data["target_cities"] = cities
    guess = context.user_data.get("exp_guess", 0)
    await update.message.reply_text(
        f"Almost done. How many years of professional experience do you have? "
        f"(I estimated {guess} from your CV — send a number to confirm or correct.)"
    )
    return ConvState.EXPERIENCE


async def got_experience(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    raw = (update.message.text or "").strip()
    try:
        years = int(float(raw))
    except ValueError:
        years = context.user_data.get("exp_guess", 0)

    tg = update.effective_user
    user = await repo.save_profile(
        tg.id,
        tg.username,
        name=context.user_data.get("name"),
        cv_text=context.user_data.get("cv_text"),
        skills=context.user_data.get("skills", []),
        target_roles=context.user_data.get("target_roles", []),
        target_cities=context.user_data.get("target_cities", []),
        experience_years=years,
    )
    context.user_data.clear()
    await update.message.reply_html(
        "🎉 You're all set!\n\n" + texts.profile_summary(user)
    )
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await update.message.reply_text("Cancelled. Send /start anytime.")
    return ConversationHandler.END


def build_onboarding_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            ConvState.NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, got_name)
            ],
            ConvState.CV: [
                MessageHandler(filters.Document.ALL, got_cv),
                MessageHandler(filters.TEXT & ~filters.COMMAND, got_cv),
            ],
            ConvState.ROLES: [
                CallbackQueryHandler(roles_accept, pattern=f"^{ROLES_ACCEPT}$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, roles_typed),
            ],
            ConvState.CITIES: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, got_cities)
            ],
            ConvState.EXPERIENCE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, got_experience)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        name="onboarding",
        persistent=False,
    )
