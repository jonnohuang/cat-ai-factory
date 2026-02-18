#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import sys
from typing import Any, Dict, List, Optional


def _repo_root() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parents[2]


def _utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _load(path: pathlib.Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _write(path: pathlib.Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _rel(path: pathlib.Path, root: pathlib.Path) -> str:
    return str(path.resolve().relative_to(root.resolve())).replace("\\", "/")


def _iter_actions(inbox_dir: pathlib.Path) -> List[pathlib.Path]:
    return sorted([p for p in inbox_dir.glob("*.json") if p.is_file()])


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Process promotion_action.v1 inbox artifacts into promotion registry.")
    parser.add_argument("--inbox-dir", default="sandbox/inbox")
    parser.add_argument("--registry-relpath", default="repo/shared/promotion_registry.v1.json")
    parser.add_argument("--archive-dir", default="sandbox/logs/lab/promotion_actions")
    args = parser.parse_args(argv[1:])

    root = _repo_root()
    inbox_dir = root / args.inbox_dir
    registry_path = root / args.registry_relpath
    archive_dir = root / args.archive_dir

    inbox_dir.mkdir(parents=True, exist_ok=True)
    archive_dir.mkdir(parents=True, exist_ok=True)

    registry = _load(registry_path)
    if not isinstance(registry, dict) or registry.get("version") != "promotion_registry.v1":
        registry = {"version": "promotion_registry.v1", "updated_at": _utc_now(), "approved": []}

    approved = registry.get("approved", []) if isinstance(registry.get("approved"), list) else []

    processed = 0
    for action_path in _iter_actions(inbox_dir):
        action = _load(action_path)
        if not isinstance(action, dict) or action.get("version") != "promotion_action.v1":
            continue
        candidate_rel = action.get("candidate_relpath")
        decision = action.get("decision")
        if not isinstance(candidate_rel, str) or not candidate_rel.startswith("sandbox/"):
            continue
        if decision not in {"approve", "reject"}:
            continue

        candidate_path = root / candidate_rel
        candidate = _load(candidate_path)
        if not isinstance(candidate, dict) or candidate.get("version") != "promotion_candidate.v1":
            continue

        if decision == "approve":
            approved.append(
                {
                    "candidate_id": candidate.get("candidate_id"),
                    "candidate_relpath": candidate_rel,
                    "applied_at": _utc_now(),
                    "proposal": candidate.get("proposal", {}),
                }
            )

        archive_path = archive_dir / action_path.name
        action_path.replace(archive_path)
        processed += 1

    registry["approved"] = approved
    registry["updated_at"] = _utc_now()
    _write(registry_path, registry)

    out_path = root / "sandbox" / "logs" / "lab" / "promotion_queue_result.v1.json"
    _write(
        out_path,
        {
            "version": "promotion_queue_result.v1",
            "generated_at": _utc_now(),
            "processed_actions": processed,
            "registry_relpath": _rel(registry_path, root),
        },
    )
    print(f"Wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
