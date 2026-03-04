"""Notion connector — internal integration auth + read/write."""

import os
import re

from dotenv import load_dotenv
from notion_client import Client

load_dotenv()

_PRIORITY_TAG_RE = re.compile(r"\[(HIGH|MEDIUM|LOW)\]\s*")


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
    ) -> int:
        """Parse action items and create a Notion page for each one.

        action_items — multi-line string like:
            - [HIGH] Respond to client complaint
            - [LOW] Archive the thread

        Returns the number of pages created.
        """
        created = 0
        for line in action_items.splitlines():
            line = line.strip().lstrip("- ")
            if not line:
                continue

            priority = "Medium"  # default
            match = _PRIORITY_TAG_RE.search(line)
            if match:
                priority = match.group(1).capitalize()  # High / Medium / Low
                line = _PRIORITY_TAG_RE.sub("", line).strip()

            if not line:
                continue

            self._client.pages.create(
                parent={"database_id": database_id},
                properties={
                    "Action Item": {"title": [{"text": {"content": line}}]},
                    "Priority": {"select": {"name": priority}},
                    "Status": {"select": {"name": "Open"}},
                },
            )
            created += 1

        return created
