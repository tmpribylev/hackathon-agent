"""Notion connector — internal integration auth + action item writer."""

from __future__ import annotations

import logging
import os
import re

from dotenv import load_dotenv
from notion_client import Client

log = logging.getLogger(__name__)

load_dotenv()

_PRIORITY_TAG_RE = re.compile(r"\[(CRITICAL|HIGH|MEDIUM|LOW)\]\s*")


class NotionClient:
    def __init__(self) -> None:
        token = os.getenv("NOTION_TOKEN")
        if not token:
            raise RuntimeError("NOTION_TOKEN must be set in .env.")
        self._client = Client(auth=token)

    def write_action_items(
        self,
        database_id: str,
        action_items: str,
        *,
        category: str = "Other",
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
                properties["Details"] = {"rich_text": [{"text": {"content": item["details"][:2000]}}]}
            if source_email:
                properties["Source Email"] = {"rich_text": [{"text": {"content": source_email[:2000]}}]}
            if item["due"]:
                properties["Due Date"] = {"date": {"start": item["due"]}}

            self._client.pages.create(
                parent={"database_id": database_id},
                properties=properties,
            )
            log.debug("Created Notion page: %s [%s]", item["title"], item["priority"])
        return len(items)

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
                priority = "Medium"
                match = _PRIORITY_TAG_RE.search(title)
                if match:
                    priority = match.group(1).capitalize()
                    title = _PRIORITY_TAG_RE.sub("", title).strip()
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
