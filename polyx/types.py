"""Core data models — no external dependencies."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any


class Sentiment(Enum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"
    MIXED = "mixed"


@dataclass
class TweetMetrics:
    likes: int = 0
    retweets: int = 0
    replies: int = 0
    quotes: int = 0
    impressions: int = 0
    bookmarks: int = 0

    @property
    def total_engagement(self) -> int:
        return self.likes + self.retweets + self.replies + self.quotes

    def to_dict(self) -> dict[str, int]:
        return {
            "likes": self.likes,
            "retweets": self.retweets,
            "replies": self.replies,
            "quotes": self.quotes,
            "impressions": self.impressions,
            "bookmarks": self.bookmarks,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TweetMetrics:
        return cls(
            likes=data.get("likes", 0),
            retweets=data.get("retweets", 0),
            replies=data.get("replies", 0),
            quotes=data.get("quotes", 0),
            impressions=data.get("impressions", 0),
            bookmarks=data.get("bookmarks", 0),
        )


@dataclass
class Tweet:
    id: str
    text: str
    author_id: str = ""
    username: str = ""
    name: str = ""
    created_at: str = ""
    conversation_id: str = ""
    metrics: TweetMetrics = field(default_factory=TweetMetrics)
    urls: list[str] = field(default_factory=list)
    mentions: list[str] = field(default_factory=list)
    hashtags: list[str] = field(default_factory=list)
    tweet_url: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "text": self.text,
            "author_id": self.author_id,
            "username": self.username,
            "name": self.name,
            "created_at": self.created_at,
            "conversation_id": self.conversation_id,
            "metrics": self.metrics.to_dict(),
            "urls": self.urls,
            "mentions": self.mentions,
            "hashtags": self.hashtags,
            "tweet_url": self.tweet_url,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Tweet:
        metrics_data = data.get("metrics", {})
        metrics = TweetMetrics.from_dict(metrics_data) if isinstance(metrics_data, dict) else TweetMetrics()
        return cls(
            id=str(data.get("id", "")),
            text=data.get("text", ""),
            author_id=str(data.get("author_id", "")),
            username=data.get("username", ""),
            name=data.get("name", ""),
            created_at=data.get("created_at", ""),
            conversation_id=data.get("conversation_id", ""),
            metrics=metrics,
            urls=data.get("urls", []),
            mentions=data.get("mentions", []),
            hashtags=data.get("hashtags", []),
            tweet_url=data.get("tweet_url", ""),
        )


@dataclass
class User:
    id: str
    username: str
    name: str = ""
    followers_count: int = 0
    following_count: int = 0
    tweet_count: int = 0
    verified: bool = False
    description: str = ""
    location: str = ""
    created_at: str = ""
    profile_image_url: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "username": self.username,
            "name": self.name,
            "followers_count": self.followers_count,
            "following_count": self.following_count,
            "tweet_count": self.tweet_count,
            "verified": self.verified,
            "description": self.description,
            "location": self.location,
            "created_at": self.created_at,
            "profile_image_url": self.profile_image_url,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> User:
        return cls(
            id=str(data.get("id", "")),
            username=data.get("username", ""),
            name=data.get("name", ""),
            followers_count=data.get("followers_count", 0),
            following_count=data.get("following_count", 0),
            tweet_count=data.get("tweet_count", 0),
            verified=data.get("verified", False),
            description=data.get("description", ""),
            location=data.get("location", ""),
            created_at=data.get("created_at", ""),
            profile_image_url=data.get("profile_image_url", ""),
        )


@dataclass
class SearchResult:
    tweets: list[Tweet] = field(default_factory=list)
    query: str = ""
    total_results: int = 0
    next_token: str = ""
    cached: bool = False
    cost_usd: float = 0.0
    client_type: str = ""
    pages_fetched: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "tweets": [t.to_dict() for t in self.tweets],
            "query": self.query,
            "total_results": self.total_results,
            "next_token": self.next_token,
            "cached": self.cached,
            "cost_usd": self.cost_usd,
            "client_type": self.client_type,
            "pages_fetched": self.pages_fetched,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SearchResult:
        tweets = [Tweet.from_dict(t) for t in data.get("tweets", [])]
        return cls(
            tweets=tweets,
            query=data.get("query", ""),
            total_results=data.get("total_results", 0),
            next_token=data.get("next_token", ""),
            cached=data.get("cached", False),
            cost_usd=data.get("cost_usd", 0.0),
            client_type=data.get("client_type", ""),
            pages_fetched=data.get("pages_fetched", 0),
        )


def _string_list(value: Any) -> list[str]:
    """Return string items from an API value, ignoring malformed entries."""
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _string(value: Any) -> str:
    """Return a string API value without leaking ``None`` into output."""
    return value if isinstance(value, str) else ""


def _integer(value: Any, default: int) -> int:
    """Return an integer API value or a safe default."""
    return value if isinstance(value, int) else default


def _legacy_timestamp(value: Any) -> str:
    """Normalize a legacy epoch-millisecond timestamp to ISO 8601."""
    if isinstance(value, bool):
        return ""
    if isinstance(value, str):
        cleaned = value.strip()
        try:
            milliseconds = int(cleaned)
        except ValueError:
            return cleaned
    elif isinstance(value, (int, float)):
        milliseconds = value
    else:
        return ""
    try:
        timestamp = datetime.fromtimestamp(milliseconds / 1_000, UTC)
    except (OSError, OverflowError, ValueError):
        return ""
    return timestamp.isoformat().replace("+00:00", "Z")


@dataclass
class NewsPost:
    """A Post clustered by X under a news story."""

    post_id: str

    def to_dict(self) -> dict[str, str]:
        return {"post_id": self.post_id}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> NewsPost:
        return cls(post_id=_string(data.get("post_id")))


@dataclass
class NewsEntities:
    events: list[str] = field(default_factory=list)
    organizations: list[str] = field(default_factory=list)
    people: list[str] = field(default_factory=list)
    places: list[str] = field(default_factory=list)
    products: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, list[str]]:
        return {
            "events": self.events,
            "organizations": self.organizations,
            "people": self.people,
            "places": self.places,
            "products": self.products,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> NewsEntities:
        return cls(
            events=_string_list(data.get("events")),
            organizations=_string_list(data.get("organizations")),
            people=_string_list(data.get("people")),
            places=_string_list(data.get("places")),
            products=_string_list(data.get("products")),
        )


@dataclass
class NewsContexts:
    """Structured entities and market context attached to a news story."""

    entities: NewsEntities = field(default_factory=NewsEntities)
    tickers: list[str] = field(default_factory=list)
    teams: list[str] = field(default_factory=list)
    topics: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "entities": self.entities.to_dict(),
            "finance": {"tickers": self.tickers},
            "sports": {"teams": self.teams},
            "topics": self.topics,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> NewsContexts:
        entities = data.get("entities")
        finance = data.get("finance")
        sports = data.get("sports")
        return cls(
            entities=NewsEntities.from_dict(entities if isinstance(entities, dict) else {}),
            tickers=_string_list(finance.get("tickers")) if isinstance(finance, dict) else [],
            teams=_string_list(sports.get("teams")) if isinstance(sports, dict) else [],
            topics=_string_list(data.get("topics")),
        )


@dataclass
class NewsStory:
    """A breaking-news story clustered and summarized by X."""

    id: str
    name: str = ""
    summary: str = ""
    hook: str = ""
    category: str = ""
    updated_at: str = ""
    contexts: NewsContexts = field(default_factory=NewsContexts)
    cluster_posts: list[NewsPost] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    disclaimer: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "summary": self.summary,
            "hook": self.hook,
            "category": self.category,
            "updated_at": self.updated_at,
            "contexts": self.contexts.to_dict(),
            "cluster_posts_results": [post.to_dict() for post in self.cluster_posts],
            "keywords": self.keywords,
            "disclaimer": self.disclaimer,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> NewsStory:
        contexts = data.get("contexts")
        raw_posts = data.get("cluster_posts_results")
        posts = raw_posts if isinstance(raw_posts, list) else []
        return cls(
            id=_string(data.get("id")) or _string(data.get("rest_id")),
            name=_string(data.get("name")),
            summary=_string(data.get("summary")),
            hook=_string(data.get("hook")),
            category=_string(data.get("category")),
            updated_at=_string(data.get("updated_at"))
            or _legacy_timestamp(data.get("last_updated_at_ms")),
            contexts=NewsContexts.from_dict(contexts if isinstance(contexts, dict) else {}),
            cluster_posts=[NewsPost.from_dict(item) for item in posts if isinstance(item, dict)],
            keywords=_string_list(data.get("keywords")),
            disclaimer=_string(data.get("disclaimer")),
        )


@dataclass
class NewsAPIError:
    """RFC 7807 problem detail returned alongside an X News response."""

    title: str = ""
    type: str = ""
    detail: str = ""
    status: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "type": self.type,
            "detail": self.detail,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> NewsAPIError:
        status = data.get("status")
        return cls(
            title=_string(data.get("title")),
            type=_string(data.get("type")),
            detail=_string(data.get("detail")),
            status=status if isinstance(status, int) else None,
        )


@dataclass
class NewsSearchResult:
    stories: list[NewsStory] = field(default_factory=list)
    query: str = ""
    total_results: int = 0
    max_age_hours: int = 168
    errors: list[NewsAPIError] = field(default_factory=list)
    client_type: str = "api_v2"
    domain: str = ""
    cached: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "stories": [story.to_dict() for story in self.stories],
            "query": self.query,
            "total_results": self.total_results,
            "max_age_hours": self.max_age_hours,
            "errors": [error.to_dict() for error in self.errors],
            "client_type": self.client_type,
            "domain": self.domain,
            "cached": self.cached,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> NewsSearchResult:
        raw_stories = data.get("stories")
        raw_errors = data.get("errors")
        stories = raw_stories if isinstance(raw_stories, list) else []
        errors = raw_errors if isinstance(raw_errors, list) else []
        return cls(
            stories=[NewsStory.from_dict(item) for item in stories if isinstance(item, dict)],
            query=_string(data.get("query")),
            total_results=_integer(data.get("total_results"), 0),
            max_age_hours=_integer(data.get("max_age_hours"), 168),
            errors=[NewsAPIError.from_dict(item) for item in errors if isinstance(item, dict)],
            client_type=_string(data.get("client_type")) or "api_v2",
            domain=_string(data.get("domain")),
            cached=bool(data.get("cached", False)),
        )


@dataclass
class SentimentScore:
    sentiment: Sentiment = Sentiment.NEUTRAL
    score: float = 0.0
    confidence: float = 0.0
    label: str = ""
    tweet_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "sentiment": self.sentiment.value,
            "score": self.score,
            "confidence": self.confidence,
            "label": self.label,
            "tweet_id": self.tweet_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SentimentScore:
        return cls(
            sentiment=Sentiment(data.get("sentiment", "neutral")),
            score=data.get("score", 0.0),
            confidence=data.get("confidence", 0.0),
            label=data.get("label", ""),
            tweet_id=data.get("tweet_id", ""),
        )


@dataclass
class SentimentResult:
    per_tweet: list[SentimentScore] = field(default_factory=list)
    aggregate: float = 0.0
    bullish_count: int = 0
    bearish_count: int = 0
    neutral_count: int = 0
    engagement_weighted: float = 0.0
    notable_accounts: list[str] = field(default_factory=list)
    high_engagement_signals: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "per_tweet": [s.to_dict() for s in self.per_tweet],
            "aggregate": self.aggregate,
            "bullish_count": self.bullish_count,
            "bearish_count": self.bearish_count,
            "neutral_count": self.neutral_count,
            "engagement_weighted": self.engagement_weighted,
            "notable_accounts": self.notable_accounts,
            "high_engagement_signals": self.high_engagement_signals,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SentimentResult:
        per_tweet = [SentimentScore.from_dict(s) for s in data.get("per_tweet", [])]
        return cls(
            per_tweet=per_tweet,
            aggregate=data.get("aggregate", 0.0),
            bullish_count=data.get("bullish_count", 0),
            bearish_count=data.get("bearish_count", 0),
            neutral_count=data.get("neutral_count", 0),
            engagement_weighted=data.get("engagement_weighted", 0.0),
            notable_accounts=data.get("notable_accounts", []),
            high_engagement_signals=data.get("high_engagement_signals", []),
        )


@dataclass
class TrendingTopic:
    name: str
    tweet_volume: int = 0
    url: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "tweet_volume": self.tweet_volume,
            "url": self.url,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TrendingTopic:
        return cls(
            name=data.get("name", ""),
            tweet_volume=data.get("tweet_volume", 0),
            url=data.get("url", ""),
        )


@dataclass
class CostEntry:
    timestamp: str = ""
    operation: str = ""
    endpoint: str = ""
    tweets_read: int = 0
    cost_usd: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "operation": self.operation,
            "endpoint": self.endpoint,
            "tweets_read": self.tweets_read,
            "cost_usd": self.cost_usd,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CostEntry:
        return cls(
            timestamp=data.get("timestamp", ""),
            operation=data.get("operation", ""),
            endpoint=data.get("endpoint", ""),
            tweets_read=data.get("tweets_read", 0),
            cost_usd=data.get("cost_usd", 0.0),
        )


@dataclass
class DailyAggregate:
    date: str = ""
    total_cost: float = 0.0
    total_tweets: int = 0
    operations: int = 0
    entries: list[CostEntry] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "date": self.date,
            "total_cost": self.total_cost,
            "total_tweets": self.total_tweets,
            "operations": self.operations,
            "entries": [e.to_dict() for e in self.entries],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DailyAggregate:
        entries = [CostEntry.from_dict(e) for e in data.get("entries", [])]
        return cls(
            date=data.get("date", ""),
            total_cost=data.get("total_cost", 0.0),
            total_tweets=data.get("total_tweets", 0),
            operations=data.get("operations", 0),
            entries=entries,
        )
