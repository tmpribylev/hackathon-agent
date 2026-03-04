"""Thin wrapper around the Anthropic SDK."""

import logging

import anthropic

from src.config import Config

log = logging.getLogger(__name__)


class LLMClient:
    def __init__(self, config: Config) -> None:
        kwargs: dict = {"api_key": config.anthropic_api_key}
        if config.anthropic_base_url:
            kwargs["base_url"] = config.anthropic_base_url
        self._client = anthropic.Anthropic(**kwargs)

    def complete(
        self, prompt: str, max_tokens: int = 1024, model: str = "claude-sonnet-4-6"
    ) -> str:
        """Send a single-turn prompt and return the response text."""
        log.debug("LLM request: model=%s, max_tokens=%d", model, max_tokens)
        message = self._client.messages.create(
            model=model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        text = message.content[0].text.strip()
        log.debug("LLM response: %d chars", len(text))
        return text
