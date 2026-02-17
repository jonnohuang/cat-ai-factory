#!/usr/bin/env python3
"""
run_recast_benchmark.py

Runs deterministic recast quality scoring across a fixed benchmark suite.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys
import time
from typing import Any


def _repo_root() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parents[2]


def _load(path: pathlib.Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _write_json(path: pathlib.Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Run deterministic recast benchmark suite")
    parser.add_argument("--suite", required=True, help="Path to recast_benchmark_suite.v1 JSON")
    parser.add_argument("--out", help="Output benchmark report JSON path")
    args = parser.parse_args(argv[1:])

    root = _repo_root()
    suite_path = pathlib.Path(args.suite).resolve()
    suite = _load(suite_path)
    if suite.get("version") != "recast_benchmark_suite.v1":
        raise SystemExit(f"Unsupported suite version: {suite.get('version')}")

    suite_id = str(suite["suite_id"])
    bench_dir = root / "sandbox" / "logs" / "benchmarks" / suite_id
    bench_dir.mkdir(parents=True, exist_ok=True)

    case_results: list[dict[str, Any]] = []
    for case in suite.get("cases", []):
        case_id = str(case["case_id"])
        out_report = bench_dir / f"{case_id}.recast_quality_report.v1.json"

        cmd = [
            sys.executable,
            "-m",
            "repo.tools.score_recast_quality",
            "--job-id",
            str(case["job_id"]),
            "--video-relpath",
            str(case["video_relpath"]),
            "--out",
            str(out_report),
        ]
        if case.get("hero_image_relpath"):
            cmd.extend(["--hero-image-relpath", str(case["hero_image_relpath"])])
        if case.get("tracks_relpath"):
            cmd.extend(["--tracks-relpath", str(case["tracks_relpath"])])
        if case.get("subject_id"):
            cmd.extend(["--subject-id", str(case["subject_id"])])
        if case.get("loop_start_frame") is not None:
            cmd.extend(["--loop-start-frame", str(case["loop_start_frame"])])
        if case.get("loop_end_frame") is not None:
            cmd.extend(["--loop-end-frame", str(case["loop_end_frame"])])

        print("RUN:", " ".join(cmd))
        subprocess.check_call(cmd, cwd=str(root))

        report = _load(out_report)
        case_results.append(
            {
                "case_id": case_id,
                "job_id": str(case["job_id"]),
                "report_path": str(out_report.relative_to(root)),
                "overall_score": float(report["overall"]["score"]),
                "overall_pass": bool(report["overall"]["pass"]),
                "failed_metrics": list(report["overall"]["failed_metrics"]),
            }
        )

    scores = [float(c["overall_score"]) for c in case_results]
    pass_count = sum(1 for c in case_results if c["overall_pass"])
    summary = {
        "case_count": len(case_results),
        "pass_count": pass_count,
        "avg_overall_score": float(sum(scores) / len(scores)) if scores else 0.0,
        "all_pass": pass_count == len(case_results) and len(case_results) > 0,
    }

    report = {
        "version": "recast_benchmark_report.v1",
        "suite_id": suite_id,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "cases": case_results,
        "summary": summary,
    }
    out_path = pathlib.Path(args.out).resolve() if args.out else (bench_dir / "recast_benchmark_report.v1.json")
    _write_json(out_path, report)
    print("Wrote", out_path)
    print("summary.avg_overall_score", summary["avg_overall_score"])
    print("summary.all_pass", summary["all_pass"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

