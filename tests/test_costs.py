"""Test cost tracking."""

from polyx.config import Config
from polyx.storage.costs import CostTracker


def test_cost_tracking(tmp_path):
    config = Config.load()
    config.data_dir = tmp_path
    tracker = CostTracker(config)

    # Initial state
    assert tracker.get_daily().total_cost == 0.0

    # Record operation
    tracker.record("search", 100, "search/recent")
    # search_recent is $0.005/tweet -> $0.50
    assert tracker.get_daily().total_cost == 0.50

    # Multiple records
    tracker.record("search", 50, "search/all")
    # search_full is $0.01/tweet -> $0.50. Total $1.00
    assert tracker.get_daily().total_cost == 1.00

    # Budget check
    tracker._budget = 0.80
    ok, remaining, pct = tracker.check_budget()
    assert ok is False
    assert remaining == 0.0
    assert pct >= 100.0


def test_cost_reset(tmp_path):
    config = Config.load()
    config.data_dir = tmp_path
    tracker = CostTracker(config)
    tracker.record("trends", 0, "trends")
    assert tracker.get_daily().total_cost > 0

    tracker.reset_today()
    assert tracker.get_daily().total_cost == 0
