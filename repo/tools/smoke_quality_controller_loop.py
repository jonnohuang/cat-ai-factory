#!/usr/bin/env python3
from __future__ import annotations

import pathlib
import subprocess
import sys


def _repo_root() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parents[2]


def main(argv: list[str]) -> int:
    _ = argv
    root = _repo_root()
    steps = [
        "repo.tools.smoke_retry_plan_contract",
        "repo.tools.smoke_worker_retry_hooks",
        "repo.tools.smoke_controller_retry_execution",
        "repo.tools.smoke_retry_attempt_lineage",
        "repo.tools.smoke_finalize_gate_contract",
    ]
    for module in steps:
        cmd = [sys.executable, "-m", module]
        print("RUN:", " ".join(cmd))
        subprocess.check_call(cmd, cwd=str(root))

    print("OK: quality controller closed-loop smoke suite")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
