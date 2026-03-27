"""Per-operation cost tracking, daily aggregates, and budget management."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from polyx.config import Config

from polyx.types import CostEntry, DailyAggregate

# Cost rates per operation (matching X API v2 pricing)
COST_RATES: dict[str, dict[str, float]] = {
    "search/recent": {"per_tweet": 0.005, "per_call": 0},
    "search/all": {"per_tweet": 0.01, "per_call": 0},
    "trends": {"per_tweet": 0, "per_call": 0.10},
    "user_lookup": {"per_tweet": 0, "per_call": 0.005},
    "timeline": {"per_tweet": 0.005, "per_call": 0},
    "tweet_lookup": {"per_tweet": 0, "per_call": 0.005},
    "graphql": {"per_tweet": 0, "per_call": 0},  # Free
}


class CostTracker:
    """Tracks API costs with daily aggregation and budget enforcement."""

    def __init__(self, config: Config) -> None:
        self._config = config
        self._file = config.data_dir / "costs.json"
        self._budget = config.daily_budget
        self._retention_days = 30

    @staticmethod
    def _utcnow() -> datetime:
        return datetime.now(UTC)

    @classmethod
    def _today(cls) -> str:
        return cls._utcnow().strftime("%Y-%m-%d")

    def _load(self) -> dict[str, Any]:
        if not self._file.exists():
            return {"entries": [], "daily": {}}
        try:
            with open(self._file) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {"entries": [], "daily": {}}

    def _save(self, data: dict[str, Any]) -> None:
        self._file.parent.mkdir(parents=True, exist_ok=True)
        with open(self._file, "w") as f:
            json.dump(data, f, indent=2)

    def record(self, operation: str, tweets_read: int, endpoint: str) -> float:
        """Record a cost entry. Returns the cost in USD."""
        rates = COST_RATES.get(endpoint, COST_RATES.get(operation, {"per_tweet": 0, "per_call": 0}))
        cost = rates["per_tweet"] * tweets_read + rates["per_call"]

        entry = CostEntry(
            timestamp=self._utcnow().isoformat(),
            operation=operation,
            endpoint=endpoint,
            tweets_read=tweets_read,
            cost_usd=cost,
        )

        data = self._load()
        data["entries"].append(entry.to_dict())

        # Update daily aggregate
        today = self._today()
        daily = data.get("daily", {})
        if today not in daily:
            daily[today] = {"total_cost": 0, "total_tweets": 0, "operations": 0}
        daily[today]["total_cost"] = round(daily[today]["total_cost"] + cost, 6)
        daily[today]["total_tweets"] += tweets_read
        daily[today]["operations"] += 1
        data["daily"] = daily

        # Auto-prune old entries
        self._prune_old(data)
        self._save(data)
        return cost

    def _prune_old(self, data: dict[str, Any]) -> None:
        cutoff = (self._utcnow() - timedelta(days=self._retention_days)).strftime("%Y-%m-%d")
        daily = data.get("daily", {})
        data["daily"] = {k: v for k, v in daily.items() if k >= cutoff}
        # Also prune entries list
        data["entries"] = [
            e for e in data.get("entries", [])
            if e.get("timestamp", "")[:10] >= cutoff
        ]

    def get_daily(self, date: str | None = None) -> DailyAggregate:
        """Get aggregate for a specific date (default: today)."""
        if date is None:
            date = self._today()
        data = self._load()
        daily = data.get("daily", {}).get(date, {})
        entries = [
            CostEntry.from_dict(e) for e in data.get("entries", [])
            if e.get("timestamp", "")[:10] == date
        ]
        return DailyAggregate(
            date=date,
            total_cost=daily.get("total_cost", 0),
            total_tweets=daily.get("total_tweets", 0),
            operations=daily.get("operations", 0),
            entries=entries,
        )

    def get_range(self, start: str, end: str) -> list[DailyAggregate]:
        """Get aggregates for a date range."""
        data = self._load()
        daily = data.get("daily", {})
        results = []
        for date, agg in sorted(daily.items()):
            if start <= date <= end:
                entries = [
                    CostEntry.from_dict(e) for e in data.get("entries", [])
                    if e.get("timestamp", "")[:10] == date
                ]
                results.append(DailyAggregate(
                    date=date,
                    total_cost=agg.get("total_cost", 0),
                    total_tweets=agg.get("total_tweets", 0),
                    operations=agg.get("operations", 0),
                    entries=entries,
                ))
        return results

    def check_budget(self) -> tuple[bool, float, float]:
        """Check budget status. Returns (ok, remaining, pct_used)."""
        today = self.get_daily()
        spent = today.total_cost
        remaining = max(0, self._budget - spent)
        pct = (spent / self._budget * 100) if self._budget > 0 else 0
        ok = spent < self._budget
        return ok, remaining, pct

    def get_summary(self, period: str = "today") -> str:
        """Get a formatted cost summary for the given period."""
        today = self._today()
        if period == "today":
            agg = self.get_daily(today)
            return (
                f"Costs for {today}:\n"
                f"  Operations: {agg.operations}\n"
                f"  Tweets read: {agg.total_tweets}\n"
                f"  Total cost: ${agg.total_cost:.4f}\n"
                f"  Budget: ${self._budget:.2f}"
            )
        elif period == "week":
            start = (self._utcnow() - timedelta(days=7)).strftime("%Y-%m-%d")
            aggregates = self.get_range(start, today)
        elif period == "month":
            start = (self._utcnow() - timedelta(days=30)).strftime("%Y-%m-%d")
            aggregates = self.get_range(start, today)
        else:  # all
            aggregates = self.get_range("2000-01-01", today)

        total_cost = sum(a.total_cost for a in aggregates)
        total_tweets = sum(a.total_tweets for a in aggregates)
        total_ops = sum(a.operations for a in aggregates)
        lines = [
            f"Costs ({period}):",
            f"  Days: {len(aggregates)}",
            f"  Operations: {total_ops}",
            f"  Tweets read: {total_tweets}",
            f"  Total cost: ${total_cost:.4f}",
        ]
        return "\n".join(lines)

    def reset_today(self) -> None:
        """Reset today's cost tracking."""
        today = self._today()
        data = self._load()
        data.get("daily", {}).pop(today, None)
        data["entries"] = [
            e for e in data.get("entries", [])
            if e.get("timestamp", "")[:10] != today
        ]
        self._save(data)
