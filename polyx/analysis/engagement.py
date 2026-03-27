"""Engagement scoring and quality filtering."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from polyx.types import Tweet


class EngagementScorer:
    """Score and filter tweets by engagement metrics."""

    @staticmethod
    def quality_filter(tweets: list[Tweet], min_likes: int = 10) -> list[Tweet]:
        """Filter tweets by minimum likes threshold."""
        return [t for t in tweets if t.metrics.likes >= min_likes]

    @staticmethod
    def sort_by_engagement(tweets: list[Tweet], metric: str = "likes", reverse: bool = True) -> list[Tweet]:
        """Sort tweets by engagement metric."""
        return sorted(tweets, key=lambda t: getattr(t.metrics, metric, 0), reverse=reverse)

    @staticmethod
    def top_tweets(tweets: list[Tweet], n: int = 10) -> list[Tweet]:
        """Get top N tweets by total engagement."""
        return sorted(tweets, key=lambda t: t.metrics.total_engagement, reverse=True)[:n]
