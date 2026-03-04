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

# ── Priority levels ───────────────────────────────────────────────────────────
PRIORITY_LEVELS = ("CRITICAL", "HIGH", "MEDIUM", "LOW")
DEFAULT_PRIORITY = "Medium"
PRIORITY_TAG_RE = re.compile(r"\[(CRITICAL|HIGH|MEDIUM|LOW)\]\s*")

# ── Google Sheets paths / scopes ──────────────────────────────────────────────
TOKEN_PATH = "token.json"
CREDS_PATH = "credentials.json"
GOOGLE_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


@dataclass
class Config:
    anthropic_api_key: str
    anthropic_base_url: str | None = None
    notion_token: str | None = None
    notion_db_id: str | None = None

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
        )
