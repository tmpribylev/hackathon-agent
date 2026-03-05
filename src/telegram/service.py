"""Business logic layer for the Telegram bot."""

from __future__ import annotations

import logging

import datetime

from src.config import (
    TG_REPLY_DRAFT_MAX_TOKENS,
    TG_BRIEFING_MAX_TOKENS,
    TG_CHAT_MAX_TOKENS,
    TG_CHAT_MAX_HISTORY,
)
from src.prompts import BRIEFING_RECOMMENDATION_PROMPT, DRAFT_REPLY_PROMPT, CHAT_SYSTEM_PROMPT_HEADER
from src.llm.client import LLMClient
from src.agents.email_analyzer import EmailAnalyzer, AnalysisResult
from src.gmail.client import GmailClient
from src.db.client import LocalDB
from src.db.sync import SyncManager
from src.telegram.context_store import AnalyzedEmail

log = logging.getLogger(__name__)


class _DBBackedStore:
    """Drop-in replacement for EmailContextStore backed by LocalDB.

    Reads from SQLite and returns AnalyzedEmail objects.
    Draft replies stay in-memory since they are ephemeral.
    """

    def __init__(self, db: LocalDB) -> None:
        self._db = db
        self._draft_replies: dict[int, str] = {}

    def all_emails(self) -> list[AnalyzedEmail]:
        return [self._row_to_email(r) for r in self._db.get_all_emails()]

    def get(self, row_index: int) -> AnalyzedEmail | None:
        email = self._db.get_email(row_index)
        if not email:
            return None
        return self._row_to_email(email)

    def emails_with_action_items(self) -> list[AnalyzedEmail]:
        return [e for e in self.all_emails() if e.action_items.strip()]

    def set_draft_reply(self, row_index: int, draft: str) -> None:
        self._draft_replies[row_index] = draft

    def as_context_summary(self) -> str:
        emails = self.all_emails()
        if not emails:
            return "No emails have been analyzed yet."

        parts: list[str] = []
        for email in emails:
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

    def _row_to_email(self, row: dict) -> AnalyzedEmail:
        row_id = row["id"]
        return AnalyzedEmail(
            row_index=row_id,
            sender=row.get("sender", ""),
            date=row.get("date", ""),
            subject=row.get("subject", ""),
            body=row.get("body", ""),
            summary=row.get("summary", ""),
            category=row.get("category", ""),
            action_items=row.get("action_items", ""),
            reply_strategy=row.get("reply_strategy", ""),
            draft_reply=self._draft_replies.get(row_id, ""),
        )


class EmailBotService:
    def __init__(
        self,
        analyzer: EmailAnalyzer,
        llm: LLMClient,
        db: LocalDB,
        sync_manager: SyncManager,
        gmail: GmailClient | None = None,
    ) -> None:
        self._analyzer = analyzer
        self._llm = llm
        self._db = db
        self._sync_manager = sync_manager
        self._gmail = gmail
        self.store = _DBBackedStore(db)
        self._chat_histories: dict[int, list[dict]] = {}

    # ── analysis ──────────────────────────────────────────────────────────────

    def run_analysis(self) -> int:
        """Run the email analyzer pipeline.

        Results are written to the local DB by the analyzer (when db is set).
        Returns the number of emails analyzed.
        """
        log.info("Starting email analysis pipeline")
        results = self._analyzer.analyze()
        log.info("Analysis complete: %d email(s) analyzed", len(results))
        return len(results)

    def sync_contacts(self) -> int:
        """Sync sender contact list from Notion into local DB.

        Returns the number of contacts synced.
        """
        return self._sync_manager.load_senders_from_notion()

    def push_to_notion(self) -> dict[str, int]:
        """Push all unsynced analyzed data to Notion.

        Returns a dict with counts: emails, action_items, senders.
        """
        return self._sync_manager.sync_to_notion()

    def load_from_notion(self) -> int:
        """Download emails from Notion into local DB.

        Returns the number of emails loaded.
        """
        return self._sync_manager.load_emails_from_notion()

    # ── briefing ──────────────────────────────────────────────────────────────

    def briefing(self) -> str:
        """Build a morning briefing: deterministic sections + LLM recommendation."""
        emails = self.store.all_emails()
        if not emails:
            return "No emails loaded. Use /analyze or /load first."

        today = datetime.date.today().isoformat()
        action_items = self._db.get_open_action_items()

        # ── Overview ──
        cats: dict[str, int] = {}
        for e in emails:
            cats[e.category] = cats.get(e.category, 0) + 1
        cat_line = ", ".join(f"{v} {k}" for k, v in sorted(cats.items(), key=lambda x: -x[1]))
        lines = [f"📊 OVERVIEW\n{len(emails)} emails: {cat_line}"]

        # ── Overdue items ──
        overdue = [a for a in action_items if a["due_date"] and a["due_date"] < today]
        if overdue:
            lines.append("\n🔴 OVERDUE")
            for a in overdue:
                src = f" ({a['source_email']})" if a["source_email"] else ""
                lines.append(f"  • [{a['priority']}] {a['title']} — due {a['due_date']}{src}")

        # ── Due today ──
        due_today = [a for a in action_items if a["due_date"] == today]
        if due_today:
            lines.append("\n🟡 DUE TODAY")
            for a in due_today:
                src = f" ({a['source_email']})" if a["source_email"] else ""
                lines.append(f"  • [{a['priority']}] {a['title']}{src}")

        # ── Upcoming (open, future or no date) ──
        upcoming = [a for a in action_items if a not in overdue and a not in due_today]
        if upcoming:
            lines.append("\n📋 OPEN ACTION ITEMS")
            for a in upcoming:
                due = f" — due {a['due_date']}" if a["due_date"] else ""
                lines.append(f"  • [{a['priority']}] {a['title']}{due}")

        if not action_items:
            lines.append("\n✅ No open action items.")

        # ── LLM recommendation ──
        briefing_text = "\n".join(lines)
        context = f"Briefing so far:\n{briefing_text}\n\nEmails analyzed: {len(emails)}, Open action items: {len(action_items)}, Overdue: {len(overdue)}, Due today: {len(due_today)}"
        prompt = BRIEFING_RECOMMENDATION_PROMPT.format(today=today, context=context)
        log.info("Generating briefing recommendation")
        recommendation = self._llm.complete(prompt, max_tokens=TG_BRIEFING_MAX_TOKENS)

        lines.append(f"\n💡 RECOMMENDATION\n{recommendation}")
        return "\n".join(lines)

    # ── draft reply ───────────────────────────────────────────────────────────

    def generate_reply_draft(self, row_index: int) -> str:
        """Generate a draft reply using LLM with email context + strategy."""
        email = self.store.get(row_index)
        if not email:
            log.warning("generate_reply_draft: email not found for row_index=%d", row_index)
            return "Email not found."

        prompt = DRAFT_REPLY_PROMPT.format(
            sender=email.sender,
            date=email.date,
            subject=email.subject,
            body=email.body,
            reply_strategy=email.reply_strategy,
        )
        log.info("Generating draft reply for row_index=%d subject=%s", row_index, email.subject)
        draft = self._llm.complete(prompt, max_tokens=TG_REPLY_DRAFT_MAX_TOKENS)
        self.store.set_draft_reply(row_index, draft)
        log.info("Draft reply generated: %d chars", len(draft))
        return draft

    # ── gmail draft ────────────────────────────────────────────────────────────

    def save_draft_to_gmail(self, row_index: int) -> str:
        """Save the generated draft reply as a Gmail draft.

        Returns the Gmail draft ID.
        """
        if not self._gmail:
            raise RuntimeError("Gmail is not configured.")

        email = self.store.get(row_index)
        if not email:
            raise ValueError("Email not found.")
        if not email.draft_reply:
            raise ValueError("No draft reply generated yet. Generate one first.")

        subject = f"Re: {email.subject}" if not email.subject.startswith("Re:") else email.subject
        log.info("Saving draft reply to Gmail for row_index=%d to=%s", row_index, email.sender)
        return self._gmail.create_draft(
            message=email.draft_reply,
            recipient=email.sender,
            subject=subject,
        )

    # ── chat ──────────────────────────────────────────────────────────────────

    def chat(self, user_id: int, message: str) -> str:
        """Multi-turn LLM chat with email context as system prompt."""
        log.debug("Chat message from user=%d: %s", user_id, message[:100])
        history = self._chat_histories.setdefault(user_id, [])
        history.append({"role": "user", "content": message})

        # Trim to max history length
        if len(history) > TG_CHAT_MAX_HISTORY:
            history[:] = history[-TG_CHAT_MAX_HISTORY:]

        system = self.store.as_context_summary()
        response = self._llm.chat(
            messages=history,
            system=system,
            max_tokens=TG_CHAT_MAX_TOKENS,
        )
        history.append({"role": "assistant", "content": response})
        return response

    def reset_chat(self, user_id: int) -> None:
        """Clear chat history for a user."""
        log.info("Chat history reset for user=%d", user_id)
        self._chat_histories.pop(user_id, None)
