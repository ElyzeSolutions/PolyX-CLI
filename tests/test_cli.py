"""Test CLI commands."""

import json
import stat
import sys
import time
from types import SimpleNamespace

from click.testing import CliRunner

from polyx.cli import _news_cache_key
from polyx.cli import main as cli
from polyx.exceptions import ConfigurationError


def test_cli_help():
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "search" in result.output
    assert "watch" in result.output
    assert "trends" in result.output
    assert "news" in result.output


def test_cli_version():
    runner = CliRunner()
    result = runner.invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert "polyx, version" in result.output


def test_cli_search_no_auth(monkeypatch):
    # Ensure no auth env vars
    monkeypatch.delenv("X_BEARER_TOKEN", raising=False)
    monkeypatch.delenv("AUTH_TOKEN", raising=False)
    monkeypatch.delenv("CT0", raising=False)

    runner = CliRunner()
    result = runner.invoke(cli, ["search", "bitcoin"])
    assert result.exit_code != 0
    assert isinstance(result.exception, ConfigurationError)
    assert "No X client configured" in str(result.exception)


def test_cli_health():
    runner = CliRunner()
    result = runner.invoke(cli, ["health"])
    assert result.exit_code == 0
    assert "Status: OK" in result.output


def test_cli_health_accepts_standardized_aliases(monkeypatch):
    monkeypatch.delenv("AUTH_TOKEN", raising=False)
    monkeypatch.delenv("CT0", raising=False)
    monkeypatch.setenv("GOOGLE_API_KEY", "google-test-key")
    monkeypatch.setenv("TWITTER_AUTH_TOKEN", "twitter-auth-cookie")
    monkeypatch.setenv("TWITTER_CT0", "twitter-ct0-cookie")

    runner = CliRunner()
    result = runner.invoke(cli, ["health"])

    assert result.exit_code == 0
    assert "GraphQL: configured" in result.output
    assert "Gemini: configured" in result.output


def test_cli_costs():
    runner = CliRunner()
    # 'costs show' instead of 'costs today'
    result = runner.invoke(cli, ["costs", "show", "--period", "today"])
    assert result.exit_code == 0
    assert "Total cost:" in result.output


def test_cli_can_disable_subscription_without_disabling_api(monkeypatch, tmp_path):
    from polyx.config import Config

    monkeypatch.setenv("POLYX_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("POLYX_DISABLED_SUBSCRIPTION_PROVIDERS", raising=False)

    result = CliRunner().invoke(cli, ["ai", "disable", "claude-subscription"])

    assert result.exit_code == 0
    assert "separately configured API mode is unchanged" in result.output
    assert Config.load().disabled_subscription_providers == ("claude-subscription",)


def test_cli_setup_key_opens_only_selected_official_page(monkeypatch):
    opened = []
    monkeypatch.setattr("click.launch", opened.append)

    result = CliRunner().invoke(cli, ["ai", "setup-key", "claude"])

    assert result.exit_code == 0
    assert opened == ["https://console.anthropic.com/settings/keys"]
    assert "ANTHROPIC_API_KEY" in result.output


def test_cli_provider_catalog_displays_pricing_snapshot_date(monkeypatch):
    async def no_subscription_rows(disabled=()):
        del disabled
        return []

    monkeypatch.setattr(
        "polyx.ai.subscription_cli.discover_subscription_providers",
        no_subscription_rows,
    )

    result = CliRunner().invoke(cli, ["ai", "providers"])

    assert result.exit_code == 0
    assert "Pricing as of: 2026-08-16" in result.output
    assert "Explicit paid Anthropic API mode" in result.output


def test_cli_news_json(monkeypatch, tmp_path):
    from polyx.client.api_v2 import XAPIv2Client
    from polyx.types import NewsSearchResult, NewsStory

    captured = {}

    async def fake_search_news(self, query, max_results=10, max_age_hours=168):
        captured.update(
            query=query,
            max_results=max_results,
            max_age_hours=max_age_hours,
        )
        return NewsSearchResult(
            stories=[NewsStory(id="news-1", name="Gold headline")],
            query=query,
            total_results=1,
            max_age_hours=max_age_hours,
        )

    monkeypatch.setenv("X_BEARER_TOKEN", "test-token")
    monkeypatch.setenv("POLYX_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(XAPIv2Client, "search_news", fake_search_news)

    result = CliRunner().invoke(
        cli,
        [
            "--json",
            "news",
            "gold",
            "--domain",
            "gold",
            "--max-results",
            "25",
            "--max-age-hours",
            "12",
        ],
    )

    assert result.exit_code == 0
    assert captured == {"query": "gold", "max_results": 25, "max_age_hours": 12}
    output = json.loads(result.output)
    assert output["stories"][0]["name"] == "Gold headline"
    assert output["domain"] == "gold"


def test_cli_news_caches_and_tracks_cost(monkeypatch, tmp_path):
    from polyx.client.api_v2 import XAPIv2Client
    from polyx.config import Config
    from polyx.storage.costs import CostTracker
    from polyx.types import NewsSearchResult, NewsStory

    calls = 0

    async def fake_search_news(self, query, max_results=10, max_age_hours=168):
        nonlocal calls
        calls += 1
        return NewsSearchResult(
            stories=[NewsStory(id="news-1", name="Gold headline")],
            query=query,
            total_results=1,
            max_age_hours=max_age_hours,
        )

    monkeypatch.setenv("X_BEARER_TOKEN", "test-token")
    monkeypatch.setenv("POLYX_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(XAPIv2Client, "search_news", fake_search_news)
    runner = CliRunner()
    args = ["--json", "news", "gold", "--domain", "gold", "--max-age-hours", "12"]

    first = runner.invoke(cli, args)
    second = runner.invoke(cli, args)
    other_domain = runner.invoke(
        cli,
        ["--json", "news", "gold", "--domain", "polymarket", "--max-age-hours", "12"],
    )
    other_limit = runner.invoke(cli, [*args, "--max-results", "11"])
    other_age = runner.invoke(
        cli,
        ["--json", "news", "gold", "--domain", "gold", "--max-age-hours", "13"],
    )
    fresh = runner.invoke(cli, [*args, "--no-cache"])

    assert first.exit_code == 0
    assert second.exit_code == 0
    assert other_domain.exit_code == 0
    assert other_limit.exit_code == 0
    assert other_age.exit_code == 0
    assert fresh.exit_code == 0
    assert calls == 5
    assert json.loads(first.output)["cached"] is False
    assert json.loads(second.output)["cached"] is True
    assert CostTracker(Config.load()).get_daily().total_cost == 0.025


def test_cli_news_defaults_to_general_domain(monkeypatch):
    from polyx.client.api_v2 import XAPIv2Client
    from polyx.types import NewsSearchResult

    async def fake_search_news(self, query, max_results=10, max_age_hours=168):
        return NewsSearchResult(query=query)

    monkeypatch.setenv("X_BEARER_TOKEN", "test-token")
    monkeypatch.setattr(XAPIv2Client, "search_news", fake_search_news)

    result = CliRunner().invoke(cli, ["--json", "news", "gold", "--no-cache"])

    assert result.exit_code == 0
    assert json.loads(result.output)["domain"] == "general"


def test_cli_news_accepts_custom_general_purpose_domain(monkeypatch):
    from polyx.client.api_v2 import XAPIv2Client
    from polyx.types import NewsSearchResult

    async def fake_search_news(self, query, max_results=10, max_age_hours=168):
        return NewsSearchResult(query=query)

    monkeypatch.setenv("X_BEARER_TOKEN", "test-token")
    monkeypatch.setattr(XAPIv2Client, "search_news", fake_search_news)

    result = CliRunner().invoke(
        cli,
        ["--json", "news", "ai agents", "--domain", "Product_Research", "--no-cache"],
    )

    assert result.exit_code == 0
    assert json.loads(result.output)["domain"] == "product_research"


def test_cli_news_reports_rejected_bearer_without_traceback(monkeypatch):
    from polyx.client.api_v2 import XAPIv2Client
    from polyx.exceptions import AuthenticationError

    async def reject_search_news(self, query, max_results=10, max_age_hours=168):
        raise AuthenticationError("X rejected the bearer token")

    monkeypatch.setenv("X_BEARER_TOKEN", "invalid-token")
    monkeypatch.setattr(XAPIv2Client, "search_news", reject_search_news)

    result = CliRunner().invoke(cli, ["news", "gold", "--no-cache"])

    assert result.exit_code != 0
    assert "Error: X rejected the bearer token" in result.output
    assert "Traceback" not in result.output


def test_cli_news_blocks_uncached_call_when_budget_exhausted_but_allows_cache(
    monkeypatch,
    tmp_path,
):
    from polyx.client.api_v2 import XAPIv2Client
    from polyx.config import Config
    from polyx.storage.cache import FileCache
    from polyx.storage.costs import CostTracker
    from polyx.types import NewsSearchResult, NewsStory

    calls = 0

    async def fake_search_news(self, query, max_results=10, max_age_hours=168):
        nonlocal calls
        calls += 1
        return NewsSearchResult(query=query)

    monkeypatch.setenv("X_BEARER_TOKEN", "test-token")
    monkeypatch.setenv("POLYX_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("POLYX_DAILY_BUDGET", "0.005")
    monkeypatch.setattr(XAPIv2Client, "search_news", fake_search_news)
    config = Config.load()
    CostTracker(config).record("news", 1, "news/search")
    cached_result = NewsSearchResult(
        stories=[NewsStory(id="cached-1", name="Cached gold story")],
        query="gold",
        total_results=1,
        domain="gold",
    )
    FileCache(config).set(
        _news_cache_key("gold", "gold", 10, 168),
        cached_result.to_dict(),
    )
    runner = CliRunner()

    cached = runner.invoke(cli, ["--json", "news", "gold", "--domain", "gold"])
    uncached = runner.invoke(cli, ["news", "silver", "--domain", "gold"])

    assert cached.exit_code == 0
    assert json.loads(cached.output)["cached"] is True
    assert uncached.exit_code != 0
    assert "daily budget is exhausted" in uncached.output
    assert calls == 0


def test_cli_news_caps_live_result_limit_to_remaining_budget(monkeypatch, tmp_path):
    from polyx.client.api_v2 import XAPIv2Client
    from polyx.config import Config
    from polyx.storage.costs import CostTracker
    from polyx.types import NewsSearchResult, NewsStory

    captured_max_results: list[int] = []

    async def fake_search_news(self, query, max_results=10, max_age_hours=168):
        captured_max_results.append(max_results)
        stories = [NewsStory(id=f"news-{index}") for index in range(max_results)]
        return NewsSearchResult(
            stories=stories,
            query=query,
            total_results=len(stories),
            max_age_hours=max_age_hours,
        )

    monkeypatch.setenv("X_BEARER_TOKEN", "test-token")
    monkeypatch.setenv("POLYX_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("POLYX_DAILY_BUDGET", "0.012")
    monkeypatch.setattr(XAPIv2Client, "search_news", fake_search_news)

    result = CliRunner().invoke(
        cli,
        ["--json", "news", "gold", "--domain", "gold", "--max-results", "100"],
    )
    monkeypatch.setenv("POLYX_DAILY_BUDGET", "1")
    second = CliRunner().invoke(
        cli,
        ["--json", "news", "gold", "--domain", "gold", "--max-results", "100"],
    )

    assert result.exit_code == 0
    assert second.exit_code == 0
    assert captured_max_results == [2, 100]
    assert len(json.loads(result.output)["stories"]) == 2
    assert CostTracker(Config.load()).get_daily().total_cost == 0.51


def test_cli_news_records_paid_result_before_cache_failure(monkeypatch, tmp_path):
    from polyx.client.api_v2 import XAPIv2Client
    from polyx.config import Config
    from polyx.storage.cache import FileCache
    from polyx.storage.costs import CostTracker
    from polyx.types import NewsSearchResult, NewsStory

    async def fake_search_news(self, query, max_results=10, max_age_hours=168):
        return NewsSearchResult(
            stories=[NewsStory(id="news-1", name="Gold story")],
            query=query,
            total_results=1,
            max_age_hours=max_age_hours,
        )

    def fail_cache_write(self, key, value, ttl=None):
        raise OSError("cache unavailable")

    monkeypatch.setenv("X_BEARER_TOKEN", "test-token")
    monkeypatch.setenv("POLYX_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(XAPIv2Client, "search_news", fake_search_news)
    monkeypatch.setattr(FileCache, "set", fail_cache_write)

    result = CliRunner().invoke(
        cli,
        ["--json", "news", "gold", "--domain", "gold", "--no-cache"],
    )

    assert result.exit_code != 0
    assert CostTracker(Config.load()).get_daily().total_cost == 0.005


def test_auth_import_browser_saves_private_cookies_without_printing_them(
    monkeypatch,
    tmp_path,
):
    from polyx.config import Config

    auth_token = "private-auth-token"
    ct0 = "private-csrf-token"
    fake_rookiepy = SimpleNamespace(
        chrome=lambda domains: [
            {
                "domain": ".twitter.com",
                "expires": time.time() + 3600,
                "name": "auth_token",
                "value": "other-session-auth",
            },
            {
                "domain": ".x.com",
                "expires": time.time() + 3600,
                "name": "auth_token",
                "value": auth_token,
            },
            {
                "domain": ".x.com",
                "expires": time.time() + 3600,
                "name": "ct0",
                "value": ct0,
            },
            {
                "domain": ".twitter.com",
                "expires": time.time() - 1,
                "name": "ct0",
                "value": "expired-other-csrf",
            },
        ]
    )
    monkeypatch.setitem(sys.modules, "rookiepy", fake_rookiepy)
    monkeypatch.setenv("POLYX_DATA_DIR", str(tmp_path))

    result = CliRunner().invoke(cli, ["auth", "import-browser"])

    assert result.exit_code == 0
    assert auth_token not in result.output
    assert ct0 not in result.output
    config_file = tmp_path / "config.yml"
    assert stat.S_IMODE(config_file.stat().st_mode) == 0o600
    saved = Config.load()
    assert saved.auth_token == auth_token
    assert saved.ct0 == ct0


def test_auth_import_browser_refuses_invalid_existing_config(monkeypatch, tmp_path):
    fake_rookiepy = SimpleNamespace(
        chrome=lambda domains: [
            {"domain": ".x.com", "name": "auth_token", "value": "auth"},
            {"domain": ".x.com", "name": "ct0", "value": "csrf"},
        ]
    )
    monkeypatch.setitem(sys.modules, "rookiepy", fake_rookiepy)
    monkeypatch.setenv("POLYX_DATA_DIR", str(tmp_path))
    config_file = tmp_path / "config.yml"
    config_file.write_text("- not\n- a\n- mapping\n")

    result = CliRunner().invoke(cli, ["auth", "import-browser"])

    assert result.exit_code != 0
    assert "Invalid mapping" in result.output
    assert config_file.read_text() == "- not\n- a\n- mapping\n"
