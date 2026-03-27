"""Test X API v2 client."""

import re

import pytest
from aioresponses import aioresponses

from polyx.client.api_v2 import XAPIv2Client
from polyx.config import Config
from polyx.types import SearchResult, User


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
        m.get(re.compile(r"https://api.x.com/2/tweets/search/recent.*"), payload=mock_response)

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
        m.get(re.compile(r"https://api.x.com/2/users/by/username/user1.*"), payload=mock_response)

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
        m.get(re.compile(r"https://api.x.com/2/trends/by/woeid/1.*"), payload=mock_response)

        async with client:
            trends = await client.get_trends(1)

        assert len(trends) == 2
        assert trends[0].name == "#Bitcoin"
        assert trends[0].tweet_volume == 100000
