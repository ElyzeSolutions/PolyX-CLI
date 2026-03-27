"""Test AI providers."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from polyx.ai.gemini import GeminiProvider
from polyx.ai.grok import GrokProvider
from polyx.ai.registry import get_provider
from polyx.config import Config
from polyx.types import Sentiment


@pytest.mark.asyncio
async def test_grok_sentiment(sample_tweets, monkeypatch):
    monkeypatch.setenv("XAI_API_KEY", "test_key")
    config = Config.load()
    provider = get_provider("grok", config)
    assert isinstance(provider, GrokProvider)

    mock_response_content = json.dumps([
        {"id": "1", "sentiment": "positive", "score": 0.9, "confidence": 0.95, "label": "Bullish"},
        {"id": "2", "sentiment": "negative", "score": -0.8, "confidence": 0.9, "label": "Bearish"}
    ])

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"choices": [{"message": {"content": mock_response_content}}]}

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp

        scores = await provider.analyze_sentiment(sample_tweets[:2])

        assert len(scores) == 2
        assert scores[0].sentiment == Sentiment.POSITIVE
        assert scores[1].sentiment == Sentiment.NEGATIVE


@pytest.mark.asyncio
async def test_gemini_sentiment(sample_tweets, monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "test_key")
    config = Config.load()
    provider = get_provider("gemini", config)
    assert isinstance(provider, GeminiProvider)

    mock_response_content = json.dumps([{"id": "1", "sentiment": "positive", "score": 0.7, "confidence": 0.8, "label": "Bullish"}])

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"choices": [{"message": {"content": mock_response_content}}]}

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp

        scores = await provider.analyze_sentiment(sample_tweets[:1])
        assert scores[0].sentiment == Sentiment.POSITIVE


def test_config_accepts_legacy_gemini_api_key(monkeypatch):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "legacy-test-key")

    config = Config.load()

    assert config.gemini_api_key == "legacy-test-key"
