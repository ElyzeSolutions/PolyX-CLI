"""GraphQL fallback X client -- cookie-based, no official API key required."""

from __future__ import annotations

import asyncio
import json
import logging
import random
import re
import time
import urllib.parse
from typing import TYPE_CHECKING, Any

import aiohttp

from polyx.exceptions import ConfigurationError, NotSupportedError, RateLimitError
from polyx.types import SearchResult, TrendingTopic, Tweet, TweetMetrics, User

if TYPE_CHECKING:
    from polyx.config import Config

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_TWITTER_GRAPHQL_BASE = "https://x.com/i/api/graphql"

_TWITTER_BEARER_TOKEN = (
    "AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs"
    "%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA"
)

_QUERY_ID_MAP = {
    "SearchTimeline": "9AW3D-T7t9Vkvfdmq2L-iQ",
    "UserByScreenName": "pLsOiyHJ1eFwPJlNmLp4Bg",
    "UserTweets": "LhtwFV9WwCOurTanx8NNfg",
}

_DEFAULT_SEARCH_QUERY_IDS = [
    _QUERY_ID_MAP["SearchTimeline"],
    "6AAys3t42mosm_yTI_QENg",
    "M1jEez78PEfVfbQLvlWMvQ",
    "5h0kNbk3ii97rmfY6CdgAA",
    "Tp1sewRU1AsZpBWhqCZicQ",
]

_QUERY_ID_CACHE_TTL_SEC = 24 * 60 * 60

_DISCOVERY_PAGES = (
    "https://x.com/?lang=en",
    "https://x.com/explore",
    "https://x.com/notifications",
    "https://x.com/settings/profile",
)

_BUNDLE_URL_REGEX = re.compile(
    r"https://abs\.twimg\.com/responsive-web/client-web/(?:-legacy/)?(?:[^\s\"']+\.js)"
)

_OPERATION_PATTERNS = (
    re.compile(
        r'e\.exports=\{queryId\s*:\s*["\']([^"\']+)["\']\s*,\s*operationName\s*:\s*["\']([^"\']+)["\']',
        re.S,
    ),
    re.compile(
        r'e\.exports=\{operationName\s*:\s*["\']([^"\']+)["\']\s*,\s*queryId\s*:\s*["\']([^"\']+)["\']',
        re.S,
    ),
    re.compile(
        r'operationName\s*[:=]\s*["\']([^"\']+)["\'](.{0,4000}?)queryId\s*[:=]\s*["\']([^"\']+)["\']',
        re.S,
    ),
    re.compile(
        r'queryId\s*[:=]\s*["\']([^"\']+)["\'](.{0,4000}?)operationName\s*[:=]\s*["\']([^"\']+)["\']',
        re.S,
    ),
)

_QUERY_ID_VALUE_REGEX = re.compile(r"^[a-zA-Z0-9_-]+$")

# Rate-limiting defaults (seconds).
_MIN_REQUEST_INTERVAL = 0.350
_JITTER_MAX = 0.120

# ---------------------------------------------------------------------------
# Search feature flags -- the full set required by the GraphQL endpoint.
# ---------------------------------------------------------------------------

_SEARCH_FEATURES: dict[str, Any] = {
    "rweb_video_screen_enabled": True,
    "profile_label_improvements_pcf_label_in_post_enabled": False,
    "responsive_web_profile_redirect_enabled": False,
    "rweb_tipjar_consumption_enabled": True,
    "verified_phone_label_enabled": False,
    "creator_subscriptions_tweet_preview_api_enabled": True,
    "responsive_web_graphql_timeline_navigation_enabled": True,
    "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
    "premium_content_api_read_enabled": False,
    "communities_web_enable_tweet_community_results_fetch": True,
    "c9s_tweet_anatomy_moderator_badge_enabled": True,
    "responsive_web_grok_analyze_button_fetch_trends_enabled": False,
    "responsive_web_grok_analyze_post_followups_enabled": False,
    "responsive_web_jetfuel_frame": False,
    "responsive_web_grok_share_attachment_enabled": False,
    "responsive_web_grok_annotations_enabled": False,
    "articles_preview_enabled": True,
    "responsive_web_edit_tweet_api_enabled": True,
    "graphql_is_translatable_rweb_tweet_is_translatable_enabled": True,
    "view_counts_everywhere_api_enabled": True,
    "longform_notetweets_consumption_enabled": True,
    "responsive_web_twitter_article_tweet_consumption_enabled": True,
    "tweet_awards_web_tipping_enabled": False,
    "content_disclosure_indicator_enabled": False,
    "content_disclosure_ai_generated_indicator_enabled": False,
    "responsive_web_grok_show_grok_translated_post": False,
    "responsive_web_grok_analysis_button_from_backend": False,
    "post_ctas_fetch_enabled": False,
    "freedom_of_speech_not_reach_fetch_enabled": True,
    "standardized_nudges_misinfo": True,
    "tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled": True,
    "longform_notetweets_rich_text_read_enabled": True,
    "longform_notetweets_inline_media_enabled": True,
    "responsive_web_grok_image_annotation_enabled": False,
    "responsive_web_grok_imagine_annotation_enabled": False,
    "responsive_web_grok_community_note_auto_translation_is_enabled": False,
    "responsive_web_enhance_cards_enabled": False,
}


class GraphQLClient:
    """Cookie-based GraphQL client for X (Twitter).

    Uses ``AUTH_TOKEN`` and ``CT0`` cookies to authenticate against the
    internal GraphQL API.  This is the **fallback** client when no official
    API bearer token is available.

    Implements :class:`~polyx.client.ClientProtocol`.
    """

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def __init__(self, config: Config) -> None:
        self._config = config
        self._auth_token: str = ""
        self._ct0: str = ""

        # aiohttp session -- created lazily in __aenter__
        self._session: aiohttp.ClientSession | None = None

        # Query-ID discovery cache
        self._cached_query_ids: list[str] = []
        self._query_id_cache_ts: float = 0.0

        # Rate limiting
        self._last_request_ts: float = 0.0

    async def __aenter__(self) -> GraphQLClient:
        self._read_cookies()
        connector = aiohttp.TCPConnector(
            limit=30,
            limit_per_host=20,
            ttl_dns_cache=300,
        )
        timeout = aiohttp.ClientTimeout(total=30)
        # Increase header limits to handle large X response headers (seen >8KB)
        self._session = aiohttp.ClientSession(
            connector=connector,
            cookie_jar=aiohttp.DummyCookieJar(),
            timeout=timeout,
            max_line_size=32768,
            max_field_size=32768,
        )
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        await self.close()

    async def close(self) -> None:
        """Close the underlying HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    # ------------------------------------------------------------------
    # Cookie / header helpers
    # ------------------------------------------------------------------

    def _read_cookies(self) -> None:
        """Read AUTH_TOKEN and CT0 from the config object."""
        self._auth_token = self._config.auth_token
        self._ct0 = self._config.ct0
        if not self._auth_token or not self._ct0:
            raise ConfigurationError(
                "GraphQL client requires both AUTH_TOKEN and CT0 cookies. "
                "Set them via environment variables or ~/.polyx/config.yml."
            )

    def _build_headers(self) -> dict[str, str]:
        """Construct request headers with bearer token, CSRF, and cookies."""
        return {
            "Authorization": f"Bearer {urllib.parse.unquote(_TWITTER_BEARER_TOKEN)}",
            "X-Csrf-Token": self._ct0,
            "X-Twitter-Auth-Type": "OAuth2Session",
            "X-Twitter-Active-User": "yes",
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Content-Type": "application/json",
            "Cookie": f"auth_token={self._auth_token}; ct0={self._ct0}",
            "Referer": "https://x.com/search",
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
        }

    # ------------------------------------------------------------------
    # Feature flags
    # ------------------------------------------------------------------

    @staticmethod
    def _search_features() -> dict[str, Any]:
        """Return the full set of GraphQL feature flags for search."""
        return dict(_SEARCH_FEATURES)

    # ------------------------------------------------------------------
    # Rate limiting
    # ------------------------------------------------------------------

    async def _rate_limit_wait(self) -> None:
        """Enforce minimum interval (350 ms + jitter) between requests."""
        now = time.monotonic()
        elapsed = now - self._last_request_ts
        required = _MIN_REQUEST_INTERVAL + random.uniform(0, _JITTER_MAX)
        if elapsed < required:
            await asyncio.sleep(required - elapsed)
        self._last_request_ts = time.monotonic()

    # ------------------------------------------------------------------
    # Query-ID discovery
    # ------------------------------------------------------------------

    async def _discover_query_ids(self) -> list[str]:
        """Scrape X bundle JS files to find ``SearchTimeline`` query IDs.

        Fetches the discovery pages, extracts bundle URLs, downloads
        the JS sources and parses them for operation name / query ID
        pairs.  Returns all query IDs whose operation name matches
        ``SearchTimeline``.
        """
        assert self._session is not None
        discovered: list[str] = []
        bundle_urls: set[str] = set()

        # 1. Fetch discovery pages to find bundle script URLs.
        for page_url in _DISCOVERY_PAGES:
            try:
                await self._rate_limit_wait()
                async with self._session.get(
                    page_url,
                    headers={"User-Agent": self._build_headers()["User-Agent"]},
                    allow_redirects=True,
                ) as resp:
                    if resp.status != 200:
                        logger.debug(
                            "Discovery page %s returned %d", page_url, resp.status
                        )
                        continue
                    html = await resp.text()
                    bundle_urls.update(_BUNDLE_URL_REGEX.findall(html))
            except Exception:
                logger.debug("Failed to fetch discovery page %s", page_url, exc_info=True)

        if not bundle_urls:
            logger.warning("No bundle URLs found on discovery pages")
            return discovered

        logger.debug("Found %d bundle URL(s)", len(bundle_urls))

        # 2. Download each bundle and search for SearchTimeline query IDs.
        for bundle_url in bundle_urls:
            try:
                await self._rate_limit_wait()
                async with self._session.get(
                    bundle_url,
                    headers={"User-Agent": self._build_headers()["User-Agent"]},
                ) as resp:
                    if resp.status != 200:
                        continue
                    js_text = await resp.text()
            except Exception:
                logger.debug("Failed to fetch bundle %s", bundle_url, exc_info=True)
                continue

            # Pattern 1: queryId first, operationName second
            for m in _OPERATION_PATTERNS[0].finditer(js_text):
                qid, op_name = m.group(1), m.group(2)
                if op_name == "SearchTimeline" and _QUERY_ID_VALUE_REGEX.match(qid):
                    discovered.append(qid)

            # Pattern 2: operationName first, queryId second
            for m in _OPERATION_PATTERNS[1].finditer(js_text):
                op_name, qid = m.group(1), m.group(2)
                if op_name == "SearchTimeline" and _QUERY_ID_VALUE_REGEX.match(qid):
                    discovered.append(qid)

            # Pattern 3: operationName ... queryId (with gap)
            for m in _OPERATION_PATTERNS[2].finditer(js_text):
                op_name, _, qid = m.group(1), m.group(2), m.group(3)
                if op_name == "SearchTimeline" and _QUERY_ID_VALUE_REGEX.match(qid):
                    discovered.append(qid)

            # Pattern 4: queryId ... operationName (with gap)
            for m in _OPERATION_PATTERNS[3].finditer(js_text):
                qid, _, op_name = m.group(1), m.group(2), m.group(3)
                if op_name == "SearchTimeline" and _QUERY_ID_VALUE_REGEX.match(qid):
                    discovered.append(qid)

        # Deduplicate while preserving order.
        seen: set[str] = set()
        unique: list[str] = []
        for qid in discovered:
            if qid not in seen:
                seen.add(qid)
                unique.append(qid)

        logger.info("Discovered %d SearchTimeline query ID(s)", len(unique))
        return unique

    async def _get_effective_query_ids(self) -> list[str]:
        """Return cached query IDs, refreshing if stale.

        Falls back to ``_DEFAULT_SEARCH_QUERY_IDS`` when discovery
        yields nothing.
        """
        now = time.monotonic()
        if (
            self._cached_query_ids
            and (now - self._query_id_cache_ts) < _QUERY_ID_CACHE_TTL_SEC
        ):
            return self._cached_query_ids

        try:
            ids = await self._discover_query_ids()
        except Exception:
            logger.warning("Query-ID discovery failed, using defaults", exc_info=True)
            ids = []

        if ids:
            self._cached_query_ids = ids
        else:
            logger.info("Using default query IDs")
            self._cached_query_ids = list(_DEFAULT_SEARCH_QUERY_IDS)

        self._query_id_cache_ts = now
        return self._cached_query_ids

    # ------------------------------------------------------------------
    # URL building
    # ------------------------------------------------------------------

    @staticmethod
    def _search_request_url(
        query_id: str,
        query: str,
        count: int,
        product: str = "Latest",
        cursor: str | None = None,
    ) -> str:
        """Build the full GraphQL search URL with query variables."""
        variables: dict[str, Any] = {
            "rawQuery": query,
            "count": count,
            "querySource": "typed_query",
            "product": product,
        }
        if cursor:
            variables["cursor"] = cursor

        params = {
            "variables": json.dumps(variables, separators=(",", ":")),
            "features": json.dumps(_SEARCH_FEATURES, separators=(",", ":")),
        }
        return (
            f"{_TWITTER_GRAPHQL_BASE}/{query_id}/SearchTimeline"
            f"?{urllib.parse.urlencode(params, quote_via=urllib.parse.quote)}"
        )

    # ------------------------------------------------------------------
    # Result unwrapping
    # ------------------------------------------------------------------

    @staticmethod
    def _unwrap_tweet_result(result: dict[str, Any]) -> dict[str, Any] | None:
        """Unwrap ``TweetWithVisibilityResults`` containers (up to 6 levels)."""
        for _ in range(6):
            type_name = result.get("__typename", "")
            if type_name == "Tweet":
                return result
            if type_name == "TweetWithVisibilityResults":
                inner = result.get("tweet")
                if isinstance(inner, dict):
                    result = inner
                    continue
                return None
            # TweetUnavailable or unknown wrapper
            if type_name == "TweetUnavailable":
                return None
            # Try generic inner "tweet" key as a last resort.
            inner = result.get("tweet")
            if isinstance(inner, dict):
                result = inner
                continue
            return result if result.get("rest_id") or result.get("legacy") else None
        return None

    @staticmethod
    def _extract_tweet_text(tweet_data: dict[str, Any]) -> str:
        """Extract the best available text from a tweet result.

        Prefers ``note_tweet`` (long-form) over ``legacy.full_text``.
        """
        # Long-form note_tweet
        note = tweet_data.get("note_tweet", {}).get("note_tweet_results", {}).get("result", {})
        note_text = note.get("text", "")
        if note_text:
            return note_text

        # Standard legacy full_text
        legacy = tweet_data.get("legacy", {})
        return legacy.get("full_text", "")

    def _map_tweet_result(self, raw: dict[str, Any]) -> Tweet | None:
        """Map a raw GraphQL tweet result to a :class:`~polyx.types.Tweet`."""
        unwrapped = self._unwrap_tweet_result(raw)
        if unwrapped is None:
            return None

        legacy = unwrapped.get("legacy", {})
        rest_id = unwrapped.get("rest_id", legacy.get("id_str", ""))

        text = self._extract_tweet_text(unwrapped)

        # Author info from core.user_results
        core = unwrapped.get("core", {})
        user_result = core.get("user_results", {}).get("result", {})
        user_legacy = user_result.get("legacy", {})
        author_id = user_result.get("rest_id", "")
        username = user_legacy.get("screen_name", "")
        name = user_legacy.get("name", "")

        # Metrics
        metrics = TweetMetrics(
            likes=legacy.get("favorite_count", 0),
            retweets=legacy.get("retweet_count", 0),
            replies=legacy.get("reply_count", 0),
            quotes=legacy.get("quote_count", 0),
            bookmarks=legacy.get("bookmark_count", 0),
            impressions=unwrapped.get("views", {}).get("count", 0)
            if isinstance(unwrapped.get("views", {}).get("count"), int)
            else _safe_int(unwrapped.get("views", {}).get("count", 0)),
        )

        # Entities
        entities = legacy.get("entities", {})
        urls = [u.get("expanded_url", u.get("url", "")) for u in entities.get("urls", [])]
        mentions = [m.get("screen_name", "") for m in entities.get("user_mentions", [])]
        hashtags = [h.get("text", "") for h in entities.get("hashtags", [])]

        created_at = legacy.get("created_at", "")
        conversation_id = legacy.get("conversation_id_str", "")
        tweet_url = f"https://x.com/{username}/status/{rest_id}" if username and rest_id else ""

        return Tweet(
            id=rest_id,
            text=text,
            author_id=author_id,
            username=username,
            name=name,
            created_at=created_at,
            conversation_id=conversation_id,
            metrics=metrics,
            urls=urls,
            mentions=mentions,
            hashtags=hashtags,
            tweet_url=tweet_url,
        )

    # ------------------------------------------------------------------
    # Result collection / pagination helpers
    # ------------------------------------------------------------------

    def _collect_tweet_results(self, obj: Any) -> list[dict[str, Any]]:
        """Recursively walk *obj* collecting all ``tweet_results`` dicts."""
        results: list[dict[str, Any]] = []
        if isinstance(obj, dict):
            if "tweet_results" in obj:
                inner = obj["tweet_results"].get("result")
                if isinstance(inner, dict):
                    results.append(inner)
            for value in obj.values():
                results.extend(self._collect_tweet_results(value))
        elif isinstance(obj, list):
            for item in obj:
                results.extend(self._collect_tweet_results(item))
        return results

    @staticmethod
    def _extract_bottom_cursor(data: dict[str, Any]) -> str | None:
        """Walk the response to find the bottom pagination cursor."""

        def _walk(obj: Any) -> str | None:
            if isinstance(obj, dict):
                # Direct cursor entry
                if obj.get("cursorType") == "Bottom":
                    return obj.get("value")
                entry_type = obj.get("entryType", "")
                if entry_type == "TimelineTimelineCursor" and obj.get("cursorType") == "Bottom":
                    return obj.get("value")
                for v in obj.values():
                    found = _walk(v)
                    if found:
                        return found
            elif isinstance(obj, list):
                for item in obj:
                    found = _walk(item)
                    if found:
                        return found
            return None

        return _walk(data)

    # ------------------------------------------------------------------
    # search() -- main entry point
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
        """Search tweets via GraphQL with query-ID rotation and retry.

        Parameters
        ----------
        query:
            The search query string.
        limit:
            Maximum number of tweets to return **per page** request.
        sort:
            ``"relevancy"`` (Top) or ``"recency"`` (Latest).
        since:
            Optional date filter (appended to the raw query).
        pages:
            Number of pagination pages to fetch.
        min_likes:
            Minimum like count filter (applied after fetching).

        Returns
        -------
        SearchResult
            A :class:`~polyx.types.SearchResult` containing the matched tweets.
        """
        assert self._session is not None, "Client not opened. Use `async with GraphQLClient(config) as client:`"

        product = "Top" if sort == "relevancy" else "Latest"

        # Build effective query
        effective_query = query
        if since:
            effective_query = f"{effective_query} since:{since}"

        query_ids = await self._get_effective_query_ids()
        all_tweets: list[Tweet] = []
        cursor: str | None = None
        pages_fetched = 0

        for _page_num in range(pages):
            # Try each query ID in turn; rotate on 404.
            page_data: dict[str, Any] | None = None
            last_error: Exception | None = None

            for idx, qid in enumerate(query_ids):
                payload = {
                    "variables": {
                        "rawQuery": effective_query,
                        "count": min(limit, 100),
                        "querySource": "typed_query",
                        "product": product,
                    },
                    "features": _SEARCH_FEATURES,
                    "queryId": qid,
                }
                if cursor:
                    payload["variables"]["cursor"] = cursor

                url = f"{_TWITTER_GRAPHQL_BASE}/{qid}/SearchTimeline"
                try:
                    await self._rate_limit_wait()
                    async with self._session.post(
                        url, headers=self._build_headers(), json=payload
                    ) as resp:
                        if resp.status == 200:
                            page_data = await resp.json()
                            # Promote the working ID to the front.
                            if idx > 0:
                                query_ids.insert(0, query_ids.pop(idx))
                            break

                        if resp.status == 404:
                            logger.debug(
                                "Query ID %s returned 404, rotating", qid
                            )
                            last_error = Exception(f"404 for query ID {qid}")
                            continue

                        if resp.status == 429:
                            retry_after = resp.headers.get("Retry-After")
                            raise RateLimitError(
                                "Rate limited (429) on GraphQL search",
                                retry_after=float(retry_after) if retry_after else None,
                            )

                        body = await resp.text()
                        logger.warning(
                            "GraphQL search returned %d: %s",
                            resp.status,
                            body[:300],
                        )
                        last_error = Exception(
                            f"GraphQL search HTTP {resp.status}"
                        )
                except RateLimitError:
                    raise
                except Exception as exc:
                    logger.debug("Request with query ID %s failed: %s", qid, exc)
                    last_error = exc

            if page_data is None:
                if last_error:
                    logger.error("All query IDs exhausted: %s", last_error)
                break

            pages_fetched += 1

            # Extract tweets from the response.
            raw_results = self._collect_tweet_results(page_data)
            for raw in raw_results:
                tweet = self._map_tweet_result(raw)
                if tweet is None:
                    continue
                if min_likes and tweet.metrics.likes < min_likes:
                    continue
                all_tweets.append(tweet)

            # Pagination cursor
            next_cursor = self._extract_bottom_cursor(page_data)
            if not next_cursor:
                break
            cursor = next_cursor

        return SearchResult(
            tweets=all_tweets,
            query=query,
            total_results=len(all_tweets),
            next_token=cursor or "",
            cached=False,
            cost_usd=0.0,
            client_type="graphql",
            pages_fetched=pages_fetched,
        )

    # ------------------------------------------------------------------
    # Unsupported protocol methods
    # ------------------------------------------------------------------

    async def get_tweet(self, tweet_id: str) -> Tweet:
        """Not supported -- use the API v2 client."""
        raise NotSupportedError(
            "get_tweet is not supported by the GraphQL fallback client. "
            "Use the API v2 client instead."
        )

    async def get_user(self, username: str) -> User:
        """Fetch user profile by screen name."""
        assert self._session is not None
        qid = _QUERY_ID_MAP["UserByScreenName"]
        variables = {
            "screen_name": username,
            "withSafetyModeUserFields": True,
        }
        params = {
            "variables": json.dumps(variables, separators=(",", ":")),
            "features": json.dumps(_SEARCH_FEATURES, separators=(",", ":")),
        }
        url = f"{_TWITTER_GRAPHQL_BASE}/{qid}/UserByScreenName?{urllib.parse.urlencode(params, quote_via=urllib.parse.quote)}"

        await self._rate_limit_wait()
        async with self._session.get(url, headers=self._build_headers()) as resp:
            if resp.status != 200:
                body = await resp.text()
                raise NotSupportedError(f"Failed to fetch user {username}: HTTP {resp.status} {body[:100]}")
            data = await resp.json()

        user_data = data.get("data", {}).get("user", {}).get("result", {})
        if not user_data:
            raise NotSupportedError(f"User {username} not found")

        legacy = user_data.get("legacy", {})
        return User(
            id=user_data.get("rest_id", ""),
            username=legacy.get("screen_name", username),
            name=legacy.get("name", ""),
            followers_count=legacy.get("followers_count", 0),
            verified=legacy.get("verified", False),
            description=legacy.get("description", ""),
            location=legacy.get("location", ""),
        )

    async def get_user_timeline(
        self, user_id: str, count: int = 20, exclude_replies: bool = False
    ) -> list[Tweet]:
        """Fetch recent tweets from a user's timeline."""
        assert self._session is not None
        qid = _QUERY_ID_MAP["UserTweets"]
        variables = {
            "userId": user_id,
            "count": count,
            "includePromotedContent": False,
            "withQuickPromoteEligibilityTweetFields": True,
            "withVoice": True,
            "withV2Timeline": True,
        }
        params = {
            "variables": json.dumps(variables, separators=(",", ":")),
            "features": json.dumps(_SEARCH_FEATURES, separators=(",", ":")),
        }
        url = f"{_TWITTER_GRAPHQL_BASE}/{qid}/UserTweets?{urllib.parse.urlencode(params, quote_via=urllib.parse.quote)}"

        await self._rate_limit_wait()
        async with self._session.get(url, headers=self._build_headers()) as resp:
            if resp.status != 200:
                body = await resp.text()
                raise NotSupportedError(f"Failed to fetch timeline for {user_id}: HTTP {resp.status} {body[:100]}")
            data = await resp.json()

        raw_results = self._collect_tweet_results(data)
        tweets: list[Tweet] = []
        for raw in raw_results:
            tweet = self._map_tweet_result(raw)
            if tweet:
                tweets.append(tweet)
        return tweets

    async def get_trends(self, woeid: int = 1) -> list[TrendingTopic]:
        """Not supported -- use the API v2 client."""
        raise NotSupportedError(
            "get_trends is not supported by the GraphQL fallback client. "
            "Use the API v2 client instead."
        )


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _safe_int(value: Any) -> int:
    """Coerce *value* to ``int``, returning ``0`` on failure."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
