"""In-memory store for analyzed email data — used by the Telegram bot."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from src.prompts import CHAT_SYSTEM_PROMPT_HEADER

log = logging.getLogger(__name__)


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


class EmailContextStore:
    """Thread-safe-ish in-memory email data store (single-writer assumption)."""

    def __init__(self) -> None:
        self._emails: dict[int, AnalyzedEmail] = {}

    def load(self, emails: list[AnalyzedEmail]) -> None:
        """Populate the store, replacing any previous data."""
        log.info("Loading %d email(s) into context store", len(emails))
        self._emails = {e.row_index: e for e in emails}

    def all_emails(self) -> list[AnalyzedEmail]:
        return list(self._emails.values())

    def get(self, row_index: int) -> AnalyzedEmail | None:
        return self._emails.get(row_index)

    def emails_with_action_items(self) -> list[AnalyzedEmail]:
        return [e for e in self._emails.values() if e.action_items.strip()]

    def set_draft_reply(self, row_index: int, draft: str) -> None:
        email = self._emails.get(row_index)
        if email:
            email.draft_reply = draft

    def as_context_summary(self) -> str:
        """Build a text blob of all emails for use as an LLM system prompt."""
        if not self._emails:
            return "No emails have been analyzed yet."

        parts: list[str] = []
        for email in self._emails.values():
            parts.append(
                f"--- Email #{email.row_index} ---\n"
                f"From: {email.sender}\n"
                f"Date: {email.date}\n"
                f"Subject: {email.subject}\n"
                f"Body: {email.body}\n"
                f"Summary: {email.summary}\n"
                f"Category: {email.category}\n"
                f"Action Items:\n{email.action_items}\n"
                f"Reply Strategy:\n{email.reply_strategy}\n"
            )
        return CHAT_SYSTEM_PROMPT_HEADER + "\n".join(parts)
