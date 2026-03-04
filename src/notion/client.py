"""Notion connector — internal integration auth + action item writer."""

from __future__ import annotations
import logging
import re
from notion_client import Client
from src.config import DEFAULT_CATEGORY, PRIORITY_TAG_RE, DEFAULT_PRIORITY

log = logging.getLogger(__name__)


class NotionClient:
    """
    Notion connector — internal integration auth + action item writer
    """

    def __init__(self, token: str) -> None:
        self._client = Client(auth=token)

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

    def get_sender(self, database_id: str, email: str) -> dict | None:
        """Query sender database by email address.

        Returns dict with keys: email, name, manual_comment, ai_summary,
        last_contact_date, email_count.
        Returns None if sender not found or on error.
        """
        try:
            response = self._client.databases.query(
                database_id=database_id,
                filter={"property": "Email", "title": {"equals": email}},
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
        try:
            response = self._client.databases.query(
                database_id=database_id,
                filter={"property": "Email", "title": {"equals": email}},
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
