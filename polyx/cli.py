"""PolyX CLI — Click-based command interface."""

from __future__ import annotations

import asyncio
from functools import wraps
from typing import Any

import click

from polyx import __version__


def async_command(f):  # noqa: ANN001, ANN201
    """Decorator to run async click commands."""
    @wraps(f)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        return asyncio.run(f(*args, **kwargs))
    return wrapper


class AliasedGroup(click.Group):
    """Click group with command aliases."""

    ALIASES = {
        "s": "search",
        "w": "watch",
        "p": "profile",
        "tr": "trends",
    }

    def get_command(self, ctx: click.Context, cmd_name: str) -> click.Command | None:
        cmd_name = self.ALIASES.get(cmd_name, cmd_name)
        return super().get_command(ctx, cmd_name)

    def resolve_command(self, ctx: click.Context, args: list[str]) -> tuple[str | None, click.Command | None, list[str]]:
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
        costs.record("search", result.total_results, "search/recent" if not full_archive else "search/all")


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
@click.option("--provider", "-p", type=click.Choice(["grok", "openrouter", "gemini"]), help="AI provider.")
@click.option("--model", "-m", help="Model name (e.g. 'gemini/gemini-pro').")
@click.option("--prompt", help="Custom analysis prompt.")
@click.pass_context
@async_command
async def analyze(ctx: click.Context, query: str, provider: str | None, model: str | None, prompt: str | None) -> None:
    """AI-powered tweet analysis."""
    from polyx.ai.registry import get_provider
    from polyx.client.auto import AutoClient
    from polyx.config import Config

    config = Config.load()
    # Default provider if not specified and not in model
    provider = provider or "gemini"

    async with AutoClient(config, client_type=ctx.obj["client_type"]) as client:
        result = await client.search(query, limit=50, pages=2)

    ai = get_provider(provider, config, model=model)
    analysis = await ai.analyze_topic(result.tweets, query, custom_prompt=prompt)
    click.echo(analysis)


@main.command()
@click.argument("topic")
@click.option("--pages", default=3, help="Pages of tweets to fetch.")
@click.option("--sentiment", is_flag=True, help="Include sentiment analysis.")
@click.option("--provider", "-p", type=click.Choice(["grok", "openrouter", "gemini"]), help="AI provider for synthesis.")
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
    # Default provider if not specified and not in model
    provider = provider or "gemini"

    generator = ReportGenerator(config, client_type=ctx.obj["client_type"])
    report_text = await generator.generate(
        topic, pages=pages, sentiment=sentiment,
        provider=provider, model=model, accounts=list(accounts), save=save,
    )
    click.echo(report_text)


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

    for name, key in [("Grok", config.xai_api_key), ("OpenRouter", config.openrouter_api_key), ("Gemini", config.gemini_api_key)]:
        status = "configured" if key else "not configured"
        click.echo(f"{name}: {status}")

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
