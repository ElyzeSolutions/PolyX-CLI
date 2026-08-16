"""PolyX CLI — Click-based command interface."""

from __future__ import annotations

import asyncio
import re
import time
from functools import wraps
from typing import TYPE_CHECKING, Any

import click

from polyx import __version__
from polyx.exceptions import AuthenticationError, ConfigurationError, NotSupportedError

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine

SUBSCRIPTION_AND_API_PROVIDERS = [
    "grok-subscription",
    "codex-subscription",
    "claude-subscription",
    "cursor-subscription",
    "antigravity-subscription",
    "openai",
    "claude",
    "grok",
    "openrouter",
    "gemini",
]


def async_command(
    f: Callable[..., Coroutine[Any, Any, Any]],
) -> Callable[..., Any]:
    """Decorator to run async click commands."""
    @wraps(f)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        return asyncio.run(f(*args, **kwargs))
    return wrapper


def _news_cache_key(query: str, domain: str, max_results: int, max_age_hours: int) -> str:
    """Build the canonical cache key for a News request."""
    return f"news:v1:{domain}:{max_results}:{max_age_hours}:{query}"


def _normalize_news_domain(
    _context: click.Context,
    _parameter: click.Parameter,
    value: str,
) -> str:
    """Normalize an optional, integration-defined News routing label."""
    domain = value.strip().lower()
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", domain):
        raise click.BadParameter(
            "use 1-64 lowercase letters, numbers, hyphens, or underscores"
        )
    return domain


def _select_browser_session(cookies: list[dict[str, Any]]) -> dict[str, str] | None:
    """Select one unexpired auth/CSRF pair from a single X cookie domain."""
    sessions: dict[str, dict[str, str]] = {}
    now = time.time()
    for cookie in cookies:
        name = cookie.get("name")
        value = cookie.get("value")
        domain = str(cookie.get("domain", "")).lstrip(".").lower()
        expires = cookie.get("expires")
        if (
            name not in {"auth_token", "ct0"}
            or not value
            or domain not in {"x.com", "twitter.com"}
            or (expires is not None and not isinstance(expires, (int, float)))
            or (isinstance(expires, (int, float)) and expires > 0 and expires <= now)
        ):
            continue
        sessions.setdefault(domain, {})[str(name)] = str(value)
    for domain in ("x.com", "twitter.com"):
        session = sessions.get(domain, {})
        if set(session) == {"auth_token", "ct0"}:
            return session
    return None


class AliasedGroup(click.Group):
    """Click group with command aliases."""

    ALIASES = {
        "s": "search",
        "w": "watch",
        "p": "profile",
        "tr": "trends",
        "n": "news",
    }

    def get_command(self, ctx: click.Context, cmd_name: str) -> click.Command | None:
        cmd_name = self.ALIASES.get(cmd_name, cmd_name)
        return super().get_command(ctx, cmd_name)

    def resolve_command(
        self, ctx: click.Context, args: list[str]
    ) -> tuple[str | None, click.Command | None, list[str]]:
        cmd_name = args[0] if args else None
        if cmd_name and cmd_name in self.ALIASES:
            args[0] = self.ALIASES[cmd_name]
        return super().resolve_command(ctx, args)


@click.group(cls=AliasedGroup)
@click.version_option(__version__, prog_name="polyx")
@click.option("--json", "output_format", flag_value="json", help="Output as JSON.")
@click.option("--jsonl", "output_format", flag_value="jsonl", help="Output as JSONL.")
@click.option("--csv", "output_format", flag_value="csv", help="Output as CSV.")
@click.option("--markdown", "output_format", flag_value="markdown", help="Output as Markdown.")
@click.option("--client", "client_type", type=click.Choice(["v2", "graphql", "auto"]), default="auto", help="X client to use.")
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose output.")
@click.pass_context
def main(ctx: click.Context, output_format: str | None, client_type: str, verbose: bool) -> None:
    """PolyX — X/Twitter intelligence toolkit."""
    import logging
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s: %(message)s")

    ctx.ensure_object(dict)
    ctx.obj["output_format"] = output_format or "terminal"
    ctx.obj["client_type"] = client_type
    ctx.obj["verbose"] = verbose


@main.command()
@click.argument("query")
@click.option("--limit", "-l", default=20, help="Max tweets to return.")
@click.option("--sort", type=click.Choice(["relevancy", "recency", "likes", "impressions"]), default="relevancy")
@click.option("--since", help="Time window (1h, 6h, 1d, 7d) or ISO date.")
@click.option("--pages", default=1, help="Number of pages to fetch.")
@click.option("--min-likes", default=0, help="Minimum likes filter.")
@click.option("--no-noise", is_flag=True, help="Filter promotional noise.")
@click.option("--sentiment", is_flag=True, help="Include keyword sentiment analysis.")
@click.option("--no-cache", is_flag=True, help="Bypass cache.")
@click.option("--full-archive", is_flag=True, help="Search full archive (API v2 only).")
@click.pass_context
@async_command
async def search(
    ctx: click.Context,
    query: str,
    limit: int,
    sort: str,
    since: str | None,
    pages: int,
    min_likes: int,
    no_noise: bool,
    sentiment: bool,
    no_cache: bool,
    full_archive: bool,
) -> None:
    """Search tweets by query."""
    from polyx.client.auto import AutoClient
    from polyx.config import Config
    from polyx.output.formats import get_formatter
    from polyx.storage.cache import FileCache
    from polyx.storage.costs import CostTracker

    config = Config.load()
    fmt = get_formatter(ctx.obj["output_format"])
    cache = FileCache(config)
    costs = CostTracker(config)

    cache_key = f"search:{query}:{limit}:{pages}:{since}:{full_archive}"
    if not no_cache:
        cached = cache.get(cache_key)
        if cached:
            from polyx.types import SearchResult
            result = SearchResult.from_dict(cached)
            result.cached = True
            click.echo(fmt.format_search(result))
            return

    async with AutoClient(config, client_type=ctx.obj["client_type"]) as client:
        if full_archive:
            result = await client.search_full_archive(query, limit=limit, pages=pages)
        else:
            result = await client.search(
                query, limit=limit, sort=sort, since=since, pages=pages, min_likes=min_likes,
            )

    if no_noise:
        from polyx.analysis.noise import filter_noise
        result.tweets = filter_noise(result.tweets)

    if sort in ("likes", "impressions"):
        result.tweets.sort(
            key=lambda t: getattr(t.metrics, sort, 0),
            reverse=True,
        )

    if sentiment:
        from polyx.analysis.sentiment import KeywordSentimentAnalyzer
        analyzer = KeywordSentimentAnalyzer()
        sent_result = analyzer.analyze(result.tweets)
        click.echo(fmt.format_search(result, sentiment=sent_result))
    else:
        click.echo(fmt.format_search(result))

    if not result.cached:
        cache.set(cache_key, result.to_dict(), ttl=config.cache_ttl)
        costs.record(
            "search", result.total_results, "search/recent" if not full_archive else "search/all"
        )


@main.command()
@click.argument("query")
@click.option(
    "--max-results",
    "-n",
    type=click.IntRange(1, 100),
    default=10,
    show_default=True,
    help="Maximum news stories to return.",
)
@click.option(
    "--max-age-hours",
    type=click.IntRange(1, 720),
    default=168,
    show_default=True,
    help="Only return stories updated within this many hours.",
)
@click.option(
    "--domain",
    default="general",
    show_default=True,
    callback=_normalize_news_domain,
    metavar="LABEL",
    help="Optional routing label for downstream consumers.",
)
@click.option("--no-cache", is_flag=True, help="Bypass cache and fetch fresh stories.")
@click.pass_context
@async_command
async def news(
    ctx: click.Context,
    query: str,
    max_results: int,
    max_age_hours: int,
    domain: str,
    no_cache: bool,
) -> None:
    """Search breaking news stories clustered and summarized by X."""
    from polyx.client.auto import AutoClient
    from polyx.config import Config
    from polyx.output.formats import get_formatter
    from polyx.storage.cache import FileCache
    from polyx.storage.costs import NEWS_RESOURCE_ESTIMATE_USD, CostTracker
    from polyx.types import NewsSearchResult

    config = Config.load()
    fmt = get_formatter(ctx.obj["output_format"])
    cache = FileCache(config)
    costs = CostTracker(config)
    cache_key = _news_cache_key(query, domain, max_results, max_age_hours)

    if not no_cache:
        cached = cache.get(cache_key)
        if isinstance(cached, dict):
            result = NewsSearchResult.from_dict(cached)
            result.cached = True
            click.echo(fmt.format_news(result))
            return

    budget_ok, remaining_budget, _ = costs.check_budget()
    affordable_results = int(remaining_budget / NEWS_RESOURCE_ESTIMATE_USD + 1e-9)
    if not budget_ok or affordable_results < 1:
        raise click.ClickException(
            "X News request blocked: PolyX daily budget is exhausted. "
            "Cached results remain available; raise POLYX_DAILY_BUDGET to allow paid calls."
        )
    live_max_results = min(max_results, affordable_results)

    try:
        async with AutoClient(config, client_type=ctx.obj["client_type"]) as client:
            result = await client.search_news(
                query,
                max_results=live_max_results,
                max_age_hours=max_age_hours,
            )
    except (AuthenticationError, ConfigurationError, NotSupportedError) as error:
        raise click.ClickException(str(error)) from error

    result.domain = domain
    # X has already served the paid resources. Record them before output or
    # cache I/O so a broken pipe or local write failure cannot hide the spend.
    costs.record("news", result.total_results, "news/search")
    click.echo(fmt.format_news(result))
    if live_max_results == max_results and result.stories and not result.errors:
        cache.set(cache_key, result.to_dict(), ttl=config.cache_ttl)


@main.group()
def auth() -> None:
    """Manage X authentication without printing secrets."""


@auth.command("import-browser")
@click.option(
    "--browser",
    type=click.Choice(["chrome", "edge", "firefox"]),
    default="chrome",
    show_default=True,
)
def import_browser_auth(browser: str) -> None:
    """Import auth_token and ct0 from a local browser profile."""
    try:
        import rookiepy
    except ImportError as error:
        raise click.ClickException(
            "Browser import needs the optional browser extra: "
            "uv tool install 'polyx-cli[browser]'"
        ) from error

    extractor = getattr(rookiepy, browser)
    try:
        cookies = extractor(["x.com", "twitter.com"])
    except Exception as error:
        raise click.ClickException(
            f"The X session in {browser.title()} could not be read. "
            "Close the browser or unlock its credential store, then try again."
        ) from error
    selected = _select_browser_session(cookies)
    if selected is None:
        raise click.ClickException(
            f"No complete authenticated X session was found in {browser.title()}. "
            "Sign in to x.com in that browser and try again."
        )

    from polyx.config import Config

    try:
        destination = Config.load().save_browser_cookies(
            selected["auth_token"], selected["ct0"]
        )
    except ConfigurationError as error:
        raise click.ClickException(str(error)) from error
    click.echo(
        f"Imported the X browser session into {destination}. "
        "Use --client graphql to select the cookie fallback."
    )


@main.command()
@click.option("--location", "-l", default="worldwide", help="Location name or WOEID.")
@click.option("--locations", is_flag=True, help="List available locations.")
@click.pass_context
@async_command
async def trends(ctx: click.Context, location: str, locations: bool) -> None:
    """Show trending topics."""
    from polyx.monitoring.trends import LOCATIONS, TrendsProvider

    if locations:
        for name, woeid in sorted(LOCATIONS.items()):
            click.echo(f"  {name}: {woeid}")
        return

    from polyx.config import Config
    from polyx.output.formats import get_formatter

    config = Config.load()
    fmt = get_formatter(ctx.obj["output_format"])
    provider = TrendsProvider(config)
    topics = await provider.get_trends(location)
    click.echo(fmt.format_trends(topics))


@main.command()
@click.argument("username")
@click.option("--tweets", "-t", default=20, help="Number of recent tweets.")
@click.pass_context
@async_command
async def profile(ctx: click.Context, username: str, tweets: int) -> None:
    """Show user profile and recent tweets."""
    from polyx.client.auto import AutoClient
    from polyx.config import Config
    from polyx.output.formats import get_formatter

    config = Config.load()
    fmt = get_formatter(ctx.obj["output_format"])

    async with AutoClient(config, client_type=ctx.obj["client_type"]) as client:
        user = await client.get_user(username.lstrip("@"))
        timeline = await client.get_user_timeline(user.id, count=tweets)

    click.echo(fmt.format_profile(user, timeline))


@main.command()
@click.argument("tweet_id")
@click.pass_context
@async_command
async def thread(ctx: click.Context, tweet_id: str) -> None:
    """Fetch a conversation thread."""
    from polyx.client.auto import AutoClient
    from polyx.config import Config
    from polyx.output.formats import get_formatter

    config = Config.load()
    fmt = get_formatter(ctx.obj["output_format"])

    async with AutoClient(config, client_type=ctx.obj["client_type"]) as client:
        result = await client.search(f"conversation_id:{tweet_id}", limit=50)

    click.echo(fmt.format_search(result))


@main.command()
@click.argument("tweet_id")
@click.pass_context
@async_command
async def tweet(ctx: click.Context, tweet_id: str) -> None:
    """Fetch a single tweet."""
    from polyx.client.auto import AutoClient
    from polyx.config import Config
    from polyx.output.formats import get_formatter

    config = Config.load()
    fmt = get_formatter(ctx.obj["output_format"])

    async with AutoClient(config, client_type=ctx.obj["client_type"]) as client:
        tw = await client.get_tweet(tweet_id)

    click.echo(fmt.format_tweet(tw))


@main.command()
@click.argument("query")
@click.option("--interval", type=click.Choice(["30s", "1m", "5m", "15m"]), default="5m")
@click.option("--webhook", help="Webhook URL for notifications.")
@click.option("--quiet", is_flag=True, help="Suppress terminal output.")
@click.pass_context
@async_command
async def watch(ctx: click.Context, query: str, interval: str, webhook: str | None, quiet: bool) -> None:
    """Watch tweets in real-time with polling."""
    from polyx.client.auto import AutoClient
    from polyx.config import Config
    from polyx.monitoring.watch import WatchSession
    from polyx.output.formats import get_formatter

    config = Config.load()
    fmt = get_formatter(ctx.obj["output_format"])

    async with AutoClient(config, client_type=ctx.obj["client_type"]) as client:
        session = WatchSession(client, config, fmt, quiet=quiet)
        await session.run(query, interval=interval, webhook_url=webhook)


@main.command()
@click.argument("query")
@click.option(
    "--provider",
    "-p",
    type=click.Choice(SUBSCRIPTION_AND_API_PROVIDERS),
    required=True,
    help="AI provider.",
)
@click.option("--model", "-m", help="Provider-native model ID override.")
@click.option("--prompt", help="Custom analysis prompt.")
@click.pass_context
@async_command
async def analyze(
    ctx: click.Context,
    query: str,
    provider: str,
    model: str | None,
    prompt: str | None,
) -> None:
    """AI-powered tweet analysis."""
    from polyx.ai.registry import get_provider
    from polyx.client.auto import AutoClient
    from polyx.config import Config

    config = Config.load()
    async with AutoClient(config, client_type=ctx.obj["client_type"]) as client:
        result = await client.search(query, limit=50, pages=2)

    ai = get_provider(provider, config, model=model)
    analysis = await ai.analyze_topic(result.tweets, query, custom_prompt=prompt)
    click.echo(analysis)


@main.command()
@click.argument("topic")
@click.option("--pages", default=3, help="Pages of tweets to fetch.")
@click.option("--sentiment", is_flag=True, help="Include sentiment analysis.")
@click.option(
    "--provider",
    "-p",
    type=click.Choice(SUBSCRIPTION_AND_API_PROVIDERS),
    help="AI provider for synthesis.",
)
@click.option("--model", "-m", help="Model override.")
@click.option("--accounts", multiple=True, help="Specific accounts to include.")
@click.option("--save", is_flag=True, help="Save report to file.")
@click.pass_context
@async_command
async def report(
    ctx: click.Context,
    topic: str,
    pages: int,
    sentiment: bool,
    provider: str | None,
    model: str | None,
    accounts: tuple[str, ...],
    save: bool,
) -> None:
    """Generate an intelligence report."""
    from polyx.config import Config
    from polyx.output.reports import ReportGenerator

    config = Config.load()
    generator = ReportGenerator(config, client_type=ctx.obj["client_type"])
    report_text = await generator.generate(
        topic, pages=pages, sentiment=sentiment,
        provider=provider, model=model, accounts=list(accounts), save=save,
    )
    click.echo(report_text)


@main.group("ai")
def ai_providers() -> None:
    """Inspect AI credential modes and live subscription model catalogs."""


@ai_providers.command("disable")
@click.argument(
    "provider",
    type=click.Choice(
        [
            "grok-subscription",
            "codex-subscription",
            "claude-subscription",
            "cursor-subscription",
            "antigravity-subscription",
        ]
    ),
)
def ai_provider_disable(provider: str) -> None:
    """Mark an unavailable subscription CLI disabled without affecting API mode."""

    from polyx.config import Config

    config = Config.load()
    providers = tuple((*config.disabled_subscription_providers, provider))
    config.save_disabled_subscription_providers(providers)
    click.echo(f"Disabled {provider}; its separately configured API mode is unchanged.")


@ai_providers.command("enable")
@click.argument(
    "provider",
    type=click.Choice(
        [
            "grok-subscription",
            "codex-subscription",
            "claude-subscription",
            "cursor-subscription",
            "antigravity-subscription",
        ]
    ),
)
def ai_provider_enable(provider: str) -> None:
    """Re-enable discovery and use of a subscription CLI."""

    from polyx.config import Config

    config = Config.load()
    providers = tuple(
        item for item in config.disabled_subscription_providers if item != provider
    )
    config.save_disabled_subscription_providers(providers)
    click.echo(f"Enabled {provider}; PolyX will require its signed-in CLI entitlement.")


@ai_providers.command("setup-key")
@click.argument(
    "provider",
    type=click.Choice(["openai", "claude", "grok", "gemini", "openrouter"]),
)
def ai_provider_setup_key(provider: str) -> None:
    """Open the official API-key page for an explicit paid provider mode."""

    destinations = {
        "openai": ("https://platform.openai.com/api-keys", "OPENAI_API_KEY"),
        "claude": ("https://console.anthropic.com/settings/keys", "ANTHROPIC_API_KEY"),
        "grok": ("https://console.x.ai/", "XAI_API_KEY"),
        "gemini": ("https://aistudio.google.com/app/apikey", "GOOGLE_API_KEY"),
        "openrouter": ("https://openrouter.ai/settings/keys", "OPENROUTER_API_KEY"),
    }
    url, variable = destinations[provider]
    click.launch(url)
    click.echo(
        f"Opened the official {provider} key page. Store the key in {variable}; "
        "PolyX never switches to this paid mode automatically."
    )


@ai_providers.command("providers")
@click.pass_context
@async_command
async def ai_provider_list(ctx: click.Context) -> None:
    """List authenticated CLI providers and the models offered by each account."""

    import json

    from polyx.ai.api_catalog import PRICING_AS_OF, PRICING_URLS, api_model_rows
    from polyx.ai.subscription_cli import discover_subscription_providers
    from polyx.config import Config

    config = Config.load()
    subscriptions = await discover_subscription_providers(
        config.disabled_subscription_providers
    )
    providers: list[dict[str, object]] = [
        *subscriptions,
        {
            "provider": "grok",
            "credential_mode": "api_key",
            "ready": bool(config.xai_api_key),
            "default_model": "grok-4.3",
            "models": api_model_rows("grok"),
            "pricing_as_of": PRICING_AS_OF,
            "pricing_url": PRICING_URLS["grok"],
            "detail": "Explicit paid xAI API mode; never selected as a subscription fallback.",
        },
        {
            "provider": "openai",
            "credential_mode": "api_key",
            "ready": bool(config.openai_api_key),
            "default_model": "gpt-5.6-luna",
            "models": api_model_rows("openai"),
            "pricing_as_of": PRICING_AS_OF,
            "pricing_url": PRICING_URLS["openai"],
            "detail": "Explicit paid OpenAI API mode; separate from ChatGPT/Codex subscription.",
        },
        {
            "provider": "claude",
            "credential_mode": "api_key",
            "ready": bool(config.anthropic_api_key),
            "default_model": "claude-sonnet-4-6",
            "models": api_model_rows("claude"),
            "pricing_as_of": PRICING_AS_OF,
            "pricing_url": PRICING_URLS["claude"],
            "detail": "Explicit paid Anthropic API mode; separate from Claude Code subscription.",
        },
        {
            "provider": "gemini",
            "credential_mode": "api_key",
            "ready": bool(config.gemini_api_key),
            "default_model": "gemini-3.5-flash-lite",
            "models": api_model_rows("gemini"),
            "pricing_as_of": PRICING_AS_OF,
            "pricing_url": PRICING_URLS["gemini"],
            "detail": "Explicit paid Gemini API mode; separate from Antigravity subscription.",
        },
        {
            "provider": "openrouter",
            "credential_mode": "api_key",
            "ready": bool(config.openrouter_api_key),
            "default_model": "openai/gpt-5-nano",
            "models": api_model_rows("openrouter"),
            "pricing_as_of": PRICING_AS_OF,
            "pricing_url": PRICING_URLS["openrouter"],
            "detail": "Explicit OpenRouter API mode; routed-model pricing must be verified live.",
        },
    ]
    if ctx.obj["output_format"] in {"json", "jsonl"}:
        if ctx.obj["output_format"] == "jsonl":
            click.echo("\n".join(json.dumps(item, sort_keys=True) for item in providers))
        else:
            click.echo(json.dumps(providers, indent=2, sort_keys=True))
        return
    for provider in providers:
        status = "ready" if provider["ready"] else "not ready"
        click.echo(
            f"{provider['provider']} [{provider['credential_mode']}] — {status}; "
            f"default: {provider['default_model']}"
        )
        models = provider["models"]
        if isinstance(models, list):
            for model in models:
                if isinstance(model, dict):
                    marker = " *" if model.get("default") else ""
                    price = ""
                    if "input_usd_per_mtok" in model:
                        input_price = model.get("input_usd_per_mtok")
                        output_price = model.get("output_usd_per_mtok")
                        if input_price is None or output_price is None:
                            price = " — live routed price"
                        else:
                            price = f" — ${input_price}/${output_price} per input/output MTok"
                    click.echo(
                        f"  {model.get('id')} — {model.get('label')}{marker}{price}"
                    )
        click.echo(f"  {provider['detail']}")
        if provider.get("pricing_url"):
            click.echo(f"  Pricing as of: {provider['pricing_as_of']}")
            click.echo(f"  Pricing: {provider['pricing_url']}")


@main.group()
def costs() -> None:
    """API cost tracking and budget management."""


@costs.command("show")
@click.option("--period", type=click.Choice(["today", "week", "month", "all"]), default="today")
def costs_show(period: str) -> None:
    """Show API costs for a period."""
    from polyx.config import Config
    from polyx.storage.costs import CostTracker

    config = Config.load()
    tracker = CostTracker(config)
    summary = tracker.get_summary(period)
    click.echo(summary)


@costs.command("budget")
def costs_budget() -> None:
    """Show budget status."""
    from polyx.config import Config
    from polyx.storage.costs import CostTracker

    config = Config.load()
    tracker = CostTracker(config)
    ok, remaining, pct = tracker.check_budget()
    status = "OK" if ok else "EXCEEDED"
    click.echo(f"Budget: {status} — ${remaining:.2f} remaining ({pct:.0f}% used)")


@costs.command("reset")
@click.confirmation_option(prompt="Reset today's cost tracking?")
def costs_reset() -> None:
    """Reset today's cost tracking."""
    from polyx.config import Config
    from polyx.storage.costs import CostTracker

    config = Config.load()
    tracker = CostTracker(config)
    tracker.reset_today()
    click.echo("Cost tracking reset for today.")


@main.command()
def health() -> None:
    """Check PolyX configuration and connectivity."""
    from polyx.config import Config

    config = Config.load()
    click.echo(f"PolyX v{__version__}")
    click.echo(f"Data dir: {config.data_dir}")

    if config.x_bearer_token:
        click.echo("X API v2: configured")
    else:
        click.echo("X API v2: not configured (set X_BEARER_TOKEN)")

    if config.auth_token and config.ct0:
        click.echo("GraphQL: configured")
    else:
        click.echo("GraphQL: not configured (set AUTH_TOKEN + CT0)")

    for name, key in [
        ("OpenAI", config.openai_api_key),
        ("Claude API", config.anthropic_api_key),
        ("Grok", config.xai_api_key),
        ("OpenRouter", config.openrouter_api_key),
        ("Gemini", config.gemini_api_key),
    ]:
        status = "configured" if key else "not configured"
        click.echo(f"{name}: {status}")

    if config.disabled_subscription_providers:
        click.echo(
            "Subscription CLIs disabled: "
            + ", ".join(config.disabled_subscription_providers)
        )

    click.echo("Status: OK")


@main.group()
def cache() -> None:
    """Cache management."""


@cache.command("clear")
@click.confirmation_option(prompt="Clear all cached data?")
def cache_clear() -> None:
    """Clear all cached data."""
    from polyx.config import Config
    from polyx.storage.cache import FileCache

    config = Config.load()
    fc = FileCache(config)
    count = fc.clear()
    click.echo(f"Cleared {count} cached entries.")


@cache.command("stats")
def cache_stats() -> None:
    """Show cache statistics."""
    from polyx.config import Config
    from polyx.storage.cache import FileCache

    config = Config.load()
    fc = FileCache(config)
    stats = fc.stats()
    click.echo(f"Cache entries: {stats['total_files']}")
    click.echo(f"Total size: {stats['total_size_kb']:.1f} KB")


if __name__ == "__main__":
    main()
