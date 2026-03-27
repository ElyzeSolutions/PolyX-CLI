"""Test auto-client selection."""

from __future__ import annotations

import pytest

import polyx.client.api_v2 as api_v2
import polyx.client.graphql as graphql
from polyx.client.auto import AutoClient
from polyx.config import Config
from polyx.exceptions import ConfigurationError


@pytest.mark.asyncio
async def test_select_api_v2(monkeypatch):
    monkeypatch.setenv("X_BEARER_TOKEN", "test_bearer")

    class FakeV2Client:
        def __init__(self, config):
            self.config = config
            self.closed = False

        async def __aenter__(self):
            return self

        async def close(self):
            self.closed = True

    monkeypatch.setattr(api_v2, "XAPIv2Client", FakeV2Client)

    config = Config.load()
    async with AutoClient(config) as client:
        assert isinstance(client._client, FakeV2Client)


@pytest.mark.asyncio
async def test_select_graphql(monkeypatch):
    monkeypatch.delenv("X_BEARER_TOKEN", raising=False)
    monkeypatch.setenv("AUTH_TOKEN", "test_auth")
    monkeypatch.setenv("CT0", "test_ct0")

    class FakeGraphQLClient:
        def __init__(self, config):
            self.config = config
            self.closed = False

        async def __aenter__(self):
            return self

        async def close(self):
            self.closed = True

    monkeypatch.setattr(graphql, "GraphQLClient", FakeGraphQLClient)

    config = Config.load()
    async with AutoClient(config) as client:
        assert isinstance(client._client, FakeGraphQLClient)


@pytest.mark.asyncio
async def test_select_graphql_with_twitter_cookie_aliases(monkeypatch):
    monkeypatch.delenv("X_BEARER_TOKEN", raising=False)
    monkeypatch.delenv("AUTH_TOKEN", raising=False)
    monkeypatch.delenv("CT0", raising=False)
    monkeypatch.setenv("TWITTER_AUTH_TOKEN", "test_auth")
    monkeypatch.setenv("TWITTER_CT0", "test_ct0")

    class FakeGraphQLClient:
        def __init__(self, config):
            self.config = config
            self.closed = False

        async def __aenter__(self):
            return self

        async def close(self):
            self.closed = True

    monkeypatch.setattr(graphql, "GraphQLClient", FakeGraphQLClient)

    config = Config.load()
    async with AutoClient(config) as client:
        assert isinstance(client._client, FakeGraphQLClient)


@pytest.mark.asyncio
async def test_explicit_override(monkeypatch):
    monkeypatch.setenv("X_BEARER_TOKEN", "test_bearer")
    monkeypatch.setenv("AUTH_TOKEN", "test_auth")
    monkeypatch.setenv("CT0", "test_ct0")

    class FakeV2Client:
        def __init__(self, config):
            self.config = config

        async def __aenter__(self):
            return self

        async def close(self):
            return None

    class FakeGraphQLClient:
        def __init__(self, config):
            self.config = config

        async def __aenter__(self):
            return self

        async def close(self):
            return None

    monkeypatch.setattr(api_v2, "XAPIv2Client", FakeV2Client)
    monkeypatch.setattr(graphql, "GraphQLClient", FakeGraphQLClient)

    config = Config.load()

    async with AutoClient(config, client_type="v2") as client_v2:
        assert isinstance(client_v2._client, FakeV2Client)

    async with AutoClient(config, client_type="graphql") as client_gql:
        assert isinstance(client_gql._client, FakeGraphQLClient)


@pytest.mark.asyncio
async def test_missing_credentials_raise_configuration_error(monkeypatch):
    monkeypatch.delenv("X_BEARER_TOKEN", raising=False)
    monkeypatch.delenv("AUTH_TOKEN", raising=False)
    monkeypatch.delenv("CT0", raising=False)

    config = Config.load()
    client = AutoClient(config)

    with pytest.raises(ConfigurationError, match="No X client configured"):
        await client.__aenter__()
