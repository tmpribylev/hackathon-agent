#!/usr/bin/env python3
"""Email Analyzer — reads emails from Google Sheets, analyzes with Claude, writes results back."""

import argparse
import logging
import sys

from src.config import Config
from src.logger import setup_logging
from src.llm.client import LLMClient
from src.sheets.client import SheetsClient
from src.console.renderer import EmailTableRenderer
from src.agents.email_analyzer import EmailAnalyzer
from src.notion.client import NotionClient
from src.gmail.client import GmailClient

log = logging.getLogger(__name__)


def main():
    setup_logging()

    parser = argparse.ArgumentParser(
        description="Analyze emails in a Google Sheet with Claude and write results back."
    )
    parser.add_argument(
        "spreadsheet_id",
        nargs="?",
        default=None,
        help="Google Sheets spreadsheet ID (overrides .env)",
    )
    args = parser.parse_args()

    try:
        config = Config.from_env()
    except ValueError as e:
        log.error("Configuration error: %s", e)
        sys.exit(f"Error: {e}")

    spreadsheet_id = args.spreadsheet_id or config.spreadsheet_id
    if not spreadsheet_id:
        log.error("No spreadsheet ID provided")
        sys.exit("Error: Provide SPREADSHEET_ID via .env or as a CLI argument.")

    log.info("Starting email analyzer for spreadsheet %s", spreadsheet_id)

    print("Authenticating with Google Sheets\u2026")
    try:
        sheets = SheetsClient(spreadsheet_id)
    except ValueError as e:
        log.error("Sheets authentication failed: %s", e)
        sys.exit(f"Error: {e}")

    notion = None
    notion_db_id = config.notion_db_id
    if notion_db_id and config.notion_token:
        notion = NotionClient(config.notion_token)
        print("Connected to Notion.")

    llm = LLMClient(config)
    renderer = EmailTableRenderer()

    try:
        # First time it will fire a confirmation window
        gmail = GmailClient()

        # Create a test draft
        draft_id = gmail.create_draft(
            message="Test draft from Python",
            recipient="your-email@example.com",
            subject="Test Draft",
        )
        print(f"Draft created: {draft_id}")
    except ValueError as e:
        log.error("Gmail drafting client failed: %s", e)
        sys.exit(f"Error: {e}")

    try:
        EmailAnalyzer(llm, sheets, renderer, notion, notion_db_id).run()
    except ValueError as e:
        log.error("Analyzer failed: %s", e)
        sys.exit(f"Error: {e}")

    log.info("Run complete.")


if __name__ == "__main__":
    main()
