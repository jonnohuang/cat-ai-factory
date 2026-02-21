#!/usr/bin/env python3
import pathlib
import sys
import json
import os
import subprocess
import shutil

# Add repo root to sys.path
repo_root = pathlib.Path(__file__).resolve().parents[2]
sys.path.append(str(repo_root))

from repo.services.budget.tracker import BudgetTracker, today_utc

RALPH_TOOL = repo_root / "repo" / "services" / "orchestrator" / "ralph_loop.py"

def setup_mock_job(job_id):
    job_dir = repo_root / "sandbox" / "jobs"
    job_dir.mkdir(parents=True, exist_ok=True)
    job_path = job_dir / f"{job_id}.job.json"
    
    job_data = {
        "version": "job.v1",
        "job_id": job_id,
        "render": {
            "background_asset": "assets/demo/mochi_front.png",
            "output_basename": job_id
        }
    }
    
    with open(job_path, "w") as f:
        json.dump(job_data, f, indent=2)
    return job_path

def test_budget_enforcement():
    print("Testing Budget Enforcement...")
    
    sandbox_dir = repo_root / "sandbox"
    budget_file = sandbox_dir / "budget_usage.json"
    
    # Backup existing budget if any
    backup_file = sandbox_dir / "budget_usage.json.bak"
    if budget_file.exists():
        shutil.copyfile(budget_file, backup_file)
    
    try:
        # 1. Create a budget file that is ALREADY EXCEEDED
        today = today_utc()
        with open(budget_file, "w") as f:
            json.dump({
                "daily_usage": {today: 100.0},
                "total_usage": 100.0,
                "transactions": {}
            }, f)
        
        job_id = "smoke-budget-fail"
        job_path = setup_mock_job(job_id)
        
        # 2. Run Ralph Loop and expect failure
        cmd = [sys.executable, str(RALPH_TOOL), "--job", str(job_path)]
        env = os.environ.copy()
        env["BUDGET_DAILY_USD_LIMIT"] = "10.0"
        env["BUDGET_TOTAL_USD_LIMIT"] = "50.0"
        
        result = subprocess.run(cmd, capture_output=True, text=True, env=env)
        
        print(f"Ralph Exit Code: {result.returncode}")
        assert result.returncode != 0, "Expected Ralph to fail due to budget exhaustion"
        assert "Budget exceeded" in result.stdout, "Expected stdout to mention budget exhaustion"

        # Check events
        events_path = sandbox_dir / "logs" / job_id / "events.ndjson"
        assert events_path.exists(), "Events file should exist"
        events = events_path.read_text().splitlines()
        last_event = json.loads(events[-1])
        assert last_event["event"] == "BUDGET_EXCEEDED", f"Expected BUDGET_EXCEEDED event, got {last_event['event']}"
        
        print("  [PASS] Budget enforcement verified.")

    finally:
        # Restore backup
        if backup_file.exists():
            shutil.copyfile(backup_file, budget_file)
            backup_file.unlink()
        elif budget_file.exists():
            budget_file.unlink()
            
        # Cleanup logs
        logs_dir = sandbox_dir / "logs" / "smoke-budget-fail"
        if logs_dir.exists():
            shutil.rmtree(logs_dir)

if __name__ == "__main__":
    test_budget_enforcement()
