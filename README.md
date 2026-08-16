# PolyX

<div align="center">
  <img src="https://raw.githubusercontent.com/ElyzeSolutions/PolyX-CLI/main/docs/assets/polyx-readme.png" alt="PolyX terminal interface showing search, monitoring, trends, sentiment, and report generation" width="720" />

  <p><strong>X/Twitter news and intelligence from the terminal.</strong></p>
  <p>Search breaking news and live conversations, monitor topics, score sentiment, inspect trends, and generate clean reports from one CLI.</p>
  <p>
    <code>search</code>
    <code>news</code>
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
- Search X's first-party breaking-news clusters with summaries, entity context, tickers, and source Post IDs.
- Prefer the official X API v2 when you have a bearer token.
- Fall back to a cookie-based GraphQL client when you need a non-API path.
- Layer in an explicitly selected subscription CLI or API-key provider for richer analysis.
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
PolyX loads the local `.env` automatically without overriding exported values.

| Variable | Purpose |
| --- | --- |
| `X_BEARER_TOKEN` | Official X API v2 bearer token |
| `AUTH_TOKEN` | GraphQL `auth_token` cookie |
| `CT0` | GraphQL CSRF cookie |
| `XAI_API_KEY` | xAI API key for the paid `grok` provider |
| `OPENAI_API_KEY` | OpenAI API key for the paid `openai` provider |
| `ANTHROPIC_API_KEY` | Anthropic API key for the paid `claude` provider |
| `OPENROUTER_API_KEY` | OpenRouter key |
| `GOOGLE_API_KEY` | Google AI key for Gemini |
| `POLYX_DISABLED_SUBSCRIPTION_PROVIDERS` | Comma-separated subscription CLI opt-outs |
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

Search breaking news through the official X API v2:

```bash
polyx news "US election" --max-results 25 --max-age-hours 12
polyx --json news "gold Federal Reserve" --domain gold --max-age-hours 6
polyx --jsonl news "crypto regulation" --domain polymarket | jq -c '{domain,id,name,summary}'
polyx --markdown news "gold real yields" --domain gold
```

`polyx news` requires `X_BEARER_TOKEN`; the cookie-based GraphQL client cannot
access X News. See [the News API guide](docs/news.md) for the typed response and
integration contract. News results use the normal PolyX cache and cost ledger;
use `--no-cache` only when a fresh paid request is necessary. Before a live
request, PolyX enforces `POLYX_DAILY_BUDGET` and reduces `--max-results` when
needed so its $0.005/story safety estimate cannot exceed the remaining budget.
Standalone use defaults to `--domain general`. Integrations such as Polybot pass
`--domain polymarket` or `--domain gold` explicitly to isolate their records.
The label is optional and extensible: another integration can pass its own
lowercase routing label without changing PolyX.

Import an existing X browser session for the GraphQL fallback without exposing
cookie values in the terminal:

```bash
uv tool install 'polyx-cli[browser]'
polyx auth import-browser --browser chrome
polyx --client graphql search "gold OR XAUUSD" --limit 20
```

The imported session is stored in `~/.polyx/config.yml` with mode `0600`.
Browser cookies grant account access and are less stable than the official API;
use them only as a local fallback.

X also publishes a hosted MCP server for agent tools. It complements PolyX's
typed, cached ingestion path rather than replacing it; see [X MCP and
PolyX](docs/mcp.md) for the recommended boundary.

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
polyx analyze "semiconductor capex" --provider grok-subscription
polyx ai providers
```

### AI credential modes

PolyX exposes subscription and API-key access as separate providers. It never
falls from a subscription into a paid API request automatically:

- `grok-subscription`: official [Grok Build CLI](https://docs.x.ai/build/overview)
- `codex-subscription`: official Codex CLI signed in through ChatGPT
- `claude-subscription`: official Claude Code CLI with an active Pro/Max plan
- `cursor-subscription`: official Cursor model discovery; analysis is withheld
  until the CLI exposes a deny-all tool policy
- `antigravity-subscription`: official Google model discovery; analysis is
  withheld until the CLI exposes explicit no-tool/read-only-web controls
- `grok`, `openai`, `claude`, `gemini`, and `openrouter`: explicit API-key modes

`polyx analyze` requires `--provider`. `polyx report` performs no AI synthesis
unless `--provider` is supplied, so an omitted choice can never trigger a paid
model accidentally.

Run `polyx ai providers` to see the actual signed-in CLI model catalogs and the
supported API models. API rows display the catalog's dated input/output USD
price snapshot per million text tokens and link to the provider pricing page.
Prices are informational; the provider remains the billing authority. OpenRouter
aliases are marked as live-routed instead of publishing a stale estimate.

`polyx ai setup-key claude` (or `openai`, `grok`, `gemini`, `openrouter`) opens
the official key page. `polyx ai disable claude-subscription` records that the
CLI entitlement is unavailable while leaving `--provider claude` available for
a future explicitly configured Anthropic key; `polyx ai enable` reverses it.

The subscription drivers follow the adapter boundary used by
[T3 Code](https://github.com/pingdotgg/t3code): PolyX owns the bounded typed
analysis contract while each adapter owns its official CLI protocol. Child
processes receive no API keys, X cookies, or generic secret environment values.
Sentiment runs without tools. Topic research enables only the provider's
read-only research capability where it can be constrained; filesystem writes,
shell execution, plugins, MCP servers, and subagents remain unavailable.

If a CLI is installed but the account lacks a subscription, disable that row
without removing the separately selectable API provider:

```bash
export POLYX_DISABLED_SUBSCRIPTION_PROVIDERS=claude-subscription
polyx analyze "AI infrastructure" --provider claude --model claude-sonnet-4-6
```

## Output formats

PolyX works well for both humans and automation:

- terminal output by default
- `--json` for machine-readable pipelines
- `--jsonl` for stream processing
- `--csv` for spreadsheets
- `--markdown` for reports and sharing

News also supports `--csv`. Global format flags go before the command, for
example `polyx --json news "gold"`.

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
