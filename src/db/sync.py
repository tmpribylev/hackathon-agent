"""Sync manager — coordinates LocalDB <-> Notion data transfer."""

from __future__ import annotations

import logging

from src.db.client import LocalDB
from src.notion.client import NotionClient

log = logging.getLogger(__name__)


class SyncManager:
    """Pushes dirty local records to Notion and loads Notion data into SQLite."""

    def __init__(
        self,
        db: LocalDB,
        notion: NotionClient | None,
        notion_db_id: str | None = None,
        notion_emails_db_id: str | None = None,
        notion_sender_db_id: str | None = None,
    ) -> None:
        self._db = db
        self._notion = notion
        self._notion_db_id = notion_db_id
        self._notion_emails_db_id = notion_emails_db_id
        self._notion_sender_db_id = notion_sender_db_id

    # ── push to Notion ─────────────────────────────────────────────────────────

    def sync_to_notion(self) -> dict[str, int]:
        """Push all unsynced local records to Notion.

        Returns a dict with counts: emails, action_items, senders (each synced).
        Errors are logged per-record; partial sync is fine.
        """
        counts = {"emails": 0, "action_items": 0, "senders": 0}

        if not self._notion:
            log.info("Notion not configured, skipping sync")
            return counts

        # ── emails ──
        if self._notion_emails_db_id:
            for email in self._db.get_unsynced_emails():
                try:
                    self._notion.write_email_analysis(
                        self._notion_emails_db_id,
                        {
                            "subject": email["subject"],
                            "sender": email["sender"],
                            "date": email["date"],
                            "summary": email["summary"],
                            "category": email["category"],
                            "action_items": email["action_items"],
                            "reply_strategy": email["reply_strategy"],
                            "body": email["body"],
                        },
                    )
                    self._db.mark_email_synced(email["id"])
                    counts["emails"] += 1
                except Exception as exc:
                    log.error("Failed to sync email id=%d to Notion: %s", email["id"], exc)

        # ── action items ──
        if self._notion_db_id:
            for item in self._db.get_unsynced_action_items():
                try:
                    self._notion.write_single_action_item(
                        self._notion_db_id,
                        title=item["title"],
                        priority=item["priority"],
                        category=item["category"],
                        details=item["details"],
                        source_email=item["source_email"],
                        due_date=item["due_date"],
                    )
                    self._db.mark_action_item_synced(item["id"])
                    counts["action_items"] += 1
                except Exception as exc:
                    log.error(
                        "Failed to sync action item id=%d to Notion: %s", item["id"], exc
                    )

        # ── senders ──
        if self._notion_sender_db_id:
            for sender in self._db.get_unsynced_senders():
                try:
                    self._notion.upsert_sender(
                        self._notion_sender_db_id,
                        sender["email"],
                        sender["sender_name"],
                        sender["ai_summary"],
                        sender["last_contact_date"],
                    )
                    self._db.mark_sender_synced(sender["id"])
                    counts["senders"] += 1
                except Exception as exc:
                    log.error(
                        "Failed to sync sender id=%d to Notion: %s", sender["id"], exc
                    )

        log.info(
            "Sync complete: %d email(s), %d action item(s), %d sender(s)",
            counts["emails"],
            counts["action_items"],
            counts["senders"],
        )
        return counts

    # ── load from Notion ───────────────────────────────────────────────────────

    def load_senders_from_notion(self) -> int:
        """Download all senders from Notion into SQLite.

        Merges into existing sender records (upsert). Local-only senders
        not present in Notion are preserved.
        Returns the number of senders synced.
        """
        if not self._notion or not self._notion_sender_db_id:
            log.info("Notion sender DB not configured, skipping contact sync")
            return 0

        log.info("Loading senders from Notion into local DB")
        senders = self._notion.read_all_senders(self._notion_sender_db_id)
        count = self._db.upsert_senders_batch(senders)
        log.info("Synced %d sender(s) from Notion into local DB", count)
        return count

    def load_action_items_from_notion(self) -> int:
        """Download all action items from Notion into SQLite.

        Clears previously loaded Notion action items, then inserts fresh ones
        with source='notion' and synced=True so they are never re-uploaded.
        Locally created action items are preserved.
        Returns the number of action items loaded.
        """
        if not self._notion or not self._notion_db_id:
            log.info("Notion action items DB not configured, skipping load")
            return 0

        log.info("Loading action items from Notion into local DB")
        items = self._notion.read_all_action_items(self._notion_db_id)

        self._db.clear_notion_action_items()
        self._db.clear_synced_local_action_items()
        self._db.insert_action_items_batch(
            [
                {
                    "title": item.get("title", ""),
                    "priority": item.get("priority", "Medium"),
                    "status": item.get("status", "Open"),
                    "category": item.get("category", "Other"),
                    "details": item.get("details", ""),
                    "source_email": item.get("source_email", ""),
                    "due_date": item.get("due_date"),
                    "source": "notion",
                    "synced": True,
                }
                for item in items
            ]
        )

        log.info("Loaded %d action item(s) from Notion into local DB", len(items))
        return len(items)

    def load_emails_from_notion(self) -> int:
        """Download all emails from Notion into SQLite.

        Clears previously loaded Notion emails, then inserts fresh ones with
        source='notion' and synced=True so they are never re-uploaded.
        Locally analyzed emails are preserved.
        Returns the number of emails loaded.
        """
        if not self._notion or not self._notion_emails_db_id:
            log.info("Notion not configured, skipping load")
            return 0

        log.info("Loading emails from Notion into local DB")
        pages = self._notion.read_email_analyses(self._notion_emails_db_id)

        self._db.clear_notion_emails()
        self._db.clear_synced_local_emails()
        self._db.insert_emails_batch(
            [
                {
                    "subject": p.get("subject", ""),
                    "sender": p.get("sender", ""),
                    "date": p.get("date", ""),
                    "summary": p.get("summary", ""),
                    "category": p.get("category", ""),
                    "action_items": p.get("action_items", ""),
                    "reply_strategy": p.get("reply_strategy", ""),
                    "body": p.get("body", ""),
                    "source": "notion",
                    "synced": True,
                }
                for p in pages
            ]
        )

        log.info("Loaded %d email(s) from Notion into local DB", len(pages))
        return len(pages)
