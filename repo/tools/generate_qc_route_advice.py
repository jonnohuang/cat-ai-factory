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


def _load_json(path: pathlib.Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _save_json(path: pathlib.Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _safe_rel(path: pathlib.Path, root: pathlib.Path) -> Optional[str]:
    try:
        return str(path.resolve().relative_to(root.resolve())).replace("\\", "/")
    except Exception:
        return None


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Emit non-authoritative qc_route_advice.v1 from qc_report"
    )
    parser.add_argument("--job-id", required=True)
    args = parser.parse_args(argv[1:])

    root = _repo_root()
    qc_dir = root / "sandbox" / "logs" / args.job_id / "qc"
    report_path = qc_dir / "qc_report.v1.json"
    out_path = qc_dir / "qc_route_advice.v1.json"
    report = _load_json(report_path)
    if not isinstance(report, dict):
        print("ERROR: missing qc_report.v1", file=sys.stderr)
        return 1

    recommended_action = str(
        report.get("overall", {}).get("recommended_action", "escalate_hitl")
    )
    failed = report.get("overall", {}).get("failed_gate_ids", [])
    reason = "policy-aligned recommendation from normalized gate failures"
    if isinstance(failed, list) and failed:
        reason = f"{reason}: {', '.join(str(x) for x in failed[:3])}"

    payload = {
        "version": "qc_route_advice.v1",
        "job_id": args.job_id,
        "generated_at": _utc_now(),
        "source": {
            "mode": "lab_advisory",
            "qc_report_relpath": _safe_rel(report_path, root),
        },
        "advice": {
            "recommended_action": recommended_action,
            "reason": reason,
        },
    }
    _save_json(out_path, payload)
    print(str(out_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
