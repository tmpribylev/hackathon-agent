"""Centralised configuration — reads environment variables once."""

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    anthropic_api_key: str
    anthropic_base_url: str | None = None

    @classmethod
    def from_env(cls) -> "Config":
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY not set. Add it to your .env file.")
        return cls(
            anthropic_api_key=api_key,
            anthropic_base_url=os.getenv("ANTHROPIC_BASE_URL"),
        )
