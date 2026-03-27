"""Trends with API v2 + search-based hashtag fallback."""

from __future__ import annotations

import re
from collections import Counter
from typing import TYPE_CHECKING

from polyx.types import TrendingTopic

if TYPE_CHECKING:
    from polyx.config import Config

LOCATIONS: dict[str, int] = {
    "worldwide": 1,
    "us": 23424977,
    "uk": 23424975,
    "canada": 23424775,
    "australia": 23424748,
    "brazil": 23424768,
    "france": 23424819,
    "germany": 23424829,
    "india": 23424848,
    "indonesia": 23424846,
    "ireland": 23424803,
    "italy": 23424853,
    "japan": 23424856,
    "mexico": 23424900,
    "netherlands": 23424909,
    "new zealand": 23424916,
    "nigeria": 23424908,
    "philippines": 23424934,
    "poland": 23424923,
    "portugal": 23424925,
    "russia": 23424936,
    "saudi arabia": 23424938,
    "singapore": 23424948,
    "south africa": 23424942,
    "south korea": 23424868,
    "spain": 23424950,
    "sweden": 23424954,
    "switzerland": 23424957,
    "thailand": 23424960,
    "turkey": 23424969,
    "uae": 23424738,
    "new york": 2459115,
    "los angeles": 2442047,
    "chicago": 2379574,
    "london": 44418,
    "paris": 615702,
    "tokyo": 1118370,
    "toronto": 4118,
    "sydney": 1105779,
    "mumbai": 2295411,
    "berlin": 638242,
}

_HASHTAG_RE = re.compile(r"#([a-zA-Z0-9_]{2,20})")


class TrendsProvider:
    """Dual-mode trends: API v2 primary, search-based fallback."""

    def __init__(self, config: Config) -> None:
        self._config = config

    async def get_trends(self, location: str = "worldwide") -> list[TrendingTopic]:
        """Get trending topics for a location."""
        woeid = self._resolve_woeid(location)

        # Try API v2 first
        if self._config.x_bearer_token:
            try:
                return await self._api_trends(woeid)
            except Exception:
                pass  # Fallback to search

        # Search-based fallback
        return await self._search_fallback()

    def _resolve_woeid(self, location: str) -> int:
        """Resolve location name to WOEID."""
        try:
            return int(location)
        except ValueError:
            pass

        woeid = LOCATIONS.get(location.lower())
        if woeid is None:
            available = ", ".join(sorted(LOCATIONS.keys()))
            raise ValueError(f"Unknown location: {location}. Available: {available}")
        return woeid

    async def _api_trends(self, woeid: int) -> list[TrendingTopic]:
        """Fetch trends from X API v2."""
        from polyx.client.api_v2 import XAPIv2Client

        client = XAPIv2Client(self._config)
        async with client:
            return await client.get_trends(woeid)

    async def _search_fallback(self) -> list[TrendingTopic]:
        """Search-based hashtag frequency fallback."""
        from polyx.client.auto import AutoClient

        async with AutoClient(self._config) as client:
            # Search for recent popular content
            result = await client.search("lang:en -is:retweet", limit=100, pages=2)

        # Extract and count hashtags
        counter: Counter[str] = Counter()
        for tweet in result.tweets:
            for match in _HASHTAG_RE.findall(tweet.text):
                counter[match.lower()] += 1
            for tag in tweet.hashtags:
                counter[tag.lower()] += 1

        topics = [
            TrendingTopic(name=f"#{tag}", tweet_volume=count)
            for tag, count in counter.most_common(20)
            if count >= 2
        ]
        return topics
