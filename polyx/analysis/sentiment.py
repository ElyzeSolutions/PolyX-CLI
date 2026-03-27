"""Keyword-based sentiment analysis — free, no API cost."""

from __future__ import annotations

import yaml

from polyx.types import Sentiment, SentimentResult, SentimentScore, Tweet

BULLISH_KEYWORDS = [
    "confirmed", "breaking", "happening", "imminent", "sources say",
    "official", "announced", "yes", "will", "moon", "pump", "bullish",
    "rally", "surge", "spike", "explosion", "wins", "won", "victory",
    "dominating", "leading", "ahead", "crushing", "destroying",
    "unstoppable", "guaranteed", "locked", "certain", "inevitable",
]

BEARISH_KEYWORDS = [
    "denied", "unlikely", "no", "won't", "false", "debunked",
    "rumor", "speculation", "fake", "calm", "stable", "peaceful",
    "deescalation", "talks", "diplomacy", "bearish", "dump", "crash",
    "loses", "lost", "defeated", "struggling", "failing", "collapse",
    "impossible", "never", "doubt", "uncertain", "risky",
]

NOTABLE_ACCOUNTS: set[str] = {
    # Crypto influencers
    "elonmusk", "vitalikbuterin", "caborex", "hsakatrades", "cobie",
    "zikiprism", "loomdart", "hsaka", "pentoshi", "thecryptodog",
    "cryptowizard", "notsofast", "trader1sz", "wsbmod", "unusual_whales",
    # News/official
    "reuters", "ap", "bbcbreaking", "wsj", "nytimes",
    "coindesk", "cointelegraph", "theblockcrypto", "decrypt_co",
    # Sports
    "espn", "bleacherreport", "sportscenter", "fifacom", "nba", "nfl",
    # Finance
    "bloombergmarkets", "yahoofinance", "cnbc", "marketwatch",
}

HIGH_FOLLOWER_THRESHOLD = 100_000


class KeywordSentimentAnalyzer:
    """Keyword-based sentiment analysis with engagement weighting."""

    def __init__(
        self,
        bullish_keywords: list[str] | None = None,
        bearish_keywords: list[str] | None = None,
        notable_accounts: set[str] | None = None,
        keywords_file: str = "",
    ) -> None:
        if keywords_file:
            custom = self._load_keywords(keywords_file)
            self.bullish = custom.get("bullish", BULLISH_KEYWORDS)
            self.bearish = custom.get("bearish", BEARISH_KEYWORDS)
        else:
            self.bullish = bullish_keywords or BULLISH_KEYWORDS
            self.bearish = bearish_keywords or BEARISH_KEYWORDS
        self.notable = notable_accounts or NOTABLE_ACCOUNTS

    @staticmethod
    def _load_keywords(path: str) -> dict[str, list[str]]:
        try:
            with open(path) as f:
                data = yaml.safe_load(f) or {}
            return {
                "bullish": data.get("bullish", []),
                "bearish": data.get("bearish", []),
            }
        except (OSError, yaml.YAMLError):
            return {}

    def analyze(self, tweets: list[Tweet]) -> SentimentResult:
        """Analyze sentiment across a list of tweets."""
        if not tweets:
            return SentimentResult()

        per_tweet: list[SentimentScore] = []
        bullish_count = 0
        bearish_count = 0
        neutral_count = 0
        notable_found: list[str] = []
        high_engagement_signals: list[str] = []

        weighted_sum = 0.0
        total_weight = 0.0

        for tweet in tweets:
            text_lower = tweet.text.lower()

            bull = sum(1 for w in self.bullish if w in text_lower)
            bear = sum(1 for w in self.bearish if w in text_lower)

            if bull > bear:
                sentiment = Sentiment.POSITIVE
                score = 1.0
                bullish_count += 1
            elif bear > bull:
                sentiment = Sentiment.NEGATIVE
                score = -1.0
                bearish_count += 1
            else:
                sentiment = Sentiment.NEUTRAL
                score = 0.0
                neutral_count += 1

            confidence = abs(bull - bear) / max(1, bull + bear)
            per_tweet.append(SentimentScore(
                sentiment=sentiment,
                score=score,
                confidence=confidence,
                label=sentiment.value,
                tweet_id=tweet.id,
            ))

            # Engagement weighting
            weight = max(1, tweet.metrics.total_engagement)
            weighted_sum += score * weight
            total_weight += weight

            # Notable accounts
            username = tweet.username.lower().lstrip("@")
            if username in self.notable and f"@{username}" not in notable_found:
                notable_found.append(f"@{username}")

            # High-engagement signals
            if tweet.metrics.total_engagement > 100 and any(
                w in text_lower for w in ["breaking", "confirmed", "official", "sources"]
            ):
                signal = tweet.text[:120] + "..." if len(tweet.text) > 120 else tweet.text
                high_engagement_signals.append(signal)

        total = bullish_count + bearish_count + neutral_count
        aggregate = (bullish_count - bearish_count) / total if total > 0 else 0.0
        engagement_weighted = weighted_sum / total_weight if total_weight > 0 else aggregate

        return SentimentResult(
            per_tweet=per_tweet,
            aggregate=aggregate,
            bullish_count=bullish_count,
            bearish_count=bearish_count,
            neutral_count=neutral_count,
            engagement_weighted=engagement_weighted,
            notable_accounts=notable_found[:10],
            high_engagement_signals=high_engagement_signals[:5],
        )
