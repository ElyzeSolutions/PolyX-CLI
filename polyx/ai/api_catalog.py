"""Small, explicit catalog for paid API modes.

Prices are informational USD rates per million text tokens. They are kept
next to the supported model IDs so the operator sees the billing consequence
before choosing an API-key provider. Subscription CLI usage is deliberately
not represented here because it is billed against the signed-in product plan.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

PRICING_AS_OF = "2026-08-16"


@dataclass(frozen=True)
class ApiModel:
    id: str
    label: str
    input_usd_per_mtok: float | None
    output_usd_per_mtok: float | None
    default: bool = False


API_MODELS: dict[str, tuple[ApiModel, ...]] = {
    "openai": (
        ApiModel("gpt-5.6-luna", "GPT-5.6 Luna", 0.2, 1.2, True),
        ApiModel("gpt-5.6-terra", "GPT-5.6 Terra", 2.0, 12.0),
        ApiModel("gpt-5.6-sol", "GPT-5.6 Sol", 5.0, 30.0),
    ),
    "claude": (
        ApiModel("claude-haiku-4-5", "Claude Haiku 4.5", 1.0, 5.0),
        ApiModel("claude-sonnet-4-6", "Claude Sonnet 4.6", 3.0, 15.0, True),
        ApiModel("claude-opus-4-7", "Claude Opus 4.7", 5.0, 25.0),
    ),
    "grok": (
        ApiModel("grok-4.3", "Grok 4.3", 1.25, 2.5, True),
        ApiModel("grok-4.5", "Grok 4.5", 2.0, 6.0),
    ),
    "gemini": (
        ApiModel("gemini-3.5-flash-lite", "Gemini 3.5 Flash-Lite", 0.3, 2.5, True),
        ApiModel("gemini-3.6-flash", "Gemini 3.6 Flash", 1.5, 7.5),
    ),
    # OpenRouter prices are model/provider specific and can change independently.
    # Do not publish a stale numeric estimate for its routing aliases.
    "openrouter": (
        ApiModel("openai/gpt-5-nano", "OpenRouter: GPT-5 Nano", None, None, True),
        ApiModel("openrouter/free", "OpenRouter free router", 0.0, 0.0),
    ),
}


PRICING_URLS = {
    "openai": "https://developers.openai.com/api/docs/models",
    "claude": "https://platform.claude.com/docs/en/about-claude/pricing",
    "grok": "https://docs.x.ai/developers/pricing",
    "gemini": "https://ai.google.dev/gemini-api/docs/pricing",
    "openrouter": "https://openrouter.ai/models",
}


def api_model_rows(provider: str) -> list[dict[str, object]]:
    return [asdict(model) for model in API_MODELS[provider]]
