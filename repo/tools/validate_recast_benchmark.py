#!/usr/bin/env python3
"""
validate_recast_benchmark.py

Validates recast benchmark suite/report schemas and consistency.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Any

try:
    from jsonschema import ValidationError, validate
except Exception:
    print("ERROR: jsonschema not installed in active environment.", file=sys.stderr)
    raise SystemExit(1)


def _repo_root() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parents[2]


def _load(path: pathlib.Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Validate recast benchmark suite/report"
    )
    parser.add_argument(
        "--suite", required=True, help="Path to recast_benchmark_suite.v1 JSON"
    )
    parser.add_argument(
        "--report", required=True, help="Path to recast_benchmark_report.v1 JSON"
    )
    args = parser.parse_args(argv[1:])

    root = _repo_root()
    suite_schema = _load(
        root / "repo" / "shared" / "recast_benchmark_suite.v1.schema.json"
    )
    report_schema = _load(
        root / "repo" / "shared" / "recast_benchmark_report.v1.schema.json"
    )
    suite = _load(pathlib.Path(args.suite).resolve())
    report = _load(pathlib.Path(args.report).resolve())

    errors: list[str] = []
    try:
        validate(instance=suite, schema=suite_schema)
    except ValidationError as ex:
        errors.append(f"SCHEMA suite: {ex.message}")
    try:
        validate(instance=report, schema=report_schema)
    except ValidationError as ex:
        errors.append(f"SCHEMA report: {ex.message}")

    if suite.get("suite_id") != report.get("suite_id"):
        errors.append("suite_id mismatch between suite and report")

    suite_case_ids = {c["case_id"] for c in suite.get("cases", [])}
    report_case_ids = {c["case_id"] for c in report.get("cases", [])}
    if suite_case_ids != report_case_ids:
        errors.append(
            f"case_id mismatch between suite/report: suite={sorted(suite_case_ids)} report={sorted(report_case_ids)}"
        )

    for c in report.get("cases", []):
        report_path = root / c["report_path"]
        if not report_path.exists():
            errors.append(f"missing case report artifact: {report_path}")

    summary = report.get("summary", {})
    if int(summary.get("case_count", -1)) != len(report.get("cases", [])):
        errors.append("summary.case_count does not match report.cases length")
    pass_count = sum(1 for c in report.get("cases", []) if c.get("overall_pass"))
    if int(summary.get("pass_count", -1)) != pass_count:
        errors.append("summary.pass_count does not match count of overall_pass=true")

    if errors:
        print("INVALID: recast benchmark", file=sys.stderr)
        for err in errors:
            print(f"- {err}", file=sys.stderr)
        return 1

    print("OK: recast benchmark")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
