"""SQLite local cache for email analysis data."""

from __future__ import annotations

import logging
import os
import sqlite3
import threading
from datetime import datetime

log = logging.getLogger(__name__)


class LocalDB:
    """SQLite access layer mirroring the three Notion databases.

    Uses WAL mode and check_same_thread=False for async bot thread safety.
    Each record tracks its provenance via ``source`` ('local' or 'notion')
    and a ``synced`` flag (0 = needs push, 1 = clean).
    """

    def __init__(self, db_path: str) -> None:
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._lock = threading.Lock()
        self._create_tables()
        log.info("LocalDB opened at %s", db_path)

    # ── schema ─────────────────────────────────────────────────────────────────

    def _create_tables(self) -> None:
        cur = self._conn.cursor()
        cur.executescript("""
            CREATE TABLE IF NOT EXISTS emails (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                subject     TEXT NOT NULL DEFAULT '',
                sender      TEXT NOT NULL DEFAULT '',
                date        TEXT NOT NULL DEFAULT '',
                summary     TEXT NOT NULL DEFAULT '',
                category    TEXT NOT NULL DEFAULT '',
                action_items TEXT NOT NULL DEFAULT '',
                reply_strategy TEXT NOT NULL DEFAULT '',
                body        TEXT NOT NULL DEFAULT '',
                source      TEXT NOT NULL DEFAULT 'local',
                synced      INTEGER NOT NULL DEFAULT 0,
                created_at  TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS action_items (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                title       TEXT NOT NULL DEFAULT '',
                priority    TEXT NOT NULL DEFAULT 'Medium',
                status      TEXT NOT NULL DEFAULT 'Open',
                category    TEXT NOT NULL DEFAULT 'Other',
                details     TEXT NOT NULL DEFAULT '',
                source_email TEXT NOT NULL DEFAULT '',
                due_date    TEXT,
                source      TEXT NOT NULL DEFAULT 'local',
                synced      INTEGER NOT NULL DEFAULT 0,
                created_at  TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS senders (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                email           TEXT NOT NULL UNIQUE,
                sender_name     TEXT NOT NULL DEFAULT '',
                manual_comment  TEXT NOT NULL DEFAULT '',
                ai_summary      TEXT NOT NULL DEFAULT '',
                last_contact_date TEXT NOT NULL DEFAULT '',
                email_count     INTEGER NOT NULL DEFAULT 0,
                source          TEXT NOT NULL DEFAULT 'local',
                synced          INTEGER NOT NULL DEFAULT 0,
                created_at      TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE INDEX IF NOT EXISTS idx_senders_email ON senders(email);
            CREATE INDEX IF NOT EXISTS idx_emails_synced ON emails(synced);
            CREATE INDEX IF NOT EXISTS idx_action_items_synced ON action_items(synced);
            CREATE INDEX IF NOT EXISTS idx_senders_synced ON senders(synced);
        """)
        self._conn.commit()

    # ── emails ─────────────────────────────────────────────────────────────────

    def insert_email(self, data: dict) -> int:
        """Insert a single email record. Returns the row id."""
        with self._lock:
            cur = self._conn.execute(
                """INSERT INTO emails
                   (subject, sender, date, summary, category, action_items,
                    reply_strategy, body, source, synced)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    data.get("subject", ""),
                    data.get("sender", ""),
                    data.get("date", ""),
                    data.get("summary", ""),
                    data.get("category", ""),
                    data.get("action_items", ""),
                    data.get("reply_strategy", ""),
                    data.get("body", ""),
                    data.get("source", "local"),
                    1 if data.get("synced") else 0,
                ),
            )
            self._conn.commit()
            return cur.lastrowid

    def insert_emails_batch(self, emails: list[dict]) -> int:
        """Insert multiple email records. Returns the number inserted."""
        with self._lock:
            self._conn.executemany(
                """INSERT INTO emails
                   (subject, sender, date, summary, category, action_items,
                    reply_strategy, body, source, synced)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                [
                    (
                        e.get("subject", ""),
                        e.get("sender", ""),
                        e.get("date", ""),
                        e.get("summary", ""),
                        e.get("category", ""),
                        e.get("action_items", ""),
                        e.get("reply_strategy", ""),
                        e.get("body", ""),
                        e.get("source", "local"),
                        1 if e.get("synced") else 0,
                    )
                    for e in emails
                ],
            )
            self._conn.commit()
            return len(emails)

    def get_all_emails(self) -> list[dict]:
        with self._lock:
            rows = self._conn.execute("SELECT * FROM emails ORDER BY id").fetchall()
            return [dict(r) for r in rows]

    def get_email(self, email_id: int) -> dict | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM emails WHERE id = ?", (email_id,)).fetchone()
            return dict(row) if row else None

    def get_unsynced_emails(self) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM emails WHERE source = 'local' AND synced = 0"
            ).fetchall()
            return [dict(r) for r in rows]

    def mark_email_synced(self, email_id: int) -> None:
        with self._lock:
            self._conn.execute("UPDATE emails SET synced = 1 WHERE id = ?", (email_id,))
            self._conn.commit()

    def clear_emails(self) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM emails")
            self._conn.commit()

    def clear_notion_emails(self) -> None:
        """Remove only Notion-sourced emails, preserving local ones."""
        with self._lock:
            self._conn.execute("DELETE FROM emails WHERE source = 'notion'")
            self._conn.commit()

    def clear_synced_local_emails(self) -> None:
        """Remove local emails already synced to Notion (they'll be re-imported)."""
        with self._lock:
            self._conn.execute("DELETE FROM emails WHERE source = 'local' AND synced = 1")
            self._conn.commit()

    # ── action items ───────────────────────────────────────────────────────────

    def insert_action_item(self, data: dict) -> int:
        with self._lock:
            cur = self._conn.execute(
                """INSERT INTO action_items
                   (title, priority, status, category, details, source_email,
                    due_date, source, synced)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    data.get("title", ""),
                    data.get("priority", "Medium"),
                    data.get("status", "Open"),
                    data.get("category", "Other"),
                    data.get("details", ""),
                    data.get("source_email", ""),
                    data.get("due_date"),
                    data.get("source", "local"),
                    1 if data.get("synced") else 0,
                ),
            )
            self._conn.commit()
            return cur.lastrowid

    def get_open_action_items(self) -> list[dict]:
        """Return all action items with status 'Open', ordered by priority and due date."""
        priority_order = "CASE priority WHEN 'Critical' THEN 1 WHEN 'High' THEN 2 WHEN 'Medium' THEN 3 WHEN 'Low' THEN 4 ELSE 5 END"
        with self._lock:
            rows = self._conn.execute(
                f"SELECT * FROM action_items WHERE status = 'Open' ORDER BY {priority_order}, due_date ASC"
            ).fetchall()
            return [dict(r) for r in rows]

    def get_unsynced_action_items(self) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM action_items WHERE source = 'local' AND synced = 0"
            ).fetchall()
            return [dict(r) for r in rows]

    def mark_action_item_synced(self, item_id: int) -> None:
        with self._lock:
            self._conn.execute("UPDATE action_items SET synced = 1 WHERE id = ?", (item_id,))
            self._conn.commit()

    # ── senders ────────────────────────────────────────────────────────────────

    def upsert_sender(self, data: dict) -> int:
        """Insert or update a sender record by email. Returns the row id."""
        with self._lock:
            now = datetime.now().isoformat()
            existing = self._conn.execute(
                "SELECT id, email_count FROM senders WHERE email = ?", (data["email"],)
            ).fetchone()

            if existing:
                self._conn.execute(
                    """UPDATE senders SET
                           sender_name = ?, ai_summary = ?, last_contact_date = ?,
                           email_count = ?, source = ?, synced = ?, updated_at = ?
                       WHERE id = ?""",
                    (
                        data.get("sender_name", ""),
                        data.get("ai_summary", ""),
                        data.get("last_contact_date", ""),
                        data.get("email_count", existing["email_count"] + 1),
                        data.get("source", "local"),
                        1 if data.get("synced") else 0,
                        now,
                        existing["id"],
                    ),
                )
                self._conn.commit()
                return existing["id"]
            else:
                cur = self._conn.execute(
                    """INSERT INTO senders
                       (email, sender_name, manual_comment, ai_summary,
                        last_contact_date, email_count, source, synced, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        data["email"],
                        data.get("sender_name", ""),
                        data.get("manual_comment", ""),
                        data.get("ai_summary", ""),
                        data.get("last_contact_date", ""),
                        data.get("email_count", 1),
                        data.get("source", "local"),
                        1 if data.get("synced") else 0,
                        now,
                        now,
                    ),
                )
                self._conn.commit()
                return cur.lastrowid

    def upsert_senders_batch(self, senders: list[dict]) -> int:
        """Bulk upsert sender records from Notion.

        For existing local senders: only updates ``manual_comment`` so that
        locally-generated fields (ai_summary, email_count, etc.) are preserved.
        For new senders: inserts the full record with source='notion', synced=1.
        Returns the number of records upserted.
        """
        with self._lock:
            now = datetime.now().isoformat()
            count = 0
            cur = self._conn.cursor()
            for s in senders:
                email = s.get("email", "")
                if not email:
                    continue
                existing = cur.execute(
                    "SELECT id FROM senders WHERE email = ?", (email,)
                ).fetchone()
                if existing:
                    cur.execute(
                        """UPDATE senders SET manual_comment = ?, updated_at = ?
                           WHERE id = ?""",
                        (
                            s.get("manual_comment", ""),
                            now,
                            existing["id"],
                        ),
                    )
                else:
                    cur.execute(
                        """INSERT INTO senders
                           (email, sender_name, manual_comment, ai_summary,
                            last_contact_date, email_count, source, synced,
                            created_at, updated_at)
                           VALUES (?, ?, ?, ?, ?, ?, 'notion', 1, ?, ?)""",
                        (
                            email,
                            s.get("name", ""),
                            s.get("manual_comment", ""),
                            s.get("ai_summary", ""),
                            s.get("last_contact_date", ""),
                            s.get("email_count", 0),
                            now,
                            now,
                        ),
                    )
                count += 1
            self._conn.commit()
            return count

    def get_sender(self, email: str) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM senders WHERE email = ?", (email,)
            ).fetchone()
            return dict(row) if row else None

    def get_unsynced_senders(self) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM senders WHERE source = 'local' AND synced = 0"
            ).fetchall()
            return [dict(r) for r in rows]

    def mark_sender_synced(self, sender_id: int) -> None:
        with self._lock:
            self._conn.execute("UPDATE senders SET synced = 1 WHERE id = ?", (sender_id,))
            self._conn.commit()

    # ── lifecycle ──────────────────────────────────────────────────────────────

    def close(self) -> None:
        with self._lock:
            self._conn.close()
        log.info("LocalDB closed")
