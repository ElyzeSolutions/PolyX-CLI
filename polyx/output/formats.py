"""Output formatters — terminal, JSON, JSONL, CSV, Markdown."""

from __future__ import annotations

import csv
import io
import json
from datetime import UTC, datetime
from typing import Any, Protocol

from polyx.types import (
    NewsSearchResult,
    NewsStory,
    SearchResult,
    SentimentResult,
    TrendingTopic,
    Tweet,
    User,
)


def compact_number(n: int) -> str:
    """Format number compactly: 1000 -> 1K, 1500000 -> 1.5M."""
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


def time_ago(date_str: str) -> str:
    """Convert ISO date string to relative time (2h, 3d, etc.)."""
    if not date_str:
        return ""
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        now = datetime.now(UTC)
        diff = now - dt
        seconds = int(diff.total_seconds())
        if seconds < 60:
            return f"{seconds}s"
        if seconds < 3600:
            return f"{seconds // 60}m"
        if seconds < 86400:
            return f"{seconds // 3600}h"
        return f"{seconds // 86400}d"
    except (ValueError, TypeError):
        return ""


class Formatter(Protocol):
    def format_search(
        self, result: SearchResult, sentiment: SentimentResult | None = None
    ) -> str: ...
    def format_tweet(self, tweet: Tweet) -> str: ...
    def format_profile(self, user: User, tweets: list[Tweet]) -> str: ...
    def format_trends(self, topics: list[TrendingTopic]) -> str: ...
    def format_news(self, result: NewsSearchResult) -> str: ...


def _news_context(story: NewsStory) -> str:
    """Build a compact context line for human-readable news output."""
    parts: list[str] = []
    if story.contexts.tickers:
        parts.append("Tickers: " + ", ".join(story.contexts.tickers))
    if story.contexts.topics:
        parts.append("Topics: " + ", ".join(story.contexts.topics))
    if story.contexts.entities.organizations:
        parts.append("Organizations: " + ", ".join(story.contexts.entities.organizations))
    return " · ".join(parts)


def _empty_news_message(result: NewsSearchResult) -> str:
    details = "; ".join(
        error.detail or error.title for error in result.errors if error.detail or error.title
    )
    return f"No news stories found. X API: {details}" if details else "No news stories found."


class TerminalFormatter:
    """Human-readable terminal output with engagement badges."""

    def format_search(self, result: SearchResult, sentiment: SentimentResult | None = None) -> str:
        if not result.tweets:
            return "No results found."

        lines: list[str] = []
        for i, tweet in enumerate(result.tweets, 1):
            age = time_ago(tweet.created_at)
            metrics = []
            if tweet.metrics.likes:
                metrics.append(f"{compact_number(tweet.metrics.likes)} likes")
            if tweet.metrics.impressions:
                metrics.append(f"{compact_number(tweet.metrics.impressions)} views")
            if tweet.metrics.retweets:
                metrics.append(f"{compact_number(tweet.metrics.retweets)} RT")

            meta = ", ".join(metrics)
            if age:
                meta = f"{meta} · {age}" if meta else age

            header = f"{i}. @{tweet.username}"
            if meta:
                header += f" ({meta})"
            lines.append(header)

            text = tweet.text.replace("\n", "\n   ")
            lines.append(f"   {text}")
            if tweet.tweet_url:
                lines.append(f"   {tweet.tweet_url}")
            lines.append("")

        footer_parts = [f"Query: {result.query}", f"{len(result.tweets)} tweets"]
        if result.cost_usd > 0:
            footer_parts.append(f"~${result.cost_usd:.4f}")
        if result.cached:
            footer_parts.append("cached")
        lines.append(" | ".join(footer_parts))

        if sentiment:
            lines.append("")
            direction = "bullish" if sentiment.aggregate > 0 else "bearish" if sentiment.aggregate < 0 else "neutral"
            lines.append(f"Sentiment: {sentiment.aggregate:+.2f} ({direction})")
            lines.append(f"  Bullish: {sentiment.bullish_count}  Bearish: {sentiment.bearish_count}  Neutral: {sentiment.neutral_count}")
            if sentiment.engagement_weighted != sentiment.aggregate:
                lines.append(f"  Engagement-weighted: {sentiment.engagement_weighted:+.2f}")
            if sentiment.notable_accounts:
                lines.append(f"  Notable: {', '.join(sentiment.notable_accounts)}")

        return "\n".join(lines)

    def format_tweet(self, tweet: Tweet) -> str:
        age = time_ago(tweet.created_at)
        likes = compact_number(tweet.metrics.likes)
        views = compact_number(tweet.metrics.impressions)
        lines = [
            f"@{tweet.username} ({tweet.name})" + (f" · {age}" if age else ""),
            tweet.text,
            f"{likes} likes · {compact_number(tweet.metrics.retweets)} RT · {views} views",
        ]
        if tweet.tweet_url:
            lines.append(tweet.tweet_url)
        return "\n".join(lines)

    def format_profile(self, user: User, tweets: list[Tweet]) -> str:
        lines = [
            f"@{user.username} ({user.name})",
            f"  Followers: {compact_number(user.followers_count)} · Following: {compact_number(user.following_count)} · Tweets: {compact_number(user.tweet_count)}",
        ]
        if user.description:
            lines.append(f"  {user.description}")
        if user.location:
            lines.append(f"  Location: {user.location}")
        lines.append("")

        if tweets:
            lines.append(f"Recent tweets ({len(tweets)}):")
            result = SearchResult(tweets=tweets, query=f"@{user.username}")
            lines.append(self.format_search(result))
        return "\n".join(lines)

    def format_trends(self, topics: list[TrendingTopic]) -> str:
        if not topics:
            return "No trending topics found."
        lines: list[str] = []
        for i, topic in enumerate(topics, 1):
            vol = f" ({compact_number(topic.tweet_volume)} tweets)" if topic.tweet_volume else ""
            lines.append(f"{i:2d}. {topic.name}{vol}")
        return "\n".join(lines)

    def format_news(self, result: NewsSearchResult) -> str:
        if not result.stories:
            return _empty_news_message(result)

        lines: list[str] = []
        for index, story in enumerate(result.stories, 1):
            age = time_ago(story.updated_at)
            category = f" [{story.category}]" if story.category else ""
            age_label = f" · {age}" if age else ""
            lines.append(f"{index}. {story.name}{category}{age_label}")
            if story.hook:
                lines.append(f"   {story.hook}")
            if story.summary and story.summary != story.hook:
                lines.append(f"   {story.summary}")
            context = _news_context(story)
            if context:
                lines.append(f"   {context}")
            if story.cluster_posts:
                lines.append(
                    f"   {len(story.cluster_posts)} clustered posts · "
                    f"https://x.com/i/status/{story.cluster_posts[0].post_id}"
                )
            lines.append("")

        lines.append(
            f"Query: {result.query} | Domain: {result.domain or 'unscoped'} | "
            f"{len(result.stories)} stories | last {result.max_age_hours}h"
        )
        if result.cached:
            lines[-1] += " | cached"
        if result.errors:
            lines.append(f"X API returned {len(result.errors)} partial errors.")
        return "\n".join(lines)


class JsonFormatter:
    """Full JSON output with metadata envelope."""

    def format_search(self, result: SearchResult, sentiment: SentimentResult | None = None) -> str:
        data: dict[str, Any] = {
            "source": "polyx",
            "timestamp": datetime.now(UTC).isoformat(),
            "query": result.query,
            "total_results": result.total_results,
            "cached": result.cached,
            "estimated_cost": result.cost_usd,
            "client_type": result.client_type,
            "tweets": [t.to_dict() for t in result.tweets],
        }
        if sentiment:
            data["sentiment"] = sentiment.to_dict()
        return json.dumps(data, indent=2)

    def format_tweet(self, tweet: Tweet) -> str:
        return json.dumps(tweet.to_dict(), indent=2)

    def format_profile(self, user: User, tweets: list[Tweet]) -> str:
        return json.dumps(
            {
                "user": user.to_dict(),
                "recent_tweets": [t.to_dict() for t in tweets],
            },
            indent=2,
        )

    def format_trends(self, topics: list[TrendingTopic]) -> str:
        return json.dumps([t.to_dict() for t in topics], indent=2)

    def format_news(self, result: NewsSearchResult) -> str:
        data = {
            "source": "polyx",
            "timestamp": datetime.now(UTC).isoformat(),
            **result.to_dict(),
        }
        return json.dumps(data, indent=2)


class JsonlFormatter:
    """One JSON object per line — pipeable."""

    def format_search(self, result: SearchResult, sentiment: SentimentResult | None = None) -> str:
        lines = [json.dumps(t.to_dict(), separators=(",", ":")) for t in result.tweets]
        return "\n".join(lines)

    def format_tweet(self, tweet: Tweet) -> str:
        return json.dumps(tweet.to_dict(), separators=(",", ":"))

    def format_profile(self, user: User, tweets: list[Tweet]) -> str:
        lines = [json.dumps(user.to_dict(), separators=(",", ":"))]
        for t in tweets:
            lines.append(json.dumps(t.to_dict(), separators=(",", ":")))
        return "\n".join(lines)

    def format_trends(self, topics: list[TrendingTopic]) -> str:
        return "\n".join(json.dumps(t.to_dict(), separators=(",", ":")) for t in topics)

    def format_news(self, result: NewsSearchResult) -> str:
        metadata: dict[str, Any] = {
            "source": "polyx",
            "query": result.query,
            "domain": result.domain,
            "client_type": result.client_type,
            "max_age_hours": result.max_age_hours,
            "total_results": result.total_results,
            "cached": result.cached,
            "errors": [error.to_dict() for error in result.errors],
        }
        if not result.stories:
            return json.dumps({**metadata, "type": "news_result"}, separators=(",", ":"))
        return "\n".join(
            json.dumps(
                {**metadata, "type": "news_story", **story.to_dict()},
                separators=(",", ":"),
            )
            for story in result.stories
        )


class CsvFormatter:
    """Flat CSV output for spreadsheets."""

    HEADERS = [
        "id",
        "username",
        "name",
        "text",
        "likes",
        "retweets",
        "replies",
        "impressions",
        "created_at",
        "url",
    ]
    NEWS_HEADERS = [
        "source",
        "domain",
        "query",
        "id",
        "name",
        "category",
        "updated_at",
        "summary",
        "hook",
        "tickers",
        "topics",
    ]

    def _rows(self, tweets: list[Tweet]) -> str:
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(self.HEADERS)
        for t in tweets:
            writer.writerow(
                [
                    t.id,
                    t.username,
                    t.name,
                    t.text,
                    t.metrics.likes,
                    t.metrics.retweets,
                    t.metrics.replies,
                    t.metrics.impressions,
                    t.created_at,
                    t.tweet_url,
                ]
            )
        return output.getvalue().rstrip()

    def format_search(self, result: SearchResult, sentiment: SentimentResult | None = None) -> str:
        if not result.tweets:
            return "No results found."
        return self._rows(result.tweets)

    def format_tweet(self, tweet: Tweet) -> str:
        return self._rows([tweet])

    def format_profile(self, user: User, tweets: list[Tweet]) -> str:
        return self._rows(tweets)

    def format_trends(self, topics: list[TrendingTopic]) -> str:
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["name", "tweet_volume", "url"])
        for t in topics:
            writer.writerow([t.name, t.tweet_volume, t.url])
        return output.getvalue().rstrip()

    def format_news(self, result: NewsSearchResult) -> str:
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(self.NEWS_HEADERS)
        for story in result.stories:
            writer.writerow(
                [
                    "polyx",
                    result.domain,
                    result.query,
                    story.id,
                    story.name,
                    story.category,
                    story.updated_at,
                    story.summary,
                    story.hook,
                    ",".join(story.contexts.tickers),
                    ",".join(story.contexts.topics),
                ]
            )
        return output.getvalue().rstrip()


class MarkdownFormatter:
    """Markdown output for reports."""

    def format_search(self, result: SearchResult, sentiment: SentimentResult | None = None) -> str:
        if not result.tweets:
            return "No results found."

        lines = [f"# Search: {result.query}", ""]

        for i, tweet in enumerate(result.tweets, 1):
            age = time_ago(tweet.created_at)
            likes = compact_number(tweet.metrics.likes)
            views = compact_number(tweet.metrics.impressions)
            lines.append(f"### {i}. @{tweet.username}" + (f" · {age}" if age else ""))
            lines.append("")
            lines.append(f"> {tweet.text}")
            lines.append("")
            metrics = f"{likes} likes · {compact_number(tweet.metrics.retweets)} RT · {views} views"
            lines.append(f"*{metrics}*")
            if tweet.tweet_url:
                lines.append(f"[View tweet]({tweet.tweet_url})")
            lines.append("")

        lines.append("---")
        lines.append(f"*{len(result.tweets)} tweets | Query: {result.query}*")

        if sentiment:
            direction = "bullish" if sentiment.aggregate > 0 else "bearish" if sentiment.aggregate < 0 else "neutral"
            lines.append("")
            lines.append(f"## Sentiment: {sentiment.aggregate:+.2f} ({direction})")
            lines.append(f"- Bullish: {sentiment.bullish_count}")
            lines.append(f"- Bearish: {sentiment.bearish_count}")
            lines.append(f"- Neutral: {sentiment.neutral_count}")

        return "\n".join(lines)

    def format_tweet(self, tweet: Tweet) -> str:
        age = time_ago(tweet.created_at)
        lines = [
            f"## @{tweet.username} ({tweet.name})" + (f" · {age}" if age else ""),
            "",
            f"> {tweet.text}",
            "",
            f"*{compact_number(tweet.metrics.likes)} likes · {compact_number(tweet.metrics.retweets)} RT · {compact_number(tweet.metrics.impressions)} views*",
        ]
        if tweet.tweet_url:
            lines.append(f"[View tweet]({tweet.tweet_url})")
        return "\n".join(lines)

    def format_profile(self, user: User, tweets: list[Tweet]) -> str:
        lines = [
            f"# @{user.username} ({user.name})",
            "",
            f"- Followers: {compact_number(user.followers_count)}",
            f"- Following: {compact_number(user.following_count)}",
            f"- Tweets: {compact_number(user.tweet_count)}",
        ]
        if user.description:
            lines.append(f"\n> {user.description}")
        if user.location:
            lines.append(f"\nLocation: {user.location}")
        if tweets:
            lines.append("")
            result = SearchResult(tweets=tweets, query=f"@{user.username}")
            lines.append(self.format_search(result))
        return "\n".join(lines)

    def format_trends(self, topics: list[TrendingTopic]) -> str:
        if not topics:
            return "No trending topics found."
        lines = ["# Trending Topics", ""]
        for i, topic in enumerate(topics, 1):
            vol = f" ({compact_number(topic.tweet_volume)} tweets)" if topic.tweet_volume else ""
            lines.append(f"{i}. **{topic.name}**{vol}")
        return "\n".join(lines)

    def format_news(self, result: NewsSearchResult) -> str:
        if not result.stories:
            return _empty_news_message(result)

        lines = [f"# X News: {result.query}", ""]
        for index, story in enumerate(result.stories, 1):
            age = time_ago(story.updated_at)
            suffix = f" · {age}" if age else ""
            lines.extend([f"## {index}. {story.name}{suffix}", ""])
            if story.hook:
                lines.extend([f"> {story.hook}", ""])
            if story.summary and story.summary != story.hook:
                lines.extend([story.summary, ""])
            context = _news_context(story)
            if context:
                lines.extend([f"**Context:** {context}", ""])
            if story.cluster_posts:
                post_links = [
                    f"[Post {post.post_id}](https://x.com/i/status/{post.post_id})"
                    for post in story.cluster_posts
                ]
                lines.extend(["**Clustered posts:** " + " · ".join(post_links), ""])

        lines.extend(
            [
                "---",
                f"*{len(result.stories)} stories | Last {result.max_age_hours}h | "
                f"Domain: {result.domain or 'unscoped'} | Query: {result.query}*",
            ]
        )
        return "\n".join(lines)


_FORMATTERS: dict[str, type[Formatter]] = {
    "terminal": TerminalFormatter,
    "json": JsonFormatter,
    "jsonl": JsonlFormatter,
    "csv": CsvFormatter,
    "markdown": MarkdownFormatter,
}


def get_formatter(name: str) -> Formatter:
    """Get a formatter by name."""
    cls = _FORMATTERS.get(name, TerminalFormatter)
    return cls()
