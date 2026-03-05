"""Centralised configuration — constants and environment variables."""

import os
import re
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()

# ── Email categories ───────────────────────────────────────────────────────────
CATEGORIES = {"Support", "Sales", "Spam", "Internal", "Finance", "Legal", "Other"}
DEFAULT_CATEGORY = "Other"

# ── LLM defaults ──────────────────────────────────────────────────────────────
DEFAULT_MODEL = "claude-sonnet-4-6"
DEFAULT_MAX_TOKENS = 1024
EMAIL_ANALYSIS_MAX_TOKENS = 2048
SENDER_SUMMARY_MAX_TOKENS = 256
LLM_MAX_WORKERS = 4

# ── Telegram bot ──────────────────────────────────────────────────────────────
TG_MAX_MESSAGE_LENGTH = 4096
TG_REPLY_DRAFT_MAX_TOKENS = 2048
TG_BRIEFING_MAX_TOKENS = 512
TG_CHAT_MAX_TOKENS = 1024
TG_CHAT_MAX_HISTORY = 20
TG_EMAILS_PER_PAGE = 5

# ── Priority levels ───────────────────────────────────────────────────────────
PRIORITY_LEVELS = ("CRITICAL", "HIGH", "MEDIUM", "LOW")
DEFAULT_PRIORITY = "Medium"
PRIORITY_TAG_RE = re.compile(r"\[(CRITICAL|HIGH|MEDIUM|LOW)\]\s*")

# ── Notion ────────────────────────────────────────────────────────────────────
# Pin to a stable API version — v3 client defaults to 2025-09-03 which removed
# databases/{id}/query and silently ignores property updates.
NOTION_API_VERSION = "2022-06-28"

# ── Google Sheets paths / scopes ──────────────────────────────────────────────
TOKEN_PATH = "token.json"
CREDS_PATH = "credentials.json"
GOOGLE_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

# ── Gmail ────────────────────────────────────────────────────────────────────
GMAIL_TOKEN_PATH = "gmail_token.json"
GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.compose"]

# ── Local DB cache ───────────────────────────────────────────────────────────
DEFAULT_DB_PATH = "data/email_cache.db"


@dataclass
class Config:
    anthropic_api_key: str
    anthropic_base_url: str | None = None
    notion_token: str | None = None
    notion_db_id: str | None = None
    notion_sender_db_id: str | None = None
    telegram_bot_token: str | None = None
    spreadsheet_id: str | None = None
    notion_emails_db_id: str | None = None

    @classmethod
    def from_env(cls) -> "Config":
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY not set. Add it to your .env file.")
        return cls(
            anthropic_api_key=api_key,
            anthropic_base_url=os.getenv("ANTHROPIC_BASE_URL"),
            notion_token=os.getenv("NOTION_TOKEN"),
            notion_db_id=os.getenv("NOTION_ACTION_ITEMS_DB_ID"),
            notion_sender_db_id=os.getenv("NOTION_SENDER_DB_ID"),
            telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN"),
            spreadsheet_id=os.getenv("SPREADSHEET_ID"),
            notion_emails_db_id=os.getenv("NOTION_EMAILS_DB_ID"),
        )
