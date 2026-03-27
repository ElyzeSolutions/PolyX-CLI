"""Official X API v2 client with bearer token authentication."""

from __future__ import annotations

import asyncio
import logging
import re
import time
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

import aiohttp

from polyx.exceptions import AuthenticationError, PolyXError, RateLimitError
from polyx.types import SearchResult, TrendingTopic, Tweet, TweetMetrics, User

if TYPE_CHECKING:
    from polyx.config import Config

logger = logging.getLogger(__name__)

BASE_URL = "https://api.x.com/2"

TWEET_FIELDS = "id,text,author_id,created_at,conversation_id,public_metrics,entities"
USER_FIELDS = (
    "id,username,name,public_metrics,verified,description,location,profile_image_url"
)
EXPANSIONS = "author_id"

_SINCE_PATTERN = re.compile(r"^(\d+)([hd])$")


def _parse_since(since: str) -> str:
    """Convert shorthand duration (e.g. '1h', '7d') to ISO 8601 timestamp.

    If the value is already ISO 8601 it is returned unchanged.
    Supported shorthands: 1h, 2h, 6h, 12h, 1d, 2d, 3d, 7d.
    """
    match = _SINCE_PATTERN.match(since.strip())
    if not match:
        # Assume raw ISO 8601
        return since

    amount = int(match.group(1))
    unit = match.group(2)

    delta = timedelta(hours=amount) if unit == "h" else timedelta(days=amount)

    dt = datetime.now(UTC) - delta
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


class XAPIv2Client:
    """Async client for the official X (Twitter) API v2.

    Uses bearer token authentication.  Implements automatic rate-limit
    handling with 350 ms minimum delay between requests and exponential
    backoff on HTTP 429 responses.
    """

    # ------------------------------------------------------------------
    # Rate-limit tunables
    # ------------------------------------------------------------------
    _MIN_DELAY: float = 0.35  # seconds between API calls
    _MAX_RETRIES: int = 3  # retries on 429

    def __init__(self, config: Config) -> None:
        self._bearer_token: str = config.x_bearer_token
        self._session: aiohttp.ClientSession | None = None
        self._last_request_time: float = 0.0

        # Rate-limit state parsed from response headers
        self._rate_limit_remaining: int | None = None
        self._rate_limit_reset: float | None = None

    # ------------------------------------------------------------------
    # Async context manager
    # ------------------------------------------------------------------

    async def __aenter__(self) -> XAPIv2Client:
        self._session = aiohttp.ClientSession(
            headers={
                "Authorization": f"Bearer {self._bearer_token}",
                "Content-Type": "application/json",
            },
        )
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.close()

    # ------------------------------------------------------------------
    # Core HTTP helper
    # ------------------------------------------------------------------

    async def _request(
        self,
        method: str,
        url: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Execute an HTTP request against the X API v2.

        * Enforces a minimum 350 ms gap between consecutive calls.
        * Parses ``x-rate-limit-remaining`` and ``x-rate-limit-reset`` headers.
        * Retries with exponential backoff on HTTP 429 (up to 3 attempts).
        * Raises :class:`AuthenticationError` on HTTP 401.
        * Raises :class:`RateLimitError` after all retries are exhausted.
        """
        if self._session is None:
            raise PolyXError(
                "Client session is not initialised. "
                "Use 'async with XAPIv2Client(config) as client:' or call __aenter__."
            )

        for attempt in range(1, self._MAX_RETRIES + 1):
            # ---- throttle --------------------------------------------------
            now = time.monotonic()
            elapsed = now - self._last_request_time
            if elapsed < self._MIN_DELAY:
                await asyncio.sleep(self._MIN_DELAY - elapsed)
            self._last_request_time = time.monotonic()

            # ---- send request -----------------------------------------------
            async with self._session.request(method, url, params=params) as resp:
                # Parse rate-limit headers
                remaining = resp.headers.get("x-rate-limit-remaining")
                reset = resp.headers.get("x-rate-limit-reset")
                if remaining is not None:
                    with suppress(ValueError):
                        self._rate_limit_remaining = int(remaining)
                if reset is not None:
                    with suppress(ValueError):
                        self._rate_limit_reset = float(reset)

                if resp.status == 200:
                    return await resp.json()  # type: ignore[no-any-return]

                if resp.status == 401:
                    raise AuthenticationError(
                        "X API v2 authentication failed (HTTP 401). "
                        "Check your bearer token."
                    )

                if resp.status == 429:
                    if attempt == self._MAX_RETRIES:
                        retry_after: float | None = None
                        if self._rate_limit_reset is not None:
                            retry_after = max(
                                0.0, self._rate_limit_reset - time.time()
                            )
                        raise RateLimitError(
                            f"Rate limit exceeded after {self._MAX_RETRIES} retries",
                            retry_after=retry_after,
                        )

                    # Exponential backoff: 1s, 2s, 4s ...
                    backoff = 2 ** (attempt - 1)
                    # If the server tells us when the window resets, honour it
                    if self._rate_limit_reset is not None:
                        wait_from_header = self._rate_limit_reset - time.time()
                        if wait_from_header > 0:
                            backoff = max(backoff, wait_from_header)

                    logger.warning(
                        "Rate limited (429). Retrying in %.1f s (attempt %d/%d).",
                        backoff,
                        attempt,
                        self._MAX_RETRIES,
                    )
                    await asyncio.sleep(backoff)
                    continue

                # Any other error
                body = await resp.text()
                raise PolyXError(
                    f"X API v2 request failed (HTTP {resp.status}): {body}"
                )

        # Should be unreachable, but satisfy the type checker
        raise PolyXError("Unexpected exit from retry loop")  # pragma: no cover

    # ------------------------------------------------------------------
    # Search endpoints
    # ------------------------------------------------------------------

    async def search(
        self,
        query: str,
        limit: int = 20,
        sort: str = "relevancy",
        since: str | None = None,
        pages: int = 1,
        min_likes: int = 0,
    ) -> SearchResult:
        """Search recent tweets (last 7 days) using the v2 search/recent endpoint."""
        params: dict[str, Any] = {
            "query": query,
            "max_results": min(limit, 100),
            "sort_order": sort,
            "tweet.fields": TWEET_FIELDS,
            "user.fields": USER_FIELDS,
            "expansions": EXPANSIONS,
        }

        if since is not None:
            params["start_time"] = _parse_since(since)

        all_tweets: list[Tweet] = []
        pages_fetched = 0

        for _ in range(pages):
            data = await self._request("GET", f"{BASE_URL}/tweets/search/recent", params=params)
            pages_fetched += 1

            includes = data.get("includes")
            for tweet_data in data.get("data", []):
                tweet = self._parse_tweet(tweet_data, includes=includes)
                if tweet.metrics.likes >= min_likes:
                    all_tweets.append(tweet)

            meta = data.get("meta", {})
            next_token = meta.get("next_token")
            if not next_token:
                break
            params["next_token"] = next_token

        return SearchResult(
            tweets=all_tweets,
            query=query,
            total_results=len(all_tweets),
            next_token=next_token if next_token else "",
            client_type="api_v2",
            pages_fetched=pages_fetched,
        )

    async def search_full_archive(
        self,
        query: str,
        limit: int = 20,
        pages: int = 1,
    ) -> SearchResult:
        """Full-archive search (academic / enterprise access required)."""
        params: dict[str, Any] = {
            "query": query,
            "max_results": min(limit, 100),
            "tweet.fields": TWEET_FIELDS,
            "user.fields": USER_FIELDS,
            "expansions": EXPANSIONS,
        }

        all_tweets: list[Tweet] = []
        pages_fetched = 0
        next_token: str | None = None

        for _ in range(pages):
            data = await self._request("GET", f"{BASE_URL}/tweets/search/all", params=params)
            pages_fetched += 1

            includes = data.get("includes")
            for tweet_data in data.get("data", []):
                all_tweets.append(self._parse_tweet(tweet_data, includes=includes))

            meta = data.get("meta", {})
            next_token = meta.get("next_token")
            if not next_token:
                break
            params["next_token"] = next_token

        return SearchResult(
            tweets=all_tweets,
            query=query,
            total_results=len(all_tweets),
            next_token=next_token if next_token else "",
            client_type="api_v2",
            pages_fetched=pages_fetched,
        )

    # ------------------------------------------------------------------
    # Single-resource endpoints
    # ------------------------------------------------------------------

    async def get_tweet(self, tweet_id: str) -> Tweet:
        """Fetch a single tweet by ID with full field expansion."""
        params: dict[str, Any] = {
            "tweet.fields": TWEET_FIELDS,
            "user.fields": USER_FIELDS,
            "expansions": EXPANSIONS,
        }
        data = await self._request("GET", f"{BASE_URL}/tweets/{tweet_id}", params=params)
        includes = data.get("includes")
        return self._parse_tweet(data["data"], includes=includes)

    async def get_user(self, username: str) -> User:
        """Fetch a user profile by username."""
        params: dict[str, Any] = {
            "user.fields": USER_FIELDS,
        }
        data = await self._request(
            "GET", f"{BASE_URL}/users/by/username/{username}", params=params
        )
        return self._parse_user(data["data"])

    async def get_user_timeline(
        self,
        user_id: str,
        count: int = 20,
        exclude_replies: bool = False,
    ) -> list[Tweet]:
        """Fetch recent tweets from a user's timeline."""
        params: dict[str, Any] = {
            "max_results": min(count, 100),
            "tweet.fields": TWEET_FIELDS,
            "user.fields": USER_FIELDS,
            "expansions": EXPANSIONS,
        }
        if exclude_replies:
            params["exclude"] = "replies"

        data = await self._request(
            "GET", f"{BASE_URL}/users/{user_id}/tweets", params=params
        )
        includes = data.get("includes")
        return [
            self._parse_tweet(t, includes=includes) for t in data.get("data", [])
        ]

    async def get_trends(self, woeid: int = 1) -> list[TrendingTopic]:
        """Fetch trending topics for a given WOEID (default: worldwide)."""
        data = await self._request("GET", f"{BASE_URL}/trends/by/woeid/{woeid}")
        trends: list[TrendingTopic] = []
        for item in data.get("data", []):
            trends.append(
                TrendingTopic(
                    name=item.get("name", item.get("trend_name", "")),
                    tweet_volume=item.get("tweet_volume", item.get("tweet_count", 0)),
                    url=item.get("url", ""),
                )
            )
        return trends

    # ------------------------------------------------------------------
    # Session management
    # ------------------------------------------------------------------

    async def close(self) -> None:
        """Close the underlying HTTP session."""
        if self._session is not None and not self._session.closed:
            await self._session.close()
            self._session = None

    # ------------------------------------------------------------------
    # Response parsing helpers
    # ------------------------------------------------------------------

    def _parse_tweet(
        self,
        data: dict[str, Any],
        includes: dict[str, Any] | None = None,
    ) -> Tweet:
        """Map an X API v2 tweet object to our internal :class:`Tweet` type."""
        tweet_id = str(data.get("id", ""))
        author_id = str(data.get("author_id", ""))

        # Resolve author info from includes.users
        username = ""
        name = ""
        if includes and "users" in includes:
            for user in includes["users"]:
                if str(user.get("id", "")) == author_id:
                    username = user.get("username", "")
                    name = user.get("name", "")
                    break

        # Parse public_metrics
        pm = data.get("public_metrics", {})
        metrics = TweetMetrics(
            likes=pm.get("like_count", 0),
            retweets=pm.get("retweet_count", 0),
            replies=pm.get("reply_count", 0),
            quotes=pm.get("quote_count", 0),
            impressions=pm.get("impression_count", 0),
            bookmarks=pm.get("bookmark_count", 0),
        )

        # Parse entities
        entities = data.get("entities", {})
        urls = [
            u.get("expanded_url", u.get("url", ""))
            for u in entities.get("urls", [])
            if u.get("expanded_url") or u.get("url")
        ]
        mentions = [m["username"] for m in entities.get("mentions", []) if "username" in m]
        hashtags = [h["tag"] for h in entities.get("hashtags", []) if "tag" in h]

        # Build tweet URL
        tweet_url = f"https://x.com/{username}/status/{tweet_id}" if username else ""

        return Tweet(
            id=tweet_id,
            text=data.get("text", ""),
            author_id=author_id,
            username=username,
            name=name,
            created_at=data.get("created_at", ""),
            conversation_id=str(data.get("conversation_id", "")),
            metrics=metrics,
            urls=urls,
            mentions=mentions,
            hashtags=hashtags,
            tweet_url=tweet_url,
        )

    def _parse_user(self, data: dict[str, Any]) -> User:
        """Map an X API v2 user object to our internal :class:`User` type."""
        pm = data.get("public_metrics", {})
        return User(
            id=str(data.get("id", "")),
            username=data.get("username", ""),
            name=data.get("name", ""),
            followers_count=pm.get("followers_count", 0),
            following_count=pm.get("following_count", 0),
            tweet_count=pm.get("tweet_count", 0),
            verified=data.get("verified", False),
            description=data.get("description", ""),
            location=data.get("location", ""),
            created_at=data.get("created_at", ""),
            profile_image_url=data.get("profile_image_url", ""),
        )
