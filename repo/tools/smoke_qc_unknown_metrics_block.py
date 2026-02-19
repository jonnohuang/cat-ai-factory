#!/usr/bin/env python3
from __future__ import annotations

import json
import pathlib
import subprocess
import sys


def _repo_root() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parents[2]


def _load(path: pathlib.Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main(argv: list[str]) -> int:
    _ = argv
    root = _repo_root()
    job_id = "smoke-qc-unknown-metrics-block"
    qc_dir = root / "sandbox" / "logs" / job_id / "qc"
    qc_dir.mkdir(parents=True, exist_ok=True)

    cmd = [sys.executable, "-m", "repo.tools.run_qc_runner", "--job-id", job_id]
    print("RUN:", " ".join(cmd))
    subprocess.check_call(cmd, cwd=str(root))

    report = _load(qc_dir / "qc_report.v1.json")
    overall = report.get("overall", {})
    if overall.get("pass") is not False:
        print("ERROR: expected overall.pass=false when required metrics are unknown", file=sys.stderr)
        return 1

    action = overall.get("recommended_action")
    if action != "escalate_hitl":
        print(f"ERROR: expected recommended_action='escalate_hitl', got {action!r}", file=sys.stderr)
        return 1

    unknown_gates = [g for g in report.get("gates", []) if isinstance(g, dict) and g.get("status") == "unknown"]
    if not unknown_gates:
        print("ERROR: expected at least one unknown gate in qc_report", file=sys.stderr)
        return 1

    print("recommended_action:", action)
    print("unknown_gate_count:", len(unknown_gates))
    print("OK:", qc_dir / "qc_report.v1.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
