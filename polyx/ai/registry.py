"""AI provider registry — factory for provider instances."""

from __future__ import annotations

from typing import TYPE_CHECKING

from polyx.exceptions import ConfigurationError

if TYPE_CHECKING:
    from polyx.ai.base import BaseProvider
    from polyx.config import Config


def get_provider(name: str, config: Config, model: str | None = None) -> BaseProvider:
    """Get the explicitly selected provider and optional provider-native model."""

    if name == "grok":
        from polyx.ai.grok import GrokProvider
        return GrokProvider(config.xai_api_key, model=model)
    elif name == "openai":
        from polyx.ai.openai import OpenAIProvider

        return OpenAIProvider(config.openai_api_key, model=model)
    elif name == "claude":
        from polyx.ai.anthropic import AnthropicProvider

        return AnthropicProvider(config.anthropic_api_key, model=model)
    elif name == "grok-subscription":
        _require_subscription_enabled(name, config)
        from polyx.ai.grok_subscription import GrokSubscriptionProvider

        return GrokSubscriptionProvider(model=model)
    elif name == "codex-subscription":
        _require_subscription_enabled(name, config)
        from polyx.ai.subscription_cli import CodexSubscriptionProvider

        return CodexSubscriptionProvider(model=model)
    elif name == "claude-subscription":
        _require_subscription_enabled(name, config)
        from polyx.ai.subscription_cli import ClaudeSubscriptionProvider

        return ClaudeSubscriptionProvider(model=model)
    elif name == "cursor-subscription":
        _require_subscription_enabled(name, config)
        from polyx.ai.subscription_cli import CursorSubscriptionProvider

        return CursorSubscriptionProvider(model=model)
    elif name == "antigravity-subscription":
        _require_subscription_enabled(name, config)
        from polyx.ai.subscription_cli import AntigravitySubscriptionProvider

        return AntigravitySubscriptionProvider(model=model)
    elif name == "openrouter":
        from polyx.ai.openrouter import OpenRouterProvider
        return OpenRouterProvider(config.openrouter_api_key, model=model)
    elif name == "gemini":
        from polyx.ai.gemini import GeminiProvider
        return GeminiProvider(config.gemini_api_key, model=model)
    else:
        raise ConfigurationError(
            "Unknown AI provider: "
            f"{name}. Available: grok-subscription, codex-subscription, "
            "claude-subscription, cursor-subscription, antigravity-subscription, "
            "openai, claude, grok, openrouter, gemini"
        )


def _require_subscription_enabled(name: str, config: Config) -> None:
    if name in config.disabled_subscription_providers:
        raise ConfigurationError(
            f"{name} is disabled in PolyX configuration; enable it only after subscribing"
        )
