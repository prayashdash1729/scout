"""Inline keyboard builders + callback_data helpers."""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

# callback_data is limited to 64 bytes; we encode compact tokens.
APPROVAL_PREFIX = "ap"  # ap:<persist|discard>:<job_id>
ROLES_ACCEPT = "roles:accept"
SOURCE_PREFIX = "src"  # src:toggle:<name>


def approval_keyboard(job_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ Persist", callback_data=f"{APPROVAL_PREFIX}:persist:{job_id}"),
                InlineKeyboardButton("🗑 Discard", callback_data=f"{APPROVAL_PREFIX}:discard:{job_id}"),
            ]
        ]
    )


def accept_roles_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("👍 Use suggested roles", callback_data=ROLES_ACCEPT)]]
    )


def sources_keyboard(available, selected: list[str]) -> InlineKeyboardMarkup:
    """One toggle button per available source. Empty selection => all are on."""
    effective = set(selected) if selected else {s.name for s in available}
    rows = [
        [
            InlineKeyboardButton(
                f"{'✅' if s.name in effective else '⬜️'} {s.label}",
                callback_data=f"{SOURCE_PREFIX}:toggle:{s.name}",
            )
        ]
        for s in available
    ]
    return InlineKeyboardMarkup(rows)
