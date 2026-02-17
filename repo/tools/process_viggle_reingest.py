#!/usr/bin/env python3
"""
process_viggle_reingest.py

Processes a viggle_reingest_pointer.v1 inbox artifact and updates
dist_artifacts lifecycle state deterministically.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import shutil
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Process Viggle re-ingest pointer and update lifecycle")
    parser.add_argument("--pointer", required=True, help="Path to viggle-reingest-*.json")
    args = parser.parse_args()

    root = _repo_root()
    pointer_path = pathlib.Path(args.pointer).resolve()
    pointer = _load(pointer_path)
    if pointer.get("version") != "viggle_reingest_pointer.v1":
        raise SystemExit(f"Unsupported pointer version: {pointer.get('version')}")

    job_id = str(pointer["job_id"])
    result_rel = str(pointer["result_video_relpath"])
    result_path = root / result_rel
    if not result_path.exists():
        raise SystemExit(f"Pointer target video not found: {result_path}")

    pack_root = root / "sandbox" / "dist_artifacts" / job_id / "viggle_pack"
    pack_root.mkdir(parents=True, exist_ok=True)
    reingest_dir = pack_root / "reingest"
    reingest_dir.mkdir(parents=True, exist_ok=True)
    copied_video = reingest_dir / result_path.name
    shutil.copy2(result_path, copied_video)

    now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    lifecycle = {
        "version": "external_recast_lifecycle.v1",
        "job_id": job_id,
        "state": "VIGGLE_DONE",
        "updated_at": now_iso,
        "notes": "External recast result ingested from inbox pointer.",
        "reingest_pointer": f"sandbox/inbox/{pointer_path.name}",
        "reingest_result_video": result_rel,
    }
    _write_json(pack_root / "external_recast_lifecycle.v1.json", lifecycle)

    print("Wrote", pack_root / "external_recast_lifecycle.v1.json")
    print("Copied", copied_video)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

