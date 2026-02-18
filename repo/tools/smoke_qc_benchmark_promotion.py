#!/usr/bin/env python3
from __future__ import annotations

import pathlib
import subprocess
import sys


def _repo_root() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parents[2]


def _run(cmd: list[str], cwd: pathlib.Path) -> None:
    print("RUN:", " ".join(cmd))
    subprocess.run(cmd, cwd=str(cwd), check=True)


def main(argv: list[str]) -> int:
    root = _repo_root()
    _run([sys.executable, "-m", "repo.tools.smoke_qc_policy_report_contract"], root)
    _run(
        [
            sys.executable,
            "-m",
            "repo.tools.benchmark_qc_advisory_lift",
            "--job-ids",
            "smoke-segment-stitch-runtime",
        ],
        root,
    )
    _run(
        [
            sys.executable,
            "-m",
            "repo.tools.validate_qc_advisory_benchmark",
            "sandbox/logs/qc/benchmarks/qc_advisory_benchmark.v1.json",
        ],
        root,
    )
    _run(
        [
            sys.executable,
            "-m",
            "repo.tools.validate_qc_promotion_gate",
            "repo/shared/qc_promotion_gate.v1.json",
        ],
        root,
    )
    _run(
        [
            sys.executable,
            "-m",
            "repo.tools.evaluate_qc_promotion_gate",
            "--benchmark-relpath",
            "sandbox/logs/qc/benchmarks/qc_advisory_benchmark.v1.json",
        ],
        root,
    )
    _run(
        [
            sys.executable,
            "-m",
            "repo.tools.validate_qc_promotion_decision",
            "sandbox/logs/qc/benchmarks/qc_promotion_decision.v1.json",
        ],
        root,
    )
    print("OK: qc benchmark + promotion smoke")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
