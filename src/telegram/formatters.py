"""Format analyzed email data into Telegram-friendly messages."""

from __future__ import annotations

import math

from src.config import TG_MAX_MESSAGE_LENGTH, TG_EMAILS_PER_PAGE
from src.telegram.context_store import AnalyzedEmail


def format_email_summary(email: AnalyzedEmail) -> str:
    """One-line summary for list views."""
    return f"[{email.category}] {email.subject} — {email.sender}"


def format_email_list_page(emails: list[AnalyzedEmail], page: int = 0) -> str:
    """Format a page of emails for the list view."""
    total_pages = max(1, math.ceil(len(emails) / TG_EMAILS_PER_PAGE))
    page = max(0, min(page, total_pages - 1))

    start = page * TG_EMAILS_PER_PAGE
    end = start + TG_EMAILS_PER_PAGE
    page_emails = emails[start:end]

    lines = [format_email_summary(e) for e in page_emails]
    header = f"<b>Analyzed Emails ({len(emails)} total):</b>\n\n"
    body = "\n".join(f"{start + i + 1}. {_esc(l)}" for i, l in enumerate(lines))
    return header + body


def format_email_detail(email: AnalyzedEmail) -> str:
    """Full detail view with action items and reply strategy."""
    lines = [
        f"<b>Subject:</b> {_esc(email.subject)}",
        f"<b>From:</b> {_esc(email.sender)}",
        f"<b>Date:</b> {_esc(email.date)}",
        f"<b>Category:</b> {_esc(email.category)}",
        f"\n<b>Summary:</b>\n{_esc(email.summary)}",
    ]
    if email.action_items.strip():
        lines.append(f"\n<b>Action Items:</b>\n{_esc(email.action_items)}")
    if email.reply_strategy.strip():
        lines.append(f"\n<b>Reply Strategy:</b>\n{_esc(email.reply_strategy)}")
    return "\n".join(lines)


def format_action_items_message(emails: list[AnalyzedEmail]) -> str:
    """All action items across all emails."""
    if not emails:
        return "No action items found."
    parts: list[str] = []
    for email in emails:
        parts.append(
            f"<b>{_esc(email.subject)}</b> ({_esc(email.sender)})\n" f"{_esc(email.action_items)}"
        )
    return "\n\n".join(parts)


def format_draft_reply(email: AnalyzedEmail, draft: str) -> str:
    """Format a draft reply for display."""
    return f"<b>Draft reply to:</b> {_esc(email.subject)}\n\n" f"{_esc(draft)}"


def split_message(text: str) -> list[str]:
    """Split text at newlines to fit TG 4096-char limit."""
    if len(text) <= TG_MAX_MESSAGE_LENGTH:
        return [text]

    chunks: list[str] = []
    current = ""
    for line in text.split("\n"):
        candidate = f"{current}\n{line}" if current else line
        if len(candidate) > TG_MAX_MESSAGE_LENGTH:
            if current:
                chunks.append(current)
            current = line[:TG_MAX_MESSAGE_LENGTH]
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks or [text[:TG_MAX_MESSAGE_LENGTH]]


def _esc(text: str) -> str:
    """Escape HTML special chars for Telegram HTML parse mode."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
