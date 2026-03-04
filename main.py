#!/usr/bin/env python3
"""Email Analyzer — reads emails from Google Sheets, analyzes with Claude, writes results back."""

import argparse
import sys

from src.config import Config
from src.llm.client import LLMClient
from src.sheets.client import SheetsClient
from src.console.renderer import EmailTableRenderer
from src.agents.email_analyzer import EmailAnalyzer


def main():
    parser = argparse.ArgumentParser(
        description="Analyze emails in a Google Sheet with Claude and write results back."
    )
    parser.add_argument("spreadsheet_id", help="Google Sheets spreadsheet ID")
    args = parser.parse_args()

    try:
        config = Config.from_env()
    except ValueError as e:
        sys.exit(f"Error: {e}")

    print("Authenticating with Google Sheets\u2026")
    try:
        sheets = SheetsClient(args.spreadsheet_id)
    except ValueError as e:
        sys.exit(f"Error: {e}")

    llm = LLMClient(config)
    renderer = EmailTableRenderer()

    try:
        EmailAnalyzer(llm, sheets, renderer).run()
    except ValueError as e:
        sys.exit(f"Error: {e}")


if __name__ == "__main__":
    main()
