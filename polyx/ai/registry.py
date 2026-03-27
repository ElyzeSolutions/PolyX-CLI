"""AI provider registry — factory for provider instances."""

from __future__ import annotations

from typing import TYPE_CHECKING

from polyx.exceptions import ConfigurationError

if TYPE_CHECKING:
    from polyx.ai.base import BaseProvider
    from polyx.config import Config


def get_provider(name: str, config: Config, model: str | None = None) -> BaseProvider:
    """Get an AI provider instance by name.

    If model starts with a provider name (e.g. 'gemini/'), it overrides the name.
    """
    if model and "/" in model:
        parts = model.split("/", 1)
        # Check if first part is a known provider
        if parts[0] in ("grok", "openrouter", "gemini"):
            name = parts[0]
            model = parts[1]

    if name == "grok":
        from polyx.ai.grok import GrokProvider
        return GrokProvider(config.xai_api_key, model=model)
    elif name == "openrouter":
        from polyx.ai.openrouter import OpenRouterProvider
        return OpenRouterProvider(config.openrouter_api_key, model=model)
    elif name == "gemini":
        from polyx.ai.gemini import GeminiProvider
        return GeminiProvider(config.gemini_api_key, model=model)
    else:
        raise ConfigurationError(f"Unknown AI provider: {name}. Available: grok, openrouter, gemini")
