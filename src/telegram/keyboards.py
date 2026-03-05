"""Inline keyboard builders for the Telegram bot."""

from __future__ import annotations

import math

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from src.config import TG_EMAILS_PER_PAGE
from src.telegram.context_store import AnalyzedEmail


def email_list_keyboard(emails: list[AnalyzedEmail], page: int = 0) -> InlineKeyboardMarkup:
    """One button per email, paginated with navigation arrows."""
    total_pages = max(1, math.ceil(len(emails) / TG_EMAILS_PER_PAGE))
    page = max(0, min(page, total_pages - 1))

    start = page * TG_EMAILS_PER_PAGE
    end = start + TG_EMAILS_PER_PAGE
    page_emails = emails[start:end]

    buttons: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                f"[{e.category}] {e.subject[:40]}",
                callback_data=f"view:{e.row_index}",
            )
        ]
        for e in page_emails
    ]

    if total_pages > 1:
        nav_row: list[InlineKeyboardButton] = []
        if page > 0:
            nav_row.append(InlineKeyboardButton("« Prev", callback_data=f"page:{page - 1}"))
        nav_row.append(InlineKeyboardButton(f"{page + 1}/{total_pages}", callback_data="noop"))
        if page < total_pages - 1:
            nav_row.append(InlineKeyboardButton("Next »", callback_data=f"page:{page + 1}"))
        buttons.append(nav_row)

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


def draft_reply_keyboard(row_index: int, gmail_enabled: bool = False) -> InlineKeyboardMarkup:
    """Regenerate / Save to Gmail / Back buttons shown after draft reply."""
    rows = [
        [InlineKeyboardButton("Regenerate", callback_data=f"draft:{row_index}")],
    ]
    if gmail_enabled:
        rows.append(
            [InlineKeyboardButton("Save as Gmail Draft", callback_data=f"gmail_draft:{row_index}")]
        )
    rows.append([InlineKeyboardButton("\u00ab Back", callback_data=f"view:{row_index}")])
    return InlineKeyboardMarkup(rows)
