"""Real-time watch monitoring with polling, dedup, and webhooks."""

from __future__ import annotations

import asyncio
import signal
import time
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

import aiohttp

from polyx.storage.costs import CostTracker

if TYPE_CHECKING:
    from polyx.config import Config
    from polyx.output.formats import Formatter
    from polyx.types import Tweet

INTERVAL_MAP = {
    "30s": 30,
    "1m": 60,
    "5m": 300,
    "15m": 900,
}


class WatchSession:
    """Continuous polling session with dedup and webhook delivery."""

    def __init__(
        self,
        client: Any,
        config: Config,
        formatter: Formatter,
        quiet: bool = False,
    ) -> None:
        self._client = client
        self._config = config
        self._fmt = formatter
        self._quiet = quiet
        self._seen: set[str] = set()
        self._running = False
        self._stats = {
            "start_time": 0.0,
            "polls": 0,
            "new_tweets": 0,
            "total_cost": 0.0,
        }

    async def poll(self, query: str, webhook_url: str | None = None) -> tuple[list[Tweet], int]:
        """Execute a single poll. Returns (new_tweets, total_fetched)."""
        result = await self._client.search(query, limit=20)

        new_tweets: list[Tweet] = []
        for tweet in result.tweets:
            if tweet.id not in self._seen:
                self._seen.add(tweet.id)
                new_tweets.append(tweet)

        total_fetched = len(result.tweets)

        if new_tweets:
            self._stats["new_tweets"] += len(new_tweets)
            if webhook_url:
                await self._send_webhook(webhook_url, new_tweets, query)

        return new_tweets, total_fetched

    async def run(
        self,
        query: str,
        interval: str = "5m",
        webhook_url: str | None = None,
    ) -> None:
        """Start the watch loop."""
        interval_sec = INTERVAL_MAP.get(interval, 300)
        self._running = True
        self._stats["start_time"] = time.time()
        costs = CostTracker(self._config)

        # Set up signal handler
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, self._stop)

        if not self._quiet:
            print(f"Watching '{query}' every {interval} (Ctrl+C to stop)")

        if webhook_url:
            self._validate_webhook(webhook_url)

        try:
            while self._running:
                # Budget check
                ok, remaining, pct = costs.check_budget()
                if not ok:
                    print(f"\nBudget exceeded (${remaining:.2f} remaining). Stopping.")
                    break
                if pct >= 80 and not self._quiet:
                    print(f"  Budget warning: {pct:.0f}% used")

                # Poll
                self._stats["polls"] += 1
                new_tweets, total_fetched = await self.poll(query, webhook_url=webhook_url)

                if new_tweets:
                    if not self._quiet:
                        for tweet in new_tweets:
                            print(self._fmt.format_tweet(tweet))
                            print()

                    cost = costs.record("search", total_fetched, "search/recent")
                    self._stats["total_cost"] += cost
                elif not self._quiet:
                    print(f"  Poll #{self._stats['polls']}: no new tweets")

                await asyncio.sleep(interval_sec)
        except asyncio.CancelledError:
            pass
        finally:
            self._print_stats()

    def _stop(self) -> None:
        self._running = False

    def _print_stats(self) -> None:
        duration = time.time() - self._stats["start_time"]
        mins = int(duration // 60)
        secs = int(duration % 60)
        print("\nWatch session ended:")
        print(f"  Duration: {mins}m {secs}s")
        print(f"  Polls: {self._stats['polls']}")
        print(f"  New tweets: {self._stats['new_tweets']}")
        print(f"  Seen total: {len(self._seen)}")
        print(f"  Estimated cost: ${self._stats['total_cost']:.4f}")

    @staticmethod
    def _validate_webhook(url: str) -> None:
        parsed = urlparse(url)
        if parsed.hostname in ("localhost", "127.0.0.1", "::1"):
            return  # Allow HTTP for localhost
        if parsed.scheme != "https":
            raise ValueError(f"Webhook URL must use HTTPS for remote hosts: {url}")

    @staticmethod
    async def _send_webhook(url: str, tweets: list[Tweet], query: str) -> None:
        payload = {
            "query": query,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "new_tweets": len(tweets),
            "tweets": [t.to_dict() for t in tweets],
        }
        try:
            async with aiohttp.ClientSession() as session, session.post(
                url,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status >= 400:
                    print(f"  Webhook delivery failed: HTTP {resp.status}")
        except Exception as e:
            print(f"  Webhook delivery failed: {e}")
