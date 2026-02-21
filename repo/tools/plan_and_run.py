#!/usr/bin/env python3
from __future__ import annotations

import argparse
import glob
import os
import re
import subprocess
import sys
from typing import List, Optional


def _repo_root() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def _latest_job_path(out_dir: str) -> Optional[str]:
    paths = sorted(glob.glob(os.path.join(out_dir, "*.job.json")))
    if not paths:
        return None
    paths.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    return paths[0]


def _extract_written_job_path(stdout: str) -> Optional[str]:
    for line in reversed(stdout.splitlines()):
        m = re.match(r"^Wrote\s+(.+\.job\.json)\s*$", line.strip())
        if m:
            return m.group(1)
    return None


def _run(cmd: List[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, text=True, capture_output=True, check=False)


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(
        description="One-command planner -> orchestrator runner."
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--prompt", help="Prompt to send to planner")
    source.add_argument("--prd", help="Path to PRD json")
    parser.add_argument("--provider", default="ai_studio", help="Planner provider")
    parser.add_argument("--inbox", default="sandbox/inbox", help="Inbox directory")
    parser.add_argument(
        "--out", default="sandbox/jobs", help="Planner output directory"
    )
    parser.add_argument("--job-id", default=None, help="Optional job_id override")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Generate job only; skip orchestrator run",
    )
    args = parser.parse_args(argv)

    root = _repo_root()
    os.chdir(root)

    planner_cmd = ["python3", "-m", "repo.services.planner.planner_cli"]
    if args.prompt:
        planner_cmd += ["--prompt", args.prompt]
    else:
        planner_cmd += ["--prd", args.prd]
    planner_cmd += [
        "--provider",
        args.provider,
        "--inbox",
        args.inbox,
        "--out",
        args.out,
    ]
    if args.job_id:
        planner_cmd += ["--job-id", args.job_id]

    print("STEP planner:", " ".join(planner_cmd))
    planner_res = _run(planner_cmd)
    if planner_res.stdout:
        print(planner_res.stdout, end="")
    if planner_res.stderr:
        print(planner_res.stderr, file=sys.stderr, end="")
    if planner_res.returncode != 0:
        return planner_res.returncode

    job_path = _extract_written_job_path(planner_res.stdout) or _latest_job_path(
        args.out
    )
    if not job_path:
        print("ERROR: planner succeeded but no job.json path found", file=sys.stderr)
        return 1
    print(f"STEP planner output: {job_path}")

    if args.dry_run:
        print("DRY RUN: skipping orchestrator")
        return 0

    orch_cmd = ["python3", "-m", "repo.services.orchestrator", "--job", job_path]
    print("STEP orchestrator:", " ".join(orch_cmd))
    orch_res = _run(orch_cmd)
    if orch_res.stdout:
        print(orch_res.stdout, end="")
    if orch_res.stderr:
        print(orch_res.stderr, file=sys.stderr, end="")
    return orch_res.returncode


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
