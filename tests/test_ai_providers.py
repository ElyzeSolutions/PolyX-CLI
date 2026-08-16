"""Test AI providers."""

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from polyx.ai.anthropic import AnthropicProvider
from polyx.ai.api_catalog import API_MODELS
from polyx.ai.gemini import GeminiProvider
from polyx.ai.grok import GrokProvider
from polyx.ai.grok_subscription import (
    GrokSubscriptionProvider,
    _assert_subscription_auth,
    _run_structured,
    _subscription_environment,
)
from polyx.ai.openai import OpenAIProvider
from polyx.ai.registry import get_provider
from polyx.ai.subscription_cli import (
    AntigravitySubscriptionProvider,
    ClaudeSubscriptionProvider,
    CodexSubscriptionProvider,
    CursorSubscriptionProvider,
    SubscriptionModel,
    _minimal_environment,
    _subscription_model,
    discover_subscription_providers,
)
from polyx.config import Config
from polyx.exceptions import ConfigurationError, PolyXError
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


@pytest.mark.asyncio
async def test_grok_subscription_uses_structured_results_without_api_key(sample_tweets):
    calls = []

    async def runner(model, prompt, schema, allow_web):
        calls.append((model, prompt, schema, allow_web))
        return {
            "items": [
                {
                    "id": "1",
                    "sentiment": "positive",
                    "score": 0.8,
                    "confidence": 0.9,
                    "label": "Bullish",
                },
                {
                    "id": "2",
                    "sentiment": "negative",
                    "score": -0.7,
                    "confidence": 0.85,
                    "label": "Bearish",
                },
            ]
        }

    provider = GrokSubscriptionProvider(runner=runner)
    scores = await provider.analyze_sentiment(sample_tweets[:2])

    assert [item.tweet_id for item in scores] == ["1", "2"]
    assert [item.sentiment for item in scores] == [Sentiment.POSITIVE, Sentiment.NEGATIVE]
    assert calls[0][0] == "grok-4.6"
    assert calls[0][2]["properties"]["items"]["maxItems"] == 2
    assert calls[0][3] is False


@pytest.mark.asyncio
async def test_grok_subscription_rejects_duplicate_or_missing_tweet_ids(sample_tweets):
    async def runner(model, prompt, schema, allow_web):
        del model, prompt, schema, allow_web
        return {
            "items": [
                {
                    "id": "1",
                    "sentiment": "neutral",
                    "score": 0,
                    "confidence": 0.5,
                    "label": "Neutral",
                },
                {
                    "id": "1",
                    "sentiment": "neutral",
                    "score": 0,
                    "confidence": 0.5,
                    "label": "Neutral",
                },
            ]
        }

    provider = GrokSubscriptionProvider(runner=runner)
    with pytest.raises(PolyXError, match="unknown or duplicate"):
        await provider.analyze_sentiment(sample_tweets[:2])


def test_grok_subscription_registry_does_not_require_xai_api_key(monkeypatch):
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    config = Config.load()

    provider = get_provider("grok-subscription", config)

    assert isinstance(provider, GrokSubscriptionProvider)


@pytest.mark.parametrize(
    ("name", "provider_type"),
    [
        ("codex-subscription", CodexSubscriptionProvider),
        ("claude-subscription", ClaudeSubscriptionProvider),
        ("cursor-subscription", CursorSubscriptionProvider),
        ("antigravity-subscription", AntigravitySubscriptionProvider),
    ],
)
def test_subscription_cli_registry_does_not_require_api_keys(
    name,
    provider_type,
    monkeypatch,
):
    for variable in (
        "ANTHROPIC_API_KEY",
        "CURSOR_API_KEY",
        "GOOGLE_API_KEY",
        "OPENAI_API_KEY",
    ):
        monkeypatch.delenv(variable, raising=False)

    provider = get_provider(name, Config.load())

    assert isinstance(provider, provider_type)


def test_paid_api_modes_remain_explicitly_selectable(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "openai-test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic-test")
    config = Config.load()

    assert isinstance(get_provider("openai", config), OpenAIProvider)
    assert isinstance(get_provider("claude", config), AnthropicProvider)


def test_openrouter_model_prefix_does_not_switch_paid_provider(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "openrouter-test")

    provider = get_provider(
        "openrouter", Config.load(), model="openai/gpt-5-nano"
    )

    assert provider.PROVIDER_NAME == "openrouter"
    assert provider._model == "openai/gpt-5-nano"


def test_disabled_subscription_does_not_disable_api_mode(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic-test")
    config = Config.load()
    config.disabled_subscription_providers = ("claude-subscription",)

    with pytest.raises(ConfigurationError, match="disabled"):
        get_provider("claude-subscription", config)
    assert isinstance(get_provider("claude", config), AnthropicProvider)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "provider_type",
    [
        CodexSubscriptionProvider,
        ClaudeSubscriptionProvider,
        CursorSubscriptionProvider,
        AntigravitySubscriptionProvider,
    ],
)
async def test_subscription_cli_sentiment_is_grounded_and_schema_bound(
    provider_type,
    sample_tweets,
):
    calls = []

    async def runner(model, prompt, schema, allow_web):
        calls.append((model, prompt, schema, allow_web))
        return {
            "items": [
                {
                    "id": "1",
                    "sentiment": "positive",
                    "score": 0.75,
                    "confidence": 0.8,
                    "label": "Constructive",
                }
            ]
        }

    provider = provider_type(runner=runner)
    scores = await provider.analyze_sentiment(sample_tweets[:1])

    assert scores[0].tweet_id == "1"
    assert scores[0].sentiment is Sentiment.POSITIVE
    assert calls[0][3] is False
    assert calls[0][2]["properties"]["items"]["maxItems"] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "provider",
    [CursorSubscriptionProvider(), AntigravitySubscriptionProvider()],
)
async def test_unfenceable_subscription_clis_withhold_analysis(provider, sample_tweets):
    with pytest.raises(ConfigurationError, match="withheld"):
        await provider.analyze_sentiment(sample_tweets[:1])


@pytest.mark.asyncio
async def test_unfenceable_subscription_clis_are_not_reported_ready(monkeypatch):
    models = [SubscriptionModel("safe", "Safe", True)]

    async def discovered():
        return models

    for name in (
        "_discover_grok_models",
        "_discover_codex_models",
        "_discover_claude_models",
        "_discover_cursor_models",
        "_discover_antigravity_models",
    ):
        monkeypatch.setattr(f"polyx.ai.subscription_cli.{name}", discovered)

    rows = await discover_subscription_providers()
    by_name = {row["provider"]: row for row in rows}

    assert by_name["cursor-subscription"]["ready"] is False
    assert by_name["antigravity-subscription"]["ready"] is False
    assert by_name["grok-subscription"]["ready"] is True


def test_paid_openai_catalog_prices_match_supported_model_contract():
    prices = {
        model.id: (model.input_usd_per_mtok, model.output_usd_per_mtok)
        for model in API_MODELS["openai"]
    }

    assert prices["gpt-5.6-luna"] == (0.2, 1.2)
    assert prices["gpt-5.6-terra"] == (2.0, 12.0)
    assert prices["gpt-5.6-sol"] == (5.0, 30.0)


@pytest.mark.asyncio
async def test_subscription_cli_research_enables_web_and_renders_sources(sample_tweets):
    calls = []

    async def runner(model, prompt, schema, allow_web):
        calls.append((model, prompt, schema, allow_web))
        return {
            "analysis": "The supplied discussion is constructive.",
            "sources": ["https://example.com/filing"],
        }

    provider = CodexSubscriptionProvider(runner=runner)
    result = await provider.analyze_topic(sample_tweets[:1], "Example Corp")

    assert calls[0][3] is True
    assert "read-only web search" in calls[0][1]
    assert "https://example.com/filing" in result


def test_subscription_cli_environment_drops_all_api_and_session_secrets(monkeypatch):
    monkeypatch.setenv("HOME", "/safe/home")
    monkeypatch.setenv("PATH", "/usr/bin")
    for variable in (
        "ANTHROPIC_API_KEY",
        "AUTH_TOKEN",
        "CT0",
        "CURSOR_API_KEY",
        "GOOGLE_API_KEY",
        "OPENAI_API_KEY",
        "XAI_API_KEY",
        "X_BEARER_TOKEN",
        "GENERIC_SECRET",
    ):
        monkeypatch.setenv(variable, "must-not-reach-child")

    environment = _minimal_environment()

    assert environment["HOME"] == "/safe/home"
    assert environment["PATH"] == "/usr/bin"
    assert not {
        "ANTHROPIC_API_KEY",
        "AUTH_TOKEN",
        "CT0",
        "CURSOR_API_KEY",
        "GOOGLE_API_KEY",
        "OPENAI_API_KEY",
        "XAI_API_KEY",
        "X_BEARER_TOKEN",
        "GENERIC_SECRET",
    } & environment.keys()


def test_subscription_model_catalog_rejects_terminal_control_sequences():
    with pytest.raises(PolyXError, match="model identifier"):
        _subscription_model("--dangerous", "Dangerous")
    with pytest.raises(PolyXError, match="model label"):
        _subscription_model("safe-model", "Safe\x1b[2J")


def test_grok_subscription_passes_only_minimal_operator_environment(monkeypatch):
    monkeypatch.setenv("XAI_API_KEY", "must-not-reach-cli")
    monkeypatch.setenv("GROK_API_KEY", "must-not-reach-cli")
    monkeypatch.setenv("X_BEARER_TOKEN", "must-not-reach-cli")
    monkeypatch.setenv("AUTH_TOKEN", "must-not-reach-cli")
    monkeypatch.setenv("CT0", "must-not-reach-cli")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "must-not-reach-cli")
    monkeypatch.setenv("GENERIC_SECRET", "must-not-reach-cli")
    monkeypatch.setenv("PATH", "/usr/bin")
    monkeypatch.setenv("HOME", "/safe/operator-home")

    environment = _subscription_environment()

    assert environment["PATH"] == "/usr/bin"
    assert environment["HOME"] == "/safe/operator-home"
    assert not {
        "XAI_API_KEY",
        "GROK_API_KEY",
        "X_BEARER_TOKEN",
        "AUTH_TOKEN",
        "CT0",
        "AWS_SECRET_ACCESS_KEY",
        "GENERIC_SECRET",
    } & environment.keys()


@pytest.mark.asyncio
async def test_grok_subscription_reaps_process_after_oversized_output(
    monkeypatch, tmp_path
):
    class FakeProcess:
        def __init__(self) -> None:
            self.pid = 12345
            self.stdout = asyncio.StreamReader()
            self.stderr = asyncio.StreamReader()
            self.stdout.feed_data(b"x" * 1_048_577)
            self.stdout.feed_eof()
            self.stderr.feed_eof()
            self.returncode = None
            self.killed = False
            self.waited = False
            self._stopped = asyncio.Event()

        def kill(self) -> None:
            self.killed = True
            self.returncode = -9
            self._stopped.set()

        async def wait(self) -> int:
            self.waited = True
            await self._stopped.wait()
            return self.returncode

    process = FakeProcess()
    operator_home = tmp_path / "operator-grok"
    operator_home.mkdir()
    operator_auth = operator_home / "auth.json"
    operator_auth.write_text('{"session":"original"}')
    operator_auth.chmod(0o600)
    monkeypatch.setenv("GROK_HOME", str(operator_home))
    isolated_auth_checks = []

    async def create_subprocess_exec(*args, **kwargs):
        del args
        isolated_auth = Path(kwargs["env"]["GROK_HOME"]) / "auth.json"
        isolated_auth_checks.append(
            (
                isolated_auth.is_symlink(),
                isolated_auth.read_text(),
                isolated_auth.stat().st_mode & 0o077,
            )
        )
        return process

    monkeypatch.setattr(
        "polyx.ai.grok_subscription.asyncio.create_subprocess_exec",
        create_subprocess_exec,
    )
    monkeypatch.setattr("polyx.ai.grok_subscription._grok_executable", lambda: "grok")
    monkeypatch.setattr(
        "polyx.ai.grok_subscription._assert_subscription_auth",
        lambda model: None,
    )
    monkeypatch.setattr(
        "polyx.ai.grok_subscription.os.killpg",
        lambda pid, sig: process.kill(),
    )

    with pytest.raises(PolyXError, match="exceeded the 1 MiB limit"):
        await _run_structured(
            "grok-4.6",
            "bounded prompt",
            {"type": "object", "properties": {}},
        )

    assert process.killed is True
    assert process.waited is True
    assert isolated_auth_checks == [(False, '{"session":"original"}', 0)]
    assert operator_auth.read_text() == '{"session":"original"}'


def test_grok_subscription_rejects_model_api_key_override(monkeypatch, tmp_path):
    grok_home = tmp_path / "grok"
    grok_home.mkdir()
    (grok_home / "config.toml").write_text(
        '[model."grok-4.6"]\napi_key = "must-not-be-used"\n'
    )
    monkeypatch.setenv("GROK_HOME", str(grok_home))

    with pytest.raises(ConfigurationError, match="api_key override"):
        _assert_subscription_auth("grok-4.6")


def test_grok_subscription_requires_owner_only_oauth_session(monkeypatch, tmp_path):
    grok_home = tmp_path / "grok"
    grok_home.mkdir()
    monkeypatch.setenv("GROK_HOME", str(grok_home))

    with pytest.raises(ConfigurationError, match="grok login"):
        _assert_subscription_auth("grok-4.6")

    auth_path = grok_home / "auth.json"
    auth_path.write_text(
        json.dumps(
            {
                "https://accounts.x.ai/sign-in": {
                    "auth_mode": "oidc",
                    "key": "session-token-is-never-returned",
                }
            }
        )
    )
    auth_path.chmod(0o600)

    _assert_subscription_auth("grok-4.6")


def test_grok_subscription_rejects_api_key_only_auth(monkeypatch, tmp_path):
    grok_home = tmp_path / "grok"
    grok_home.mkdir()
    auth_path = grok_home / "auth.json"
    auth_path.write_text(
        json.dumps(
            {
                "xai::api_key": {
                    "auth_mode": "api_key",
                    "key": "must-not-be-used",
                }
            }
        )
    )
    auth_path.chmod(0o600)
    monkeypatch.setenv("GROK_HOME", str(grok_home))

    with pytest.raises(ConfigurationError, match="not authenticated with a subscription"):
        _assert_subscription_auth("grok-4.6")
