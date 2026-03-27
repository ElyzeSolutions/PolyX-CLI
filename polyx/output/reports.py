"""Comprehensive markdown intelligence report generation."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from polyx.analysis.engagement import EngagementScorer
from polyx.analysis.sentiment import KeywordSentimentAnalyzer
from polyx.output.formats import compact_number

if TYPE_CHECKING:
    from polyx.config import Config
    from polyx.types import Tweet


class ReportGenerator:
    """Generate comprehensive markdown intelligence reports."""

    def __init__(self, config: Config, client_type: str = "auto") -> None:
        self._config = config
        self._client_type = client_type

    async def generate(
        self,
        topic: str,
        pages: int = 3,
        sentiment: bool = True,
        provider: str | None = None,
        model: str | None = None,
        accounts: list[str] | None = None,
        save: bool = False,
    ) -> str:
        """Generate a full intelligence report."""
        from polyx.client.auto import AutoClient

        # Fetch tweets
        async with AutoClient(self._config, client_type=self._client_type) as client:
            result = await client.search(topic, limit=50, pages=pages)
            account_tweets: dict[str, list[Tweet]] = {}
            if accounts:
                for username in accounts:
                    try:
                        user = await client.get_user(username.lstrip("@"))
                        timeline = await client.get_user_timeline(user.id, count=10)
                        account_tweets[username] = timeline
                    except Exception:
                        account_tweets[username] = []

        tweets = result.tweets
        sections: list[str] = []

        # Header
        now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
        sections.append(f"# Intelligence Report: {topic}")
        sections.append(f"*Generated {now} by PolyX*\n")

        # Summary stats
        sections.append("## Summary")
        sections.append(f"- **Total tweets analyzed:** {len(tweets)}")
        sections.append(f"- **Pages fetched:** {result.pages_fetched}")
        sections.append(f"- **Client:** {result.client_type or self._client_type}")
        if result.cost_usd > 0:
            sections.append(f"- **Estimated cost:** ${result.cost_usd:.4f}")
        sections.append("")

        # Top tweets by engagement
        top = EngagementScorer.top_tweets(tweets, n=10)
        if top:
            sections.append("## Top Tweets by Engagement")
            for i, tweet in enumerate(top, 1):
                sections.append(
                    f"{i}. **@{tweet.username}** ({compact_number(tweet.metrics.likes)} likes, "
                    f"{compact_number(tweet.metrics.impressions)} views)"
                )
                sections.append(f"   > {tweet.text[:200]}")
                if tweet.tweet_url:
                    sections.append(f"   [View]({tweet.tweet_url})")
                sections.append("")

        # Sentiment breakdown
        if sentiment:
            analyzer = KeywordSentimentAnalyzer()
            sent = analyzer.analyze(tweets)
            direction = "bullish" if sent.aggregate > 0 else "bearish" if sent.aggregate < 0 else "neutral"
            sections.append("## Sentiment Breakdown")
            sections.append(f"- **Overall:** {sent.aggregate:+.2f} ({direction})")
            sections.append(f"- **Bullish tweets:** {sent.bullish_count}")
            sections.append(f"- **Bearish tweets:** {sent.bearish_count}")
            sections.append(f"- **Neutral tweets:** {sent.neutral_count}")
            if sent.engagement_weighted != sent.aggregate:
                sections.append(f"- **Engagement-weighted:** {sent.engagement_weighted:+.2f}")
            if sent.notable_accounts:
                sections.append(f"- **Notable accounts:** {', '.join(sent.notable_accounts)}")
            if sent.high_engagement_signals:
                sections.append("\n**High-Engagement Signals:**")
                for sig in sent.high_engagement_signals:
                    sections.append(f"- {sig}")
            sections.append("")

        # Account activity
        if account_tweets:
            sections.append("## Account Activity")
            for username, tweets_list in account_tweets.items():
                sections.append(f"### @{username.lstrip('@')}")
                if tweets_list:
                    for tweet in tweets_list[:5]:
                        sections.append(f"- {tweet.text[:150]}")
                else:
                    sections.append("- No recent tweets found")
                sections.append("")

        # AI synthesis
        if provider:
            try:
                from polyx.ai.registry import get_provider
                ai = get_provider(provider, self._config, model=model)
                synthesis = await ai.analyze_topic(tweets, topic)
                sections.append("## AI Analysis")
                sections.append(synthesis)
                sections.append("")
            except Exception as e:
                sections.append(f"## AI Analysis\n*Error: {e}*\n")

        report = "\n".join(sections)

        if save:
            filename = f"report_{topic.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
            path = self._config.reports_dir / filename
            path.write_text(report)
            report += f"\n\n*Saved to {path}*"

        return report
