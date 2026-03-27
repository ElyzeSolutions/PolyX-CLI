"""X client implementations — API v2 and GraphQL fallback."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from polyx.types import SearchResult, TrendingTopic, Tweet, User


@runtime_checkable
class ClientProtocol(Protocol):
    """Protocol that all X clients must implement."""

    async def search(
        self,
        query: str,
        limit: int = 20,
        sort: str = "relevancy",
        since: str | None = None,
        pages: int = 1,
        min_likes: int = 0,
    ) -> SearchResult: ...

    async def get_tweet(self, tweet_id: str) -> Tweet: ...

    async def get_user(self, username: str) -> User: ...

    async def get_user_timeline(
        self, user_id: str, count: int = 20, exclude_replies: bool = False
    ) -> list[Tweet]: ...

    async def get_trends(self, woeid: int = 1) -> list[TrendingTopic]: ...

    async def close(self) -> None: ...
