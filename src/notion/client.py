"""Notion connector — internal integration auth + action item writer."""

from __future__ import annotations
import logging
import re
from datetime import datetime
from notion_client import Client
from src.config import DEFAULT_CATEGORY, PRIORITY_TAG_RE, DEFAULT_PRIORITY, NOTION_API_VERSION

log = logging.getLogger(__name__)


class NotionClient:
    """
    Notion connector — internal integration auth + action item writer
    """

    def __init__(self, token: str) -> None:
        self._client = Client(auth=token, notion_version=NOTION_API_VERSION)

    def write_action_items(
        self,
        database_id: str,
        action_items: str,
        *,
        category: str = DEFAULT_CATEGORY,
        source_email: str = "",
    ) -> int:
        """Parse structured action items and create a Notion page for each one.

        Expected format per item:
            - [HIGH] Short title
              Details: Longer explanation...
              Due: 2026-03-07  (or "none")

        Returns the number of pages created.
        """
        items = self._parse_action_items(action_items)
        log.info("Creating %d action item(s) in Notion database %s", len(items), database_id)
        for item in items:
            properties: dict = {
                "Action Item": {"title": [{"text": {"content": item["title"]}}]},
                "Priority": {"select": {"name": item["priority"]}},
                "Status": {"select": {"name": "Open"}},
                "Category": {"select": {"name": category}},
            }
            if item["details"]:
                properties["Details"] = {
                    "rich_text": [{"text": {"content": item["details"][:2000]}}]
                }
            if source_email:
                properties["Source Email"] = {
                    "rich_text": [{"text": {"content": source_email[:2000]}}]
                }
            if item["due"]:
                properties["Due Date"] = {"date": {"start": item["due"]}}

            self._client.pages.create(
                parent={"database_id": database_id},
                properties=properties,
            )
            log.debug("Created Notion page: %s [%s]", item["title"], item["priority"])
        return len(items)

    def write_single_action_item(
        self,
        database_id: str,
        *,
        title: str,
        priority: str = "Medium",
        category: str = DEFAULT_CATEGORY,
        details: str = "",
        source_email: str = "",
        due_date: str | None = None,
    ) -> None:
        """Write a single pre-parsed action item to Notion."""
        properties: dict = {
            "Action Item": {"title": [{"text": {"content": title}}]},
            "Priority": {"select": {"name": priority}},
            "Status": {"select": {"name": "Open"}},
            "Category": {"select": {"name": category}},
        }
        if details:
            properties["Details"] = {
                "rich_text": [{"text": {"content": details[:2000]}}]
            }
        if source_email:
            properties["Source Email"] = {
                "rich_text": [{"text": {"content": source_email[:2000]}}]
            }
        if due_date:
            properties["Due Date"] = {"date": {"start": due_date}}

        self._client.pages.create(
            parent={"database_id": database_id},
            properties=properties,
        )
        log.debug("Created single Notion action item: %s [%s]", title, priority)

    def get_sender(self, database_id: str, email: str) -> dict | None:
        """Query sender database by email address.

        Returns dict with keys: email, name, manual_comment, ai_summary,
        last_contact_date, email_count.
        Returns None if sender not found or on error.
        """
        try:
            response = self._client.request(
                path=f"databases/{database_id}/query",
                method="POST",
                body={"filter": {"property": "Email", "title": {"equals": email}}},
            )

            if not response.get("results"):
                log.debug("Sender not found: %s", email)
                return None

            page = response["results"][0]
            props = page["properties"]

            sender_data = {
                "email": email,
                "name": self._extract_rich_text(props.get("Sender Name", {})),
                "manual_comment": self._extract_rich_text(props.get("Manual Comment", {})),
                "ai_summary": self._extract_rich_text(props.get("AI Summary", {})),
                "last_contact_date": self._extract_date(props.get("Last Contact Date", {})),
                "email_count": props.get("Email Count", {}).get("number", 0),
            }

            log.debug("Found sender: %s (count: %d)", email, sender_data["email_count"])
            return sender_data

        except Exception as exc:
            log.error("Failed to query sender %s: %s", email, exc)
            return None

    def upsert_sender(
        self,
        database_id: str,
        email: str,
        name: str,
        ai_summary: str,
        last_email_date: str,
    ) -> None:
        """Create or update sender in database.

        If sender exists: updates AI Summary, Last Contact Date, increments Email Count.
        If sender is new: creates page with all fields.
        Preserves Manual Comment field (never overwrites).
        """
        last_email_date = self._normalize_date(last_email_date)
        try:
            response = self._client.request(
                path=f"databases/{database_id}/query",
                method="POST",
                body={"filter": {"property": "Email", "title": {"equals": email}}},
            )

            if response.get("results"):
                page_id = response["results"][0]["id"]
                current_count = (
                    response["results"][0]["properties"].get("Email Count", {}).get("number", 0)
                )

                self._client.pages.update(
                    page_id=page_id,
                    properties={
                        "AI Summary": {"rich_text": [{"text": {"content": ai_summary[:2000]}}]},
                        "Last Contact Date": {"date": {"start": last_email_date}},
                        "Email Count": {"number": current_count + 1},
                    },
                )
                log.info(
                    "Updated sender: %s (count: %d -> %d)",
                    email,
                    current_count,
                    current_count + 1,
                )
            else:
                self._client.pages.create(
                    parent={"database_id": database_id},
                    properties={
                        "Email": {"title": [{"text": {"content": email}}]},
                        "Sender Name": {"rich_text": [{"text": {"content": name[:2000]}}]},
                        "Manual Comment": {"rich_text": []},
                        "AI Summary": {"rich_text": [{"text": {"content": ai_summary[:2000]}}]},
                        "Last Contact Date": {"date": {"start": last_email_date}},
                        "Email Count": {"number": 1},
                    },
                )
                log.info("Created new sender: %s", email)

        except Exception as exc:
            log.error("Failed to upsert sender %s: %s", email, exc)

    @staticmethod
    def _normalize_date(date_str: str) -> str:
        """Convert a human-readable date string to ISO 8601 (YYYY-MM-DD).

        Handles formats like "March 4, 2026 at 10:35 AM CET".
        Returns the original string if already ISO 8601 or unparseable.
        """
        if re.match(r"\d{4}-\d{2}-\d{2}", date_str):
            return date_str[:10]
        cleaned = re.sub(r"\s+at\s+", " ", date_str)
        cleaned = re.sub(r"\s+[A-Z]{2,5}$", "", cleaned)
        for fmt in ("%B %d, %Y %I:%M %p", "%B %d, %Y", "%b %d, %Y %I:%M %p", "%b %d, %Y"):
            try:
                return datetime.strptime(cleaned, fmt).date().isoformat()
            except ValueError:
                continue
        log.warning("Could not parse date '%s', using as-is", date_str)
        return date_str

    @staticmethod
    def _extract_rich_text(prop: dict) -> str:
        """Extract text content from Notion rich_text property."""
        rich_text = prop.get("rich_text", [])
        if not rich_text:
            return ""
        return "".join(item.get("text", {}).get("content", "") for item in rich_text)

    @staticmethod
    def _extract_date(prop: dict) -> str:
        """Extract date string from Notion date property."""
        date_obj = prop.get("date")
        if not date_obj:
            return ""
        return date_obj.get("start", "")
    def read_all_senders(self, database_id: str) -> list[dict]:
        """Read all sender pages from the Notion sender database.

        Returns list of dicts with keys: email, name, manual_comment,
        ai_summary, last_contact_date, email_count.
        """
        results: list[dict] = []
        has_more = True
        start_cursor = None

        while has_more:
            body: dict = {"page_size": 100}
            if start_cursor:
                body["start_cursor"] = start_cursor

            try:
                response = self._client.request(
                    path=f"databases/{database_id}/query",
                    method="POST",
                    body=body,
                )
            except Exception as exc:
                log.error("Failed to query sender DB %s: %s", database_id, exc)
                return results

            for page in response.get("results", []):
                props = page.get("properties", {})
                results.append(
                    {
                        "email": self._get_title_text(props.get("Email", {})),
                        "name": self._extract_rich_text(props.get("Sender Name", {})),
                        "manual_comment": self._extract_rich_text(
                            props.get("Manual Comment", {})
                        ),
                        "ai_summary": self._extract_rich_text(props.get("AI Summary", {})),
                        "last_contact_date": self._extract_date(
                            props.get("Last Contact Date", {})
                        ),
                        "email_count": props.get("Email Count", {}).get("number", 0),
                    }
                )

            has_more = response.get("has_more", False)
            start_cursor = response.get("next_cursor")

        log.info(
            "Read %d sender(s) from Notion database %s", len(results), database_id
        )
        return results

    def write_email_analysis(self, database_id: str, email_data: dict) -> None:
        """Write a full email analysis page to the Notion Emails database.

        email_data keys: subject, sender, date, summary, category,
                         action_items, reply_strategy, body

        On first call, ensures the database has the required properties.
        """
        self._ensure_emails_db_schema(database_id)

        properties: dict = {
            "Subject": {"title": [{"text": {"content": email_data.get("subject", "")[:2000]}}]},
            "Sender": {"rich_text": [{"text": {"content": email_data.get("sender", "")[:2000]}}]},
            "Date": {"rich_text": [{"text": {"content": email_data.get("date", "")[:2000]}}]},
            "Summary": {"rich_text": [{"text": {"content": email_data.get("summary", "")[:2000]}}]},
            "Category": {"select": {"name": email_data.get("category", DEFAULT_CATEGORY)}},
        }
        if email_data.get("action_items"):
            properties["Action Items"] = {
                "rich_text": [{"text": {"content": email_data["action_items"][:2000]}}]
            }
        if email_data.get("reply_strategy"):
            properties["Reply Strategy"] = {
                "rich_text": [{"text": {"content": email_data["reply_strategy"][:2000]}}]
            }
        if email_data.get("body"):
            properties["Body"] = {"rich_text": [{"text": {"content": email_data["body"][:2000]}}]}

        self._client.pages.create(
            parent={"database_id": database_id},
            properties=properties,
        )
        log.debug("Wrote email analysis to Notion: %s", email_data.get("subject", ""))

    def read_email_analyses(self, database_id: str) -> list[dict]:
        """Read all email analysis pages from the Notion Emails database.

        Returns list of dicts with keys: subject, sender, date, summary,
        category, action_items, reply_strategy, body.
        """
        results: list[dict] = []
        has_more = True
        start_cursor = None

        while has_more:
            body: dict = {"page_size": 100}
            if start_cursor:
                body["start_cursor"] = start_cursor
            response = self._client.request(
                path=f"databases/{database_id}/query",
                method="POST",
                body=body,
            )

            for page in response.get("results", []):
                props = page.get("properties", {})
                results.append(
                    {
                        "subject": self._get_title_text(props.get("Subject", {})),
                        "sender": self._get_rich_text(props.get("Sender", {})),
                        "date": self._get_rich_text(props.get("Date", {})),
                        "summary": self._get_rich_text(props.get("Summary", {})),
                        "category": self._get_select_name(props.get("Category", {})),
                        "action_items": self._get_rich_text(props.get("Action Items", {})),
                        "reply_strategy": self._get_rich_text(props.get("Reply Strategy", {})),
                        "body": self._get_rich_text(props.get("Body", {})),
                    }
                )

            has_more = response.get("has_more", False)
            start_cursor = response.get("next_cursor")

        log.info(
            "Read %d email analysis page(s) from Notion database %s", len(results), database_id
        )
        return results

    _emails_db_ready: set[str] = set()

    def _ensure_emails_db_schema(self, database_id: str) -> None:
        """Add missing properties to the Notion Emails database (idempotent)."""
        if database_id in self._emails_db_ready:
            return

        db = self._client.databases.retrieve(database_id)
        existing = set(db.get("properties", {}).keys())

        needed: dict = {}
        # Title property — Notion databases always have exactly one title column.
        # If the existing title column isn't called "Subject", rename it.
        if "Subject" not in existing:
            # Find the current title property name
            for name, prop in db.get("properties", {}).items():
                if prop.get("type") == "title":
                    needed[name] = {"name": "Subject", "title": {}}
                    break
        for field in ("Sender", "Date", "Summary", "Action Items", "Reply Strategy", "Body"):
            if field not in existing:
                needed[field] = {"rich_text": {}}
        if "Category" not in existing:
            needed["Category"] = {"select": {}}

        if needed:
            log.info("Adding missing properties to Notion Emails DB: %s", list(needed.keys()))
            # databases.update() in notion-client v3 drops "properties" via pick(),
            # so we use client.request() directly.
            self._client.request(
                path=f"databases/{database_id}",
                method="PATCH",
                body={"properties": needed},
            )

        self._emails_db_ready.add(database_id)

    @staticmethod
    def _get_title_text(prop: dict) -> str:
        items = prop.get("title", [])
        return items[0].get("plain_text", "") if items else ""

    @staticmethod
    def _get_rich_text(prop: dict) -> str:
        items = prop.get("rich_text", [])
        return items[0].get("plain_text", "") if items else ""

    @staticmethod
    def _get_select_name(prop: dict) -> str:
        select = prop.get("select")
        return select.get("name", "") if select else ""

    @staticmethod
    def _parse_action_items(text: str) -> list[dict]:
        """Parse multi-line action items into structured dicts.

        Returns list of {"title", "priority", "details", "due"}.
        """
        items: list[dict] = []
        current: dict | None = None

        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                continue

            # New action item line starts with "- "
            if raw_line.lstrip().startswith("- "):
                if current:
                    items.append(current)
                title = line.lstrip("- ")
                priority = DEFAULT_PRIORITY
                match = PRIORITY_TAG_RE.search(title)
                if match:
                    priority = match.group(1).capitalize()
                    title = PRIORITY_TAG_RE.sub("", title).strip()
                current = {
                    "title": title,
                    "priority": priority,
                    "details": "",
                    "due": None,
                }
            elif current is not None:
                if line.startswith("Details:"):
                    current["details"] = line[len("Details:") :].strip()
                elif line.startswith("Due:"):
                    due_val = line[len("Due:") :].strip()
                    if due_val.lower() != "none" and re.match(r"\d{4}-\d{2}-\d{2}", due_val):
                        current["due"] = due_val[:10]

        if current:
            items.append(current)
        return items
