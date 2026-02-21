import os
import pathlib

import pytest

from repo.services.budget.tracker import BudgetTracker


@pytest.fixture
def sandbox_dir(tmp_path):
    d = tmp_path / "sandbox"
    d.mkdir()
    return d


def test_daily_limit(sandbox_dir):
    os.environ["BUDGET_DAILY_USD_LIMIT"] = "1.0"
    os.environ["BUDGET_TOTAL_USD_LIMIT"] = "100.0"
    tracker = BudgetTracker(sandbox_dir=str(sandbox_dir))

    assert tracker.check_budget(0.5)
    tracker.record_spending(0.5, "tx1")

    assert tracker.check_budget(0.4)
    tracker.record_spending(0.4, "tx2")

    assert not tracker.check_budget(0.2)  # 0.9 + 0.2 = 1.1 > 1.0


def test_total_limit(sandbox_dir):
    os.environ["BUDGET_DAILY_USD_LIMIT"] = "100.0"
    os.environ["BUDGET_TOTAL_USD_LIMIT"] = "2.0"
    tracker = BudgetTracker(sandbox_dir=str(sandbox_dir))

    tracker.record_spending(1.5, "tx1")
    assert tracker.check_budget(0.4)
    assert not tracker.check_budget(0.6)  # 1.5 + 0.6 = 2.1 > 2.0


def test_idempotency(sandbox_dir):
    os.environ["BUDGET_DAILY_USD_LIMIT"] = "100.0"
    os.environ["BUDGET_TOTAL_USD_LIMIT"] = "100.0"
    tracker = BudgetTracker(sandbox_dir=str(sandbox_dir))

    tracker.record_spending(1.0, "tx1")
    initial_total = tracker.data["total_usage"]

    tracker.record_spending(1.0, "tx1")
    assert tracker.data["total_usage"] == initial_total


def test_persistence(sandbox_dir):
    os.environ["BUDGET_DAILY_USD_LIMIT"] = "100.0"
    os.environ["BUDGET_TOTAL_USD_LIMIT"] = "100.0"
    tracker = BudgetTracker(sandbox_dir=str(sandbox_dir))
    tracker.record_spending(1.0, "tx1")

    tracker2 = BudgetTracker(sandbox_dir=str(sandbox_dir))
    assert tracker2.data["total_usage"] == 1.0
    assert "tx1" in tracker2.data["transactions"]
