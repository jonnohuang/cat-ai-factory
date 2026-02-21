#!/usr/bin/env python3
"""
create_viggle_reingest_pointer.py

Creates an explicit inbox metadata pointer for external Viggle output:
  sandbox/inbox/viggle-reingest-<job_id>-<nonce>.json
"""

from __future__ import annotations

import argparse
import json
import pathlib
import time
from typing import Any


def _repo_root() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parents[2]


def _write_json(path: pathlib.Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create external recast re-ingest pointer in inbox"
    )
    parser.add_argument("--job-id", required=True, help="Job ID")
    parser.add_argument(
        "--result-video-relpath",
        required=True,
        help="Result video relpath like sandbox/inbox/viggle_results/<job_id>/viggle.mp4",
    )
    parser.add_argument("--notes", default="", help="Optional notes")
    args = parser.parse_args()

    root = _repo_root()
    inbox = root / "sandbox" / "inbox"
    now_epoch = int(time.time())
    now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    pointer = {
        "version": "viggle_reingest_pointer.v1",
        "job_id": args.job_id,
        "source": "viggle",
        "result_video_relpath": args.result_video_relpath,
        "submitted_at": now_iso,
        "notes": args.notes,
    }
    out_path = inbox / f"viggle-reingest-{args.job_id}-{now_epoch}.json"
    _write_json(out_path, pointer)
    print("Wrote", out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
