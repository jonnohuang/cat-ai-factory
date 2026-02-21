#!/usr/bin/env python3
import argparse
import json
import pathlib
import sys
import os

# Add repo root to sys.path
repo_root = pathlib.Path(__file__).resolve().parents[2]
sys.path.append(str(repo_root))

from repo.services.budget.tracker import BudgetTracker

def main():
    parser = argparse.ArgumentParser(description="Cat AI Factory Budget Monitor")
    parser.add_argument("--reset", action="store_true", help="Reset all budget usage")
    parser.add_argument("--set-daily", type=float, help="Set new daily USD limit")
    parser.add_argument("--set-total", type=float, help="Set new total USD limit")
    args = parser.parse_args()

    sandbox_dir = repo_root / "sandbox"
    tracker = BudgetTracker(str(sandbox_dir))

    if args.reset:
        tracker.data = {
            "daily_usage": {},
            "total_usage": 0.0,
            "transactions": {},
        }
        tracker._save()
        print("Budget usage has been reset.")

    if args.set_daily is not None:
        print(f"Update your .env file: BUDGET_DAILY_USD_LIMIT={args.set_daily}")
        
    if args.set_total is not None:
        print(f"Update your .env file: BUDGET_TOTAL_USD_LIMIT={args.set_total}")

    summary = tracker.get_usage_summary()
    
    print("\n--- Budget Status ---")
    print(f"Daily Limit: ${summary['daily_limit']:.2f}")
    print(f"Daily Spent: ${summary['daily_spent']:.4f}")
    print(f"Remaining:   ${summary['remaining_daily']:.4f}")
    print("----------------------")
    print(f"Total Limit: ${summary['total_limit']:.2f}")
    print(f"Total Spent: ${summary['total_spent']:.4f}")
    print(f"Remaining:   ${summary['remaining_total']:.4f}")
    print("----------------------\n")

    if not tracker.check_budget(0.0):
        print("!!! ALERT: Budget Limit Reached !!!")
        sys.exit(1)

if __name__ == "__main__":
    main()
