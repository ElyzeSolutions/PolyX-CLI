"""Test CLI commands."""

from click.testing import CliRunner

from polyx.cli import main as cli
from polyx.exceptions import ConfigurationError


def test_cli_help():
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "search" in result.output
    assert "watch" in result.output
    assert "trends" in result.output


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
