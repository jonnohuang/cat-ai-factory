#!/usr/bin/env python3
"""
smoke_recast_benchmark.py

PR-34.5 smoke runner for deterministic recast benchmark harness.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys


def _repo_root() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parents[2]


def main(argv: list[str]) -> int:
    _ = argv
    root = _repo_root()
    suite = root / "repo/examples/recast_benchmark_suite.v1.example.json"
    report = (
        root
        / "sandbox/logs/benchmarks/recast-regression-smoke/recast_benchmark_report.v1.json"
    )

    run_cmd = [
        sys.executable,
        "-m",
        "repo.tools.run_recast_benchmark",
        "--suite",
        str(suite),
    ]
    print("RUN:", " ".join(run_cmd))
    subprocess.check_call(run_cmd, cwd=str(root))

    validate_cmd = [
        sys.executable,
        "-m",
        "repo.tools.validate_recast_benchmark",
        "--suite",
        str(suite),
        "--report",
        str(report),
    ]
    print("RUN:", " ".join(validate_cmd))
    subprocess.check_call(validate_cmd, cwd=str(root))
    print("OK:", report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
