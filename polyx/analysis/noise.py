"""Promotional noise filtering — spam detection for tweets."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from polyx.types import Tweet

# Promotional noise tokens (ported from Polybot's twitter_source.py)
PROMO_NOISE_TOKENS: tuple[str, ...] = (
    "join telegram", "free signal", "free signals", "accuracy rate",
    "tp1", "tp 1", "sl :", "sl:", "gold buy now", "gold sell now",
    "join free", "vip signal",
)


def is_promotional_noise(text: str, noise_tokens: tuple[str, ...] | None = None) -> bool:
    """Detect if a tweet is promotional spam.

    A tweet is flagged if:
    1. It has 2+ promotional token hits, OR
    2. It has a link + telegram reference + at least 1 token hit.
    """
    tokens = noise_tokens or PROMO_NOISE_TOKENS
    text_lower = text.lower()

    token_hits = sum(1 for token in tokens if token in text_lower)

    if token_hits >= 2:
        return True

    has_link = any(s in text_lower for s in ("http://", "https://", "t.co/"))
    has_telegram = "telegram" in text_lower or "t.me/" in text_lower

    return has_link and has_telegram and token_hits >= 1


def filter_noise(tweets: list[Tweet], noise_tokens: tuple[str, ...] | None = None) -> list[Tweet]:
    """Filter out promotional noise tweets."""
    return [t for t in tweets if not is_promotional_noise(t.text, noise_tokens)]
