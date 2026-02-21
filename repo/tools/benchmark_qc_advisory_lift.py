#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import sys
from typing import Any, Dict, Optional


def _repo_root() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parents[2]


def _utc_now() -> str:
    return (
        dt.datetime.now(dt.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _load(path: pathlib.Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _save(path: pathlib.Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Replay benchmark for baseline vs advisory route alignment."
    )
    parser.add_argument("--job-ids", nargs="+", required=True)
    parser.add_argument(
        "--out-relpath",
        default="sandbox/logs/qc/benchmarks/qc_advisory_benchmark.v1.json",
    )
    args = parser.parse_args(argv[1:])

    root = _repo_root()
    rows = []
    baseline_hits = 0
    advisory_hits = 0

    for job_id in args.job_ids:
        qc_dir = root / "sandbox" / "logs" / job_id / "qc"
        decision = _load(qc_dir / "quality_decision.v1.json")
        report = _load(qc_dir / "qc_report.v1.json")
        advice = _load(qc_dir / "qc_route_advice.v1.json")
        if not isinstance(decision, dict) or not isinstance(report, dict):
            continue
        baseline_action = str(decision.get("decision", {}).get("action", "unknown"))
        policy_action = str(
            report.get("overall", {}).get("recommended_action", "unknown")
        )
        advisory_action = None
        if isinstance(advice, dict):
            raw = advice.get("advice", {})
            if isinstance(raw, dict) and isinstance(raw.get("recommended_action"), str):
                advisory_action = str(raw.get("recommended_action"))
        baseline_aligned = baseline_action == policy_action
        advisory_aligned = (
            advisory_action == policy_action if advisory_action is not None else False
        )
        baseline_hits += 1 if baseline_aligned else 0
        advisory_hits += 1 if advisory_aligned else 0
        rows.append(
            {
                "job_id": job_id,
                "baseline_action": baseline_action,
                "advisory_action": advisory_action,
                "policy_recommended_action": policy_action,
                "baseline_aligned": baseline_aligned,
                "advisory_aligned": advisory_aligned,
            }
        )

    total = len(rows)
    baseline_rate = float(baseline_hits / total) if total > 0 else 0.0
    advisory_rate = float(advisory_hits / total) if total > 0 else 0.0
    payload = {
        "version": "qc_advisory_benchmark.v1",
        "generated_at": _utc_now(),
        "summary": {
            "jobs_total": total,
            "baseline_alignment_rate": baseline_rate,
            "advisory_alignment_rate": advisory_rate,
            "alignment_lift": advisory_rate - baseline_rate,
        },
        "jobs": rows,
    }
    out_path = root / args.out_relpath
    _save(out_path, payload)
    print(str(out_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
