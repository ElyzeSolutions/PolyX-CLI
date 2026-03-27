"""Auto-selecting client that wraps API v2 and GraphQL behind a unified interface."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from polyx.exceptions import ConfigurationError, NotSupportedError

if TYPE_CHECKING:
    from polyx.config import Config
    from polyx.types import SearchResult, TrendingTopic, Tweet, User

log = logging.getLogger("polyx.client")


class AutoClient:
    """Unified X client that auto-selects API v2 or GraphQL based on config."""

    def __init__(self, config: Config, client_type: str = "auto") -> None:
        self._config = config
        self._client_type = client_type
        self._client: object | None = None

    async def __aenter__(self) -> AutoClient:
        self._client = await self._create_client()
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()

    async def _create_client(self) -> object:
        if self._client_type == "v2" or (self._client_type == "auto" and self._config.x_bearer_token):
            if not self._config.x_bearer_token:
                raise ConfigurationError(
                    "X API v2 requires X_BEARER_TOKEN. Set it in your environment or ~/.polyx/config.yml"
                )
            from polyx.client.api_v2 import XAPIv2Client
            client = XAPIv2Client(self._config)
            await client.__aenter__()
            log.debug("Using X API v2 client")
            return client

        if self._client_type == "graphql" or (self._client_type == "auto" and self._config.auth_token and self._config.ct0):
            if not self._config.auth_token or not self._config.ct0:
                raise ConfigurationError(
                    "GraphQL client requires AUTH_TOKEN and CT0. Set them in your environment."
                )
            from polyx.client.graphql import GraphQLClient
            client = GraphQLClient(self._config)
            await client.__aenter__()
            log.debug("Using GraphQL client")
            return client

        raise ConfigurationError(
            "No X client configured. Set one of:\n"
            "  - X_BEARER_TOKEN (for official API v2)\n"
            "  - AUTH_TOKEN + CT0 (for GraphQL fallback)\n"
            "See: polyx health"
        )

    async def search(self, query: str, limit: int = 20, sort: str = "relevancy",
                     since: str | None = None, pages: int = 1, min_likes: int = 0) -> SearchResult:
        return await self._client.search(query, limit=limit, sort=sort, since=since, pages=pages, min_likes=min_likes)

    async def search_full_archive(self, query: str, limit: int = 20, pages: int = 1) -> SearchResult:
        if hasattr(self._client, "search_full_archive"):
            return await self._client.search_full_archive(query, limit=limit, pages=pages)
        raise NotSupportedError("Full archive search requires the API v2 client (--client v2)")

    async def get_tweet(self, tweet_id: str) -> Tweet:
        return await self._client.get_tweet(tweet_id)

    async def get_user(self, username: str) -> User:
        return await self._client.get_user(username)

    async def get_user_timeline(self, user_id: str, count: int = 20, exclude_replies: bool = False) -> list[Tweet]:
        return await self._client.get_user_timeline(user_id, count=count, exclude_replies=exclude_replies)

    async def get_trends(self, woeid: int = 1) -> list[TrendingTopic]:
        return await self._client.get_trends(woeid)

    async def close(self) -> None:
        if self._client and hasattr(self._client, "close"):
            await self._client.close()
            self._client = None
