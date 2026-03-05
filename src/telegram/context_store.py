"""Data model for analyzed email data — used by the Telegram bot."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class AnalyzedEmail:
    """Single analyzed email with all fields the bot needs."""

    row_index: int
    sender: str
    date: str
    subject: str
    body: str
    summary: str
    category: str
    action_items: str
    reply_strategy: str
    draft_reply: str = ""
