#!/usr/bin/env python3
"""
smoke_mode_b_contracts.py

PR-33.3 smoke runner for Mode B optional contracts.
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
    cmd = [
        sys.executable,
        "-m",
        "repo.tools.validate_mode_b_contracts",
        "--script-plan",
        "repo/examples/script_plan.v1.example.json",
        "--identity-anchor",
        "repo/examples/identity_anchor.v1.example.json",
        "--storyboard",
        "repo/examples/storyboard.v1.example.json",
    ]
    print("RUN:", " ".join(cmd))
    subprocess.check_call(cmd, cwd=str(root))
    print("OK: Mode B smoke validation")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

