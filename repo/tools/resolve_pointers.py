#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Any

# Add repo root to sys.path
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from repo.services.planner.pointer_resolver import PointerResolver


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Resolve pointers for a brief")
    parser.add_argument("--job-id", required=True, help="Job ID")
    parser.add_argument(
        "--brief", required=True, help="Path to brief JSON or raw JSON string"
    )
    parser.add_argument(
        "--policy", default="prefer_canon_strict_motion", help="Resolution policy"
    )
    parser.add_argument("--out", help="Output path for pointer_resolution.v1.json")
    args = parser.parse_args(argv[1:])

    brief_data: dict[str, Any] = {}
    if args.brief.strip().startswith("{"):
        try:
            brief_data = json.loads(args.brief)
        except json.JSONDecodeError as e:
            print(f"ERROR: invalid brief JSON string: {e}", file=sys.stderr)
            return 1
    else:
        path = pathlib.Path(args.brief)
        if path.exists():
            brief_data = json.loads(path.read_text(encoding="utf-8"))
        else:
            print(f"ERROR: brief file not found: {args.brief}", file=sys.stderr)
            return 1

    resolver = PointerResolver(_REPO_ROOT)
    resolution = resolver.resolve(args.job_id, brief_data, args.policy)

    output = json.dumps(resolution, indent=2)
    if args.out:
        pathlib.Path(args.out).write_text(output + "\n", encoding="utf-8")
        print(f"Wrote resolution to {args.out}")
    else:
        print(output)

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
