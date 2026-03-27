"""Test core types and data models."""

from polyx.types import Sentiment, SentimentResult, SentimentScore, Tweet, TweetMetrics, User


def test_tweet_from_dict():
    data = {
        "id": "123",
        "text": "Hello world",
        "username": "user",
        "name": "User",
        "metrics": {"likes": 10, "retweets": 5}
    }
    tweet = Tweet.from_dict(data)
    assert tweet.id == "123"
    assert tweet.metrics.likes == 10
    assert tweet.metrics.retweets == 5
    assert tweet.metrics.replies == 0


def test_tweet_to_dict(sample_tweet):
    data = sample_tweet.to_dict()
    assert data["id"] == "1234567890"
    assert data["metrics"]["likes"] == 150
    assert "hashtags" in data


def test_user_serialization(sample_user):
    data = sample_user.to_dict()
    assert data["username"] == "cryptotrader"
    assert data["followers_count"] == 15000

    user2 = User.from_dict(data)
    assert user2.username == "cryptotrader"
    assert user2.followers_count == 15000


def test_tweet_metrics_total_engagement():
    metrics = TweetMetrics(likes=10, retweets=5, replies=2, quotes=3)
    assert metrics.total_engagement == 20


def test_search_result_serialization(sample_search_result):
    data = sample_search_result.to_dict()
    assert data["query"] == "bitcoin"
    assert len(data["tweets"]) == 5
    assert data["tweets"][0]["id"] == "1"


def test_sentiment_result_serialization():
    scores = [
        SentimentScore(sentiment=Sentiment.POSITIVE, score=0.8, confidence=0.9, label="Bullish"),
        SentimentScore(sentiment=Sentiment.NEGATIVE, score=-0.5, confidence=0.7, label="Bearish"),
    ]
    result = SentimentResult(
        per_tweet=scores,
        aggregate=0.15,
        bullish_count=1,
        bearish_count=1,
        neutral_count=0,
        engagement_weighted=0.2
    )
    data = result.to_dict()
    assert data["bullish_count"] == 1
    assert data["per_tweet"][0]["sentiment"] == "positive"
