"""Anthropic API-key provider, separate from Claude Code subscription auth."""

from __future__ import annotations

from typing import Any

import httpx

from polyx.ai.base import BaseProvider
from polyx.exceptions import PolyXError


class AnthropicProvider(BaseProvider):
    PROVIDER_NAME = "claude"
    BASE_URL = "https://api.anthropic.com/v1"
    ENV_KEY = "ANTHROPIC_API_KEY"
    DEFAULT_MODEL = "claude-sonnet-4-6"

    async def _chat(self, messages: list[dict[str, str]], temperature: float = 0.3) -> str:
        system_parts = [item["content"] for item in messages if item["role"] == "system"]
        user_messages = [item for item in messages if item["role"] != "system"]
        body: dict[str, Any] = {
            "model": self._model,
            "max_tokens": 4_096,
            "messages": user_messages,
            "temperature": temperature,
        }
        if system_parts:
            body["system"] = "\n".join(system_parts)
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                f"{self.BASE_URL}/messages",
                headers={
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                    "x-api-key": self._api_key,
                },
                json=body,
            )
        if response.status_code >= 400:
            raise PolyXError(f"claude API error {response.status_code}")
        try:
            payload = response.json()
            blocks = payload["content"]
            text = "".join(
                block["text"]
                for block in blocks
                if isinstance(block, dict)
                and block.get("type") == "text"
                and isinstance(block.get("text"), str)
            )
        except (KeyError, TypeError, ValueError) as error:
            raise PolyXError("claude API returned an invalid response") from error
        if not text:
            raise PolyXError("claude API returned no text")
        return text
