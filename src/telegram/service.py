"""Business logic layer for the Telegram bot."""

from __future__ import annotations

import logging

from src.config import TG_REPLY_DRAFT_MAX_TOKENS, TG_CHAT_MAX_TOKENS, TG_CHAT_MAX_HISTORY
from src.llm.client import LLMClient
from src.agents.email_analyzer import EmailAnalyzer, AnalysisResult
from src.notion.client import NotionClient
from src.gmail.client import GmailClient
from src.telegram.context_store import AnalyzedEmail, EmailContextStore

log = logging.getLogger(__name__)


class EmailBotService:
    def __init__(
        self,
        analyzer: EmailAnalyzer,
        llm: LLMClient,
        notion: NotionClient | None = None,
        notion_emails_db_id: str | None = None,
        gmail: GmailClient | None = None,
    ) -> None:
        self._analyzer = analyzer
        self._llm = llm
        self._notion = notion
        self._notion_emails_db_id = notion_emails_db_id
        self._gmail = gmail
        self.store = EmailContextStore()
        self._chat_histories: dict[int, list[dict]] = {}

    # ── analysis ──────────────────────────────────────────────────────────────

    def run_analysis(self) -> int:
        """Run the email analyzer, write to Notion emails DB, load into store.

        Returns the number of emails analyzed.
        """
        results = self._analyzer.analyze()

        if results and self._notion and self._notion_emails_db_id:
            for r in results:
                try:
                    self._notion.write_email_analysis(
                        self._notion_emails_db_id,
                        {
                            "subject": r.subject,
                            "sender": r.sender,
                            "date": r.date,
                            "summary": r.summary,
                            "category": r.category,
                            "action_items": r.action_items,
                            "reply_strategy": r.reply_strategy,
                            "body": r.body,
                        },
                    )
                except Exception as exc:
                    log.error("Failed to write email analysis to Notion: %s", exc)

        self.store.load(self._results_to_analyzed(results))
        return len(results)

    def load_from_notion(self) -> int:
        """Read previously analyzed emails from Notion and load into store.

        Returns the number of emails loaded.
        """
        if not self._notion or not self._notion_emails_db_id:
            return 0

        pages = self._notion.read_email_analyses(self._notion_emails_db_id)
        emails = [
            AnalyzedEmail(
                row_index=i,
                sender=p.get("sender", ""),
                date=p.get("date", ""),
                subject=p.get("subject", ""),
                body=p.get("body", ""),
                summary=p.get("summary", ""),
                category=p.get("category", ""),
                action_items=p.get("action_items", ""),
                reply_strategy=p.get("reply_strategy", ""),
            )
            for i, p in enumerate(pages)
        ]
        self.store.load(emails)
        return len(emails)

    # ── draft reply ───────────────────────────────────────────────────────────

    def generate_reply_draft(self, row_index: int) -> str:
        """Generate a draft reply using LLM with email context + strategy."""
        email = self.store.get(row_index)
        if not email:
            return "Email not found."

        prompt = (
            "Write a professional email reply based on the original email and the "
            "reply strategy below. Write only the reply body — no subject line, "
            "no commentary.\n\n"
            f"Original email:\n"
            f"From: {email.sender}\n"
            f"Date: {email.date}\n"
            f"Subject: {email.subject}\n"
            f"Body: {email.body}\n\n"
            f"Reply Strategy:\n{email.reply_strategy}\n\n"
            "Draft reply:"
        )
        draft = self._llm.complete(prompt, max_tokens=TG_REPLY_DRAFT_MAX_TOKENS)
        self.store.set_draft_reply(row_index, draft)
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
        return self._gmail.create_draft(
            message=email.draft_reply,
            recipient=email.sender,
            subject=subject,
        )

    # ── chat ──────────────────────────────────────────────────────────────────

    def chat(self, user_id: int, message: str) -> str:
        """Multi-turn LLM chat with email context as system prompt."""
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
        self._chat_histories.pop(user_id, None)

    # ── internal ──────────────────────────────────────────────────────────────

    @staticmethod
    def _results_to_analyzed(results: list[AnalysisResult]) -> list[AnalyzedEmail]:
        return [
            AnalyzedEmail(
                row_index=r.row_index,
                sender=r.sender,
                date=r.date,
                subject=r.subject,
                body=r.body,
                summary=r.summary,
                category=r.category,
                action_items=r.action_items,
                reply_strategy=r.reply_strategy,
            )
            for r in results
        ]
