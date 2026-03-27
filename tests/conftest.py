"""Shared test fixtures."""

from __future__ import annotations

import pytest

from polyx.types import SearchResult, TrendingTopic, Tweet, TweetMetrics, User


@pytest.fixture
def sample_tweet() -> Tweet:
    return Tweet(
        id="1234567890",
        text="Bitcoin is going to the moon! Bullish confirmed breaking news",
        author_id="111",
        username="cryptotrader",
        name="Crypto Trader",
        created_at="2025-01-15T10:30:00Z",
        conversation_id="1234567890",
        metrics=TweetMetrics(likes=150, retweets=30, replies=12, impressions=5200),
        urls=["https://example.com"],
        mentions=["elonmusk"],
        hashtags=["bitcoin", "crypto"],
        tweet_url="https://x.com/cryptotrader/status/1234567890",
    )


@pytest.fixture
def sample_tweets() -> list[Tweet]:
    return [
        Tweet(
            id="1", text="Bitcoin moon pump rally confirmed!",
            username="bull1", name="Bull One",
            metrics=TweetMetrics(likes=200, retweets=50, impressions=10000),
        ),
        Tweet(
            id="2", text="Market crash dump bearish collapse incoming",
            username="bear1", name="Bear One",
            metrics=TweetMetrics(likes=100, retweets=20, impressions=5000),
        ),
        Tweet(
            id="3", text="Just had a nice coffee this morning",
            username="neutral1", name="Neutral One",
            metrics=TweetMetrics(likes=5, retweets=1, impressions=200),
        ),
        Tweet(
            id="4", text="Breaking official sources say bitcoin surge",
            username="reuters", name="Reuters",
            metrics=TweetMetrics(likes=500, retweets=200, impressions=50000),
        ),
        Tweet(
            id="5", text="Join telegram free signals accuracy rate vip signal",
            username="spammer", name="Spammer",
            metrics=TweetMetrics(likes=0, retweets=0, impressions=10),
        ),
    ]


@pytest.fixture
def sample_user() -> User:
    return User(
        id="111",
        username="cryptotrader",
        name="Crypto Trader",
        followers_count=15000,
        following_count=500,
        tweet_count=3200,
        verified=False,
        description="Trading crypto since 2017",
        location="New York",
    )


@pytest.fixture
def sample_search_result(sample_tweets: list[Tweet]) -> SearchResult:
    return SearchResult(
        tweets=sample_tweets,
        query="bitcoin",
        total_results=5,
        client_type="v2",
        pages_fetched=1,
        cost_usd=0.025,
    )


@pytest.fixture
def sample_trending() -> list[TrendingTopic]:
    return [
        TrendingTopic(name="#Bitcoin", tweet_volume=125000),
        TrendingTopic(name="#AI", tweet_volume=95000),
        TrendingTopic(name="#BreakingNews", tweet_volume=80000),
    ]
