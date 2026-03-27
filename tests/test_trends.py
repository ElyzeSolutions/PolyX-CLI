"""Test trends."""

import pytest

from polyx.config import Config
from polyx.monitoring.trends import TrendsProvider
from polyx.types import TrendingTopic


@pytest.mark.asyncio
async def test_trends_provider_v2(monkeypatch):
    monkeypatch.setenv("X_BEARER_TOKEN", "test_bearer")
    config = Config.load()

    # Mock client
    class MockClient:
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def get_trends(self, woeid):
            return [TrendingTopic(name="#Bitcoin", tweet_volume=100000)]

    provider = TrendsProvider(config)
    # We mock the _api_trends method to avoid creating a real client
    async def mock_api_trends(woeid):
        return [TrendingTopic(name="#Bitcoin", tweet_volume=100000)]

    monkeypatch.setattr(provider, "_api_trends", mock_api_trends)

    trends = await provider.get_trends("us")

    assert len(trends) == 1
    assert trends[0].name == "#Bitcoin"


@pytest.mark.asyncio
async def test_trends_fallback(monkeypatch):
    config = Config.load()
    provider = TrendsProvider(config)

    # Mock search fallback
    async def mock_search_fallback():
        return [TrendingTopic(name="#Bitcoin", tweet_volume=100)]

    monkeypatch.setattr(provider, "_search_fallback", mock_search_fallback)
    trends = await provider.get_trends("us")

    assert len(trends) >= 1
    assert trends[0].name == "#Bitcoin"
