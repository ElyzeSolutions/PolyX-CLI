"""Test watch monitoring."""

import pytest
from aioresponses import aioresponses

from polyx.config import Config
from polyx.monitoring.watch import WatchSession
from polyx.output.formats import get_formatter
from polyx.types import SearchResult, Tweet, TweetMetrics


@pytest.mark.asyncio
async def test_watch_deduplication():
    # Mock client
    class MockClient:
        async def search(self, query, limit=20, sort="relevancy", since=None, pages=1, min_likes=0):
            # First poll: tweet 1, 2
            # Second poll: tweet 1, 2, 3
            if not hasattr(self, "_polls"):
                self._polls = 0
            self._polls += 1

            if self._polls == 1:
                return SearchResult(
                    tweets=[
                        Tweet(id="1", text="T1", username="u1", metrics=TweetMetrics()),
                        Tweet(id="2", text="T2", username="u2", metrics=TweetMetrics())
                    ],
                    query=query
                )
            else:
                return SearchResult(
                    tweets=[
                        Tweet(id="1", text="T1", username="u1", metrics=TweetMetrics()),
                        Tweet(id="2", text="T2", username="u2", metrics=TweetMetrics()),
                        Tweet(id="3", text="T3", username="u3", metrics=TweetMetrics())
                    ],
                    query=query
                )

    config = Config.load()
    fmt = get_formatter("terminal")
    session = WatchSession(client=MockClient(), config=config, formatter=fmt)

    # Run two polls
    results1, _ = await session.poll("bitcoin")
    assert len(results1) == 2
    assert results1[0].id == "1"

    results2, _ = await session.poll("bitcoin")
    # Only new tweet should be returned
    assert len(results2) == 1
    assert results2[0].id == "3"


@pytest.mark.asyncio
async def test_watch_webhook():
    # Mock client returning 1 tweet
    class MockClient:
        async def search(self, query, limit=20, sort="relevancy", since=None, pages=1, min_likes=0):
            return SearchResult(
                tweets=[Tweet(id="1", text="T1", username="u1", metrics=TweetMetrics())],
                query=query
            )

    config = Config.load()
    fmt = get_formatter("terminal")
    session = WatchSession(client=MockClient(), config=config, formatter=fmt)

    with aioresponses() as m:
        m.post("http://localhost/hook", status=200)

        await session.poll("bitcoin", webhook_url="http://localhost/hook")

        # Verify any POST was made to the URL
        assert any(str(url) == "http://localhost/hook" and method == "POST"
                   for method, url in m.requests)
