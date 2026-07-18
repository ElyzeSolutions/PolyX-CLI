"""Test X API v2 client."""

import re

import pytest
from aioresponses import aioresponses

from polyx.client.api_v2 import XAPIv2Client
from polyx.config import Config
from polyx.exceptions import PolyXError
from polyx.types import NewsSearchResult, SearchResult, User


@pytest.mark.asyncio
async def test_search_recent(monkeypatch):
    monkeypatch.setenv("X_BEARER_TOKEN", "test_token")
    config = Config.load()
    client = XAPIv2Client(config)

    mock_response = {
        "data": [
            {
                "id": "1",
                "text": "First tweet",
                "author_id": "100",
                "created_at": "2025-01-01T00:00:00Z",
                "public_metrics": {"like_count": 10, "retweet_count": 5}
            }
        ],
        "includes": {
            "users": [{"id": "100", "username": "user1", "name": "User One"}]
        },
        "meta": {"result_count": 1, "next_token": "next123"}
    }

    with aioresponses() as m:
        # Use regex to match URL with many query params
        m.get(
            re.compile(r"^https://api\.x\.com/2/tweets/search/recent(?:\?.*)?$"),
            payload=mock_response,
        )

        async with client:
            result = await client.search("bitcoin", limit=10)

        assert isinstance(result, SearchResult)
        assert len(result.tweets) == 1
        assert result.tweets[0].id == "1"
        assert result.tweets[0].username == "user1"


@pytest.mark.asyncio
async def test_get_user(monkeypatch):
    monkeypatch.setenv("X_BEARER_TOKEN", "test_token")
    config = Config.load()
    client = XAPIv2Client(config)

    mock_response = {
        "data": {
            "id": "100",
            "username": "user1",
            "name": "User One",
            "public_metrics": {"followers_count": 500, "following_count": 200, "tweet_count": 1000}
        }
    }

    with aioresponses() as m:
        m.get(
            re.compile(r"^https://api\.x\.com/2/users/by/username/user1(?:\?.*)?$"),
            payload=mock_response,
        )

        async with client:
            user = await client.get_user("user1")

        assert isinstance(user, User)
        assert user.id == "100"
        assert user.username == "user1"
        assert user.followers_count == 500


@pytest.mark.asyncio
async def test_get_trends(monkeypatch):
    monkeypatch.setenv("X_BEARER_TOKEN", "test_token")
    config = Config.load()
    client = XAPIv2Client(config)

    mock_response = {
        "data": [
            {"name": "#Bitcoin", "tweet_volume": 100000},
            {"name": "#AI", "tweet_volume": 50000}
        ]
    }

    with aioresponses() as m:
        m.get(
            re.compile(r"^https://api\.x\.com/2/trends/by/woeid/1(?:\?.*)?$"),
            payload=mock_response,
        )

        async with client:
            trends = await client.get_trends(1)

        assert len(trends) == 2
        assert trends[0].name == "#Bitcoin"
        assert trends[0].tweet_volume == 100000


@pytest.mark.asyncio
async def test_search_news_parses_structured_story_and_partial_errors(monkeypatch):
    monkeypatch.setenv("X_BEARER_TOKEN", "test_token")
    client = XAPIv2Client(Config.load())
    mock_response = {
        "data": [
            {
                "id": "1989418137272422538",
                "name": "Gold rises after central bank signal",
                "summary": "Gold advanced after a dovish policy signal.",
                "hook": "Gold moved sharply as rate expectations changed.",
                "category": "News",
                "updated_at": "2026-07-18T08:30:00Z",
                "contexts": {
                    "entities": {
                        "organizations": ["Federal Reserve"],
                        "people": ["Jerome Powell"],
                    },
                    "finance": {"tickers": ["GC=F", "XAUUSD"]},
                    "sports": {"teams": []},
                    "topics": ["Gold", "Interest Rates"],
                },
                "cluster_posts_results": [
                    {"post_id": "1989409257394245835"},
                    {"post_id": "1989410019562197162"},
                ],
                "keywords": ["gold", "rates"],
                "disclaimer": "Verify this evolving summary.",
            }
        ],
        "errors": [
            {
                "title": "Partial field unavailable",
                "type": "https://api.x.com/problems/partial",
                "detail": "One optional field could not be expanded.",
                "status": 200,
            }
        ],
        "meta": {"result_count": 1},
    }

    with aioresponses() as mocked:
        mocked.get(
            re.compile(r"^https://api\.x\.com/2/news/search(?:\?.*)?$"),
            payload=mock_response,
        )
        async with client:
            result = await client.search_news("gold", max_results=25, max_age_hours=12)

    assert isinstance(result, NewsSearchResult)
    assert result.query == "gold"
    assert result.total_results == 1
    assert result.max_age_hours == 12
    assert result.stories[0].id == "1989418137272422538"
    assert result.stories[0].contexts.tickers == ["GC=F", "XAUUSD"]
    assert result.stories[0].cluster_posts[0].post_id == "1989409257394245835"
    assert result.errors[0].title == "Partial field unavailable"

    request = next(iter(mocked.requests.values()))[0]
    assert request.kwargs["params"]["query"] == "gold"
    assert request.kwargs["params"]["max_results"] == 25
    assert request.kwargs["params"]["max_age_hours"] == 12
    assert "contexts" in request.kwargs["params"]["news.fields"]


@pytest.mark.asyncio
async def test_search_news_accepts_documented_legacy_response_fields(monkeypatch):
    monkeypatch.setenv("X_BEARER_TOKEN", "test_token")
    client = XAPIv2Client(Config.load())
    mock_response = {
        "data": [
            {
                "rest_id": "2244994945",
                "name": "Election update",
                "last_updated_at_ms": "2026-07-18T09:00:00Z",
                "contexts": None,
                "cluster_posts_results": "malformed",
            }
        ],
        "meta": {},
    }

    with aioresponses() as mocked:
        mocked.get(
            re.compile(r"^https://api\.x\.com/2/news/search(?:\?.*)?$"),
            payload=mock_response,
        )
        async with client:
            result = await client.search_news("election")

    assert result.total_results == 1
    assert result.stories[0].id == "2244994945"
    assert result.stories[0].updated_at == "2026-07-18T09:00:00Z"
    assert result.stories[0].cluster_posts == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("query", "max_results", "max_age_hours", "message"),
    [
        ("", 10, 168, "query"),
        ("gold", 0, 168, "max_results"),
        ("gold", 10, 721, "max_age_hours"),
    ],
)
async def test_search_news_validates_official_limits(
    monkeypatch,
    query,
    max_results,
    max_age_hours,
    message,
):
    monkeypatch.setenv("X_BEARER_TOKEN", "test_token")
    client = XAPIv2Client(Config.load())

    async with client:
        with pytest.raises(PolyXError, match=message):
            await client.search_news(
                query,
                max_results=max_results,
                max_age_hours=max_age_hours,
            )
