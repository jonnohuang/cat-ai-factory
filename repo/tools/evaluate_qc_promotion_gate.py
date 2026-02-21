#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import sys
from typing import Any, Dict


def _repo_root() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parents[2]


def _utc_now() -> str:
    return (
        dt.datetime.now(dt.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _load(path: pathlib.Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"expected object: {path}")
    return data


def _save(path: pathlib.Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _rel(path: pathlib.Path, root: pathlib.Path) -> str:
    return str(path.resolve().relative_to(root.resolve())).replace("\\", "/")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate benchmark against promotion gate thresholds."
    )
    parser.add_argument("--benchmark-relpath", required=True)
    parser.add_argument(
        "--promotion-gate-relpath", default="repo/shared/qc_promotion_gate.v1.json"
    )
    parser.add_argument(
        "--out-relpath",
        default="sandbox/logs/qc/benchmarks/qc_promotion_decision.v1.json",
    )
    args = parser.parse_args(argv[1:])

    root = _repo_root()
    bench_path = root / args.benchmark_relpath
    gate_path = root / args.promotion_gate_relpath
    bench = _load(bench_path)
    gate = _load(gate_path)

    lift = float(bench.get("summary", {}).get("alignment_lift", 0.0))
    thresholds = gate.get("thresholds", {})
    min_lift = float(thresholds.get("min_alignment_lift", 0.0))
    max_negative = float(thresholds.get("max_negative_lift", -0.05))

    promote = lift >= min_lift and lift >= max_negative
    reason = (
        "Alignment lift meets configured threshold."
        if promote
        else "Alignment lift below promotion gate."
    )
    payload = {
        "version": "qc_promotion_decision.v1",
        "generated_at": _utc_now(),
        "inputs": {
            "benchmark_relpath": _rel(bench_path, root),
            "promotion_gate_relpath": _rel(gate_path, root),
            "alignment_lift": lift,
        },
        "decision": {
            "promote": promote,
            "reason": reason,
        },
    }
    out_path = root / args.out_relpath
    _save(out_path, payload)
    print(str(out_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
