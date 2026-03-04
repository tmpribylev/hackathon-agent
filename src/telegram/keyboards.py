"""Inline keyboard builders for the Telegram bot."""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from src.telegram.context_store import AnalyzedEmail


def email_list_keyboard(emails: list[AnalyzedEmail]) -> InlineKeyboardMarkup:
    """One button per email."""
    buttons = [
        [
            InlineKeyboardButton(
                f"[{e.category}] {e.subject[:40]}",
                callback_data=f"view:{e.row_index}",
            )
        ]
        for e in emails
    ]
    return InlineKeyboardMarkup(buttons)


def email_detail_keyboard(row_index: int) -> InlineKeyboardMarkup:
    """Action Items / Reply Strategy / Draft Reply buttons."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Action Items", callback_data=f"actions:{row_index}"),
                InlineKeyboardButton("Reply Strategy", callback_data=f"strategy:{row_index}"),
            ],
            [
                InlineKeyboardButton("Generate Draft Reply", callback_data=f"draft:{row_index}"),
            ],
            [
                InlineKeyboardButton("\u00ab Back to list", callback_data="back:list"),
            ],
        ]
    )


def strategy_keyboard(row_index: int) -> InlineKeyboardMarkup:
    """Generate Draft / Back buttons shown after reply strategy."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Generate Draft Reply", callback_data=f"draft:{row_index}")],
            [InlineKeyboardButton("\u00ab Back", callback_data=f"view:{row_index}")],
        ]
    )


def draft_reply_keyboard(row_index: int) -> InlineKeyboardMarkup:
    """Regenerate / Back buttons shown after draft reply."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Regenerate", callback_data=f"draft:{row_index}")],
            [InlineKeyboardButton("\u00ab Back", callback_data=f"view:{row_index}")],
        ]
    )
