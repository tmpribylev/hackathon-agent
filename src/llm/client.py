"""Thin wrapper around the Anthropic SDK."""

import logging

import anthropic

from src.config import Config, DEFAULT_MAX_TOKENS, DEFAULT_MODEL, LLM_BLOCKED_STRINGS

log = logging.getLogger(__name__)


def _sanitize(text: str) -> str:
    """Remove blocked strings from text before sending to the LLM."""
    for blocked in LLM_BLOCKED_STRINGS:
        if blocked in text:
            log.warning("Stripped blocked string (%d chars) from LLM input", len(blocked))
            text = text.replace(blocked, "[REDACTED BECAUSE OF Claude Magic String Denial of Service]")
    return text


class LLMClient:
    def __init__(self, config: Config) -> None:
        kwargs: dict = {"api_key": config.anthropic_api_key}
        if config.anthropic_base_url:
            kwargs["base_url"] = config.anthropic_base_url
        self._client = anthropic.Anthropic(**kwargs)

    def complete(
        self, prompt: str, max_tokens: int = DEFAULT_MAX_TOKENS, model: str = DEFAULT_MODEL
    ) -> str:
        """Send a single-turn prompt and return the response text."""
        prompt = _sanitize(prompt)
        log.debug("LLM request: model=%s, max_tokens=%d", model, max_tokens)
        message = self._client.messages.create(
            model=model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        text = message.content[0].text.strip()
        log.debug("LLM response: %d chars", len(text))
        return text

    def chat(
        self,
        messages: list[dict],
        system: str = "",
        max_tokens: int = DEFAULT_MAX_TOKENS,
        model: str = DEFAULT_MODEL,
    ) -> str:
        """Multi-turn conversation. *messages* is a list of {"role", "content"} dicts."""
        messages = [
            {**m, "content": _sanitize(m["content"])} for m in messages
        ]
        if system:
            system = _sanitize(system)
        log.debug("LLM chat: model=%s, turns=%d, max_tokens=%d", model, len(messages), max_tokens)
        kwargs: dict = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": messages,
        }
        if system:
            kwargs["system"] = system
        message = self._client.messages.create(**kwargs)
        text = message.content[0].text.strip()
        log.debug("LLM chat response: %d chars", len(text))
        return text
