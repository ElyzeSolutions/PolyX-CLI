"""Base AI provider with shared OpenAI-compatible request logic."""

from __future__ import annotations

import json

import httpx

from polyx.exceptions import ConfigurationError, PolyXError
from polyx.types import Sentiment, SentimentScore, Tweet


class BaseProvider:
    """Base class for OpenAI-compatible AI providers."""

    PROVIDER_NAME: str = "base"
    BASE_URL: str = ""
    ENV_KEY: str = ""
    DEFAULT_MODEL: str = ""

    def __init__(self, api_key: str, model: str | None = None) -> None:
        if not api_key:
            raise ConfigurationError(f"Set {self.ENV_KEY} for {self.PROVIDER_NAME} provider")
        self._api_key = api_key
        self._model = model or self.DEFAULT_MODEL

    async def _chat(self, messages: list[dict[str, str]], temperature: float = 0.3) -> str:
        """Send a chat completion request."""
        async with httpx.AsyncClient(timeout=60) as client:
            for attempt in range(3):
                resp = await client.post(
                    f"{self.BASE_URL}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self._model,
                        "messages": messages,
                        "temperature": temperature,
                    },
                )
                if resp.status_code == 429 and attempt < 2:
                    import asyncio
                    await asyncio.sleep(2 ** attempt)
                    continue
                if resp.status_code >= 400:
                    raise PolyXError(f"{self.PROVIDER_NAME} API error {resp.status_code}: {resp.text[:200]}")
                break

            data = resp.json()
            return data["choices"][0]["message"]["content"]

    async def analyze_sentiment(self, tweets: list[Tweet], batch_size: int = 20) -> list[SentimentScore]:
        """Analyze sentiment for tweets using AI."""
        results: list[SentimentScore] = []

        for i in range(0, len(tweets), batch_size):
            batch = tweets[i : i + batch_size]
            tweet_texts = "\n".join(
                f"[{t.id}] @{t.username}: {t.text[:200]}" for t in batch
            )

            response = await self._chat([
                {
                    "role": "system",
                    "content": (
                        "You are a sentiment analysis expert. Classify each tweet as positive, negative, neutral, or mixed. "
                        "Return a JSON array with objects: {\"id\": \"tweet_id\", \"sentiment\": \"positive|negative|neutral|mixed\", "
                        "\"score\": -1.0 to 1.0, \"confidence\": 0.0 to 1.0, \"label\": \"short description\"}. "
                        "Return ONLY the JSON array, no other text."
                    ),
                },
                {"role": "user", "content": f"Analyze these tweets:\n\n{tweet_texts}"},
            ])

            try:
                # Try to extract JSON from response
                text = response.strip()
                if text.startswith("```"):
                    text = text.split("```")[1]
                    if text.startswith("json"):
                        text = text[4:]
                parsed = json.loads(text)
                for item in parsed:
                    try:
                        results.append(SentimentScore(
                            sentiment=Sentiment(item.get("sentiment", "neutral")),
                            score=float(item.get("score", 0.0)),
                            confidence=float(item.get("confidence", 0.5)),
                            label=item.get("label", ""),
                            tweet_id=str(item.get("id", "")),
                        ))
                    except (ValueError, KeyError):
                        results.append(SentimentScore(
                            sentiment=Sentiment.NEUTRAL,
                            score=0.0,
                            confidence=0.1,
                            label="parse error",
                        ))
            except json.JSONDecodeError:
                # Fallback: return neutral for all tweets in batch
                for t in batch:
                    results.append(SentimentScore(
                        sentiment=Sentiment.NEUTRAL,
                        score=0.0,
                        confidence=0.1,
                        label="parse error",
                        tweet_id=t.id,
                    ))

        return results

    async def analyze_topic(self, tweets: list[Tweet], query: str, custom_prompt: str | None = None) -> str:
        """Free-form AI analysis of tweets about a topic."""
        tweet_texts = "\n".join(
            f"@{t.username} ({t.metrics.likes} likes): {t.text[:300]}"
            for t in tweets[:50]
        )

        prompt = custom_prompt or (
            f"Analyze these tweets about '{query}' and provide:\n"
            f"1. Key themes and insights\n"
            f"2. Overall sentiment summary\n"
            f"3. Notable signals or trends\n"
            f"4. Contrarian viewpoints if any\n"
            f"Be concise and data-driven."
        )

        return await self._chat([
            {"role": "system", "content": "You are an expert social media analyst. Provide clear, actionable insights."},
            {"role": "user", "content": f"{prompt}\n\nTweets:\n{tweet_texts}"},
        ])
