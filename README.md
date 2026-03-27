# PolyX

<div align="center">
  <img src="https://raw.githubusercontent.com/ElyzeSolutions/PolyX-CLI/main/docs/assets/polyx-readme.png" alt="PolyX terminal interface showing search, monitoring, trends, sentiment, and report generation" width="720" />

  <p><strong>X/Twitter intelligence from the terminal.</strong></p>
  <p>Search live conversations, monitor topics, score sentiment, inspect trends, and generate clean reports from one CLI.</p>
  <p>
    <code>search</code>
    <code>watch</code>
    <code>trends</code>
    <code>analyze</code>
    <code>report</code>
    <code>json</code>
    <code>markdown</code>
  </p>
</div>

PolyX is built for research, trading, monitoring, and agent workflows where signal matters more than browsing the web UI by hand.

## Why use it

- Search X quickly from the terminal with structured output.
- Prefer the official X API v2 when you have a bearer token.
- Fall back to a cookie-based GraphQL client when you need a non-API path.
- Layer in Grok, Gemini, or OpenRouter for richer topic analysis.
- Save reports, cache results, and keep an eye on API spend.

## Install

The PyPI distribution name is `polyx-cli`. The executable stays `polyx`.

```bash
pip install polyx-cli

# With AI providers and richer terminal output
pip install "polyx-cli[ai,rich]"
```

From source:

```bash
git clone https://github.com/ElyzeSolutions/PolyX-CLI.git
cd PolyX
pip install -e ".[ai,rich]"
```

## Authentication modes

PolyX supports two access paths:

1. Official X API v2 via `X_BEARER_TOKEN`
2. Cookie-based GraphQL fallback via `AUTH_TOKEN` and `CT0`

The GraphQL path is unofficial and can break when X changes internal endpoints. Use API v2 when you can.

## Configuration

Use environment variables directly or copy `.env.example` to a local `.env`.

| Variable | Purpose |
| --- | --- |
| `X_BEARER_TOKEN` | Official X API v2 bearer token |
| `AUTH_TOKEN` | GraphQL `auth_token` cookie |
| `CT0` | GraphQL CSRF cookie |
| `XAI_API_KEY` | xAI key for Grok |
| `OPENROUTER_API_KEY` | OpenRouter key |
| `GOOGLE_API_KEY` | Google AI key for Gemini |
| `POLYX_DATA_DIR` | Base directory for reports, cache, and cost tracking |
| `POLYX_CACHE_DIR` | Optional cache directory override |
| `POLYX_DAILY_BUDGET` | Daily API budget in USD |
| `POLYX_CACHE_TTL` | Cache TTL in seconds |

Supported aliases:

- `TWITTER_AUTH_TOKEN` and `TWITTER_CT0` for GraphQL cookies
- `GROK_API_KEY` for xAI
- `GEMINI_API_KEY` for Gemini

## Quick start

Check your setup:

```bash
polyx health
```

Search recent posts:

```bash
polyx search "bitcoin" --limit 25
polyx search "ai agents" --sentiment --json
polyx search "solana" --sort likes --pages 2
```

Watch a topic over time:

```bash
polyx watch "breaking news" --interval 1m
polyx watch "ethereum" --interval 5m --webhook https://hooks.example.com/polyx
```

Inspect trends:

```bash
polyx trends --location us
polyx trends --locations
```

Generate analysis and reports:

```bash
polyx analyze "stablecoins" --provider gemini
polyx report "AI agents" --pages 3 --sentiment --save
```

## Output formats

PolyX works well for both humans and automation:

- terminal output by default
- `--json` for machine-readable pipelines
- `--jsonl` for stream processing
- `--csv` for spreadsheets
- `--markdown` for reports and sharing

## Docker

```bash
docker build -t polyx .
docker run --rm -e X_BEARER_TOKEN=your_token polyx search "bitcoin"
```

## Development

```bash
uv sync --extra ai --extra rich --extra dev
uv run ruff check .
uv run pytest
uv build
```

GitHub Actions are included for CI and tag-based PyPI publishing.

## License

MIT
