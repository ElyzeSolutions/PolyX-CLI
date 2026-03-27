"""Test report generation."""

from __future__ import annotations

import pytest

import polyx.ai.registry as registry
import polyx.client.auto as auto_module
from polyx.config import Config
from polyx.output.reports import ReportGenerator
from polyx.types import SearchResult, User


@pytest.mark.asyncio
async def test_generate_report_includes_core_sections(sample_tweets, monkeypatch, tmp_path):
    monkeypatch.setenv("POLYX_DATA_DIR", str(tmp_path))

    class FakeAutoClient:
        def __init__(self, config, client_type="auto"):
            self.config = config
            self.client_type = client_type

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def search(self, topic, limit=50, pages=3):
            return SearchResult(
                tweets=sample_tweets[:4],
                query=topic,
                total_results=4,
                client_type="graphql",
                pages_fetched=pages,
            )

        async def get_user(self, username):
            return User(id="u1", username=username, name=username)

        async def get_user_timeline(self, user_id, count=10):
            return [sample_tweets[0]]

    monkeypatch.setattr(auto_module, "AutoClient", FakeAutoClient)

    config = Config.load()
    generator = ReportGenerator(config, client_type="graphql")
    report = await generator.generate("bitcoin", pages=2, accounts=["reuters"])

    assert "# Intelligence Report: bitcoin" in report
    assert "## Summary" in report
    assert "## Top Tweets by Engagement" in report
    assert "## Sentiment Breakdown" in report
    assert "## Account Activity" in report
    assert "### @reuters" in report


@pytest.mark.asyncio
async def test_generate_report_can_save_with_ai_summary(sample_tweets, monkeypatch, tmp_path):
    monkeypatch.setenv("POLYX_DATA_DIR", str(tmp_path))

    class FakeAutoClient:
        def __init__(self, config, client_type="auto"):
            self.config = config
            self.client_type = client_type

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def search(self, topic, limit=50, pages=3):
            return SearchResult(
                tweets=sample_tweets[:2],
                query=topic,
                total_results=2,
                client_type="v2",
                pages_fetched=pages,
                cost_usd=0.01,
            )

    class FakeProvider:
        async def analyze_topic(self, tweets, topic):
            return f"AI summary for {topic}"

    monkeypatch.setattr(auto_module, "AutoClient", FakeAutoClient)
    monkeypatch.setattr(registry, "get_provider", lambda name, config, model=None: FakeProvider())

    config = Config.load()
    generator = ReportGenerator(config, client_type="v2")
    report = await generator.generate(
        "ethereum",
        sentiment=False,
        provider="gemini",
        model="gemini/test",
        save=True,
    )

    saved_reports = list(config.reports_dir.glob("report_ethereum_*.md"))
    assert saved_reports
    assert "## AI Analysis" in report
    assert "AI summary for ethereum" in report
    assert "Saved to" in report
