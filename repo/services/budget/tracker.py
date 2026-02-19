import datetime
import json
import os
import pathlib
from typing import Any, Dict


def today_utc() -> str:
    """Returns the current UTC date in YYYY-MM-DD format."""
    return datetime.datetime.now(datetime.timezone.utc).date().isoformat()


class BudgetTracker:
    def __init__(self, sandbox_dir: str = "sandbox") -> None:
        self.usage_file = pathlib.Path(sandbox_dir) / "budget_usage.json"
        self.daily_limit = float(os.getenv("BUDGET_DAILY_USD_LIMIT", "10.0"))
        self.total_limit = float(os.getenv("BUDGET_TOTAL_USD_LIMIT", "50.0"))
        self.data: Dict[str, Any] = {
            "daily_usage": {},
            "total_usage": 0.0,
            "transactions": {},
        }
        self._load()

    def _load(self) -> None:
        if self.usage_file.exists():
            try:
                with open(self.usage_file, "r", encoding="utf-8") as f:
                    self.data = json.load(f)
            except Exception:
                # If load fails (corrupt file), start fresh but maybe log warning
                pass

        # Ensure schema integrity
        if "daily_usage" not in self.data:
            self.data["daily_usage"] = {}
        if "total_usage" not in self.data:
            self.data["total_usage"] = 0.0
        if "transactions" not in self.data:
            self.data["transactions"] = {}

    def _save(self) -> None:
        # Ensure directory exists
        self.usage_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.usage_file, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2, sort_keys=True)

    def check_budget(self, estimated_cost: float) -> bool:
        """
        Returns True if the estimated cost is within budget limits.
        """
        today = today_utc()
        daily_spent = self.data["daily_usage"].get(today, 0.0)

        if daily_spent + estimated_cost > self.daily_limit:
            return False
        if self.data["total_usage"] + estimated_cost > self.total_limit:
            return False
        return True

    def record_spending(self, cost: float, transaction_id: str) -> None:
        """
        Records spending. Idempotent based on transaction_id.
        """
        if transaction_id in self.data["transactions"]:
            return  # Idempotent

        today = today_utc()
        self.data["daily_usage"][today] = self.data["daily_usage"].get(today, 0.0) + cost
        self.data["total_usage"] += cost
        self.data["transactions"][transaction_id] = cost
        self._save()
