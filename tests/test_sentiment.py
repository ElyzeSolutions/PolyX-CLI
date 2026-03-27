"""Test sentiment analysis."""

from polyx.analysis.sentiment import KeywordSentimentAnalyzer
from polyx.types import SentimentResult


def test_keyword_analysis(sample_tweets):
    analyzer = KeywordSentimentAnalyzer()
    result = analyzer.analyze(sample_tweets)

    assert isinstance(result, SentimentResult)
    # Tweet 1 is bullish ("moon pump rally")
    # Tweet 2 is bearish ("crash dump bearish")
    # Tweet 3 is neutral ("coffee")
    assert result.bullish_count >= 1
    assert result.bearish_count >= 1
    assert result.neutral_count >= 1


def test_engagement_weighting(sample_tweets):
    analyzer = KeywordSentimentAnalyzer()

    # Let's make the bullish tweet have massive engagement
    sample_tweets[0].metrics.likes = 1000000

    result = analyzer.analyze(sample_tweets)
    # Aggregate should be heavily influenced by the bullish tweet
    assert result.engagement_weighted > result.aggregate


def test_notable_accounts(sample_tweets):
    analyzer = KeywordSentimentAnalyzer()
    result = analyzer.analyze(sample_tweets)

    # @reuters should be detected as notable (in default list or high followers)
    assert "@reuters" in result.notable_accounts
