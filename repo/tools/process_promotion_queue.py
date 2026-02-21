#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import sys
from typing import Any, Dict, List, Optional

try:
    from jsonschema import ValidationError, validate
except Exception:
    ValidationError = Exception
    validate = None


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


def _validated(
    payload: Dict[str, Any],
    *,
    schema: Dict[str, Any],
) -> bool:
    if validate is None:
        return True
    try:
        validate(instance=payload, schema=schema)
    except ValidationError:
        return False
    return True


def _quality_lift(candidate: Dict[str, Any]) -> tuple[float, float] | None:
    evidence = candidate.get("evidence")
    if not isinstance(evidence, dict):
        return None
    quality_lift = evidence.get("quality_lift")
    if not isinstance(quality_lift, dict):
        return None
    pass_rate_delta = quality_lift.get("pass_rate_delta")
    retry_count_delta = quality_lift.get("retry_count_delta")
    if not isinstance(pass_rate_delta, (float, int)):
        return None
    if not isinstance(retry_count_delta, (float, int)):
        return None
    return float(pass_rate_delta), float(retry_count_delta)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Process promotion_queue.v1 artifact into promotion registry."
    )
    parser.add_argument(
        "--queue-relpath", default="repo/shared/promotion_queue.v1.json"
    )
    parser.add_argument(
        "--registry-relpath", default="repo/shared/promotion_registry.v1.json"
    )
    parser.add_argument("--min-pass-rate-delta", type=float, default=0.0)
    parser.add_argument("--max-retry-count-delta", type=float, default=0.0)
    args = parser.parse_args(argv[1:])

    root = _repo_root()
    queue_path = root / args.queue_relpath
    registry_path = root / args.registry_relpath

    queue_data = _load(queue_path)
    if (
        not isinstance(queue_data, dict)
        or queue_data.get("version") != "promotion_queue.v1"
    ):
        # If queue missing or invalid, treat as empty but don't crash
        print(
            f"WARNING: Promotion queue not found or invalid: {args.queue_relpath}",
            file=sys.stderr,
        )
        queue_data = {
            "version": "promotion_queue.v1",
            "generated_at": _utc_now(),
            "queue": [],
        }

    queue_items = queue_data.get("queue", [])
    if not isinstance(queue_items, list):
        queue_items = []

    registry = _load(registry_path)
    if (
        not isinstance(registry, dict)
        or registry.get("version") != "promotion_registry.v1"
    ):
        registry = {
            "version": "promotion_registry.v1",
            "updated_at": _utc_now(),
            "approved": [],
        }

    approved = (
        registry.get("approved", [])
        if isinstance(registry.get("approved"), list)
        else []
    )
    approved_candidate_ids = {
        str(row.get("candidate_id"))
        for row in approved
        if isinstance(row, dict) and isinstance(row.get("candidate_id"), str)
    }

    # Schemas for validation
    queue_schema = (
        _load(root / "repo" / "shared" / "promotion_queue.v1.schema.json") or {}
    )
    candidate_schema = (
        _load(root / "repo" / "shared" / "promotion_candidate.v1.schema.json") or {}
    )

    processed = 0
    approved_count = 0
    rejected_count = 0
    skipped_count = 0
    outcomes: List[Dict[str, Any]] = []
    remaining_queue: List[Dict[str, Any]] = []

    for item in queue_items:
        if not isinstance(item, dict):
            continue

        # item is effectively a candidate structure embedded in queue
        candidate_id = str(item.get("candidate_id") or "")
        if not candidate_id:
            continue

        outcome: Dict[str, Any] = {
            "candidate_id": candidate_id,
        }

        # Check evidence
        quality_lift = _quality_lift(item)

        status = "unknown"
        if candidate_id in approved_candidate_ids:
            status = "skipped_duplicate"
            skipped_count += 1
            # duplicate means already processed, so we remove from queue?
            # or keep? Logic: if in registry, we can remove from queue.
        elif quality_lift is None:
            status = "rejected_missing_quality_lift"
            rejected_count += 1
        else:
            pass_rate_delta, retry_count_delta = quality_lift
            if pass_rate_delta < float(args.min_pass_rate_delta):
                status = "rejected_insufficient_pass_rate_delta"
                outcome["pass_rate_delta"] = pass_rate_delta
                rejected_count += 1
            elif retry_count_delta > float(args.max_retry_count_delta):
                status = "rejected_retry_delta_not_improved"
                outcome["retry_count_delta"] = retry_count_delta
                rejected_count += 1
            else:
                # Approve
                approved.append(
                    {
                        "candidate_id": candidate_id,
                        "candidate_relpath": f"embedded://{candidate_id}",
                        "applied_at": _utc_now(),
                        "proposal": item.get("proposal", {}),
                        "action_id": "auto-promotion-queue",
                        "decision_reason": "Met quality lift thresholds.",
                        "evidence_summary": {
                            "pass_rate_delta": pass_rate_delta,
                            "retry_count_delta": retry_count_delta,
                        },
                    }
                )
                approved_candidate_ids.add(candidate_id)
                status = "approved"
                approved_count += 1

        outcome["status"] = status
        outcomes.append(outcome)
        processed += 1

        # If rejected or approved, we consume it (don't add to remaining).
        # If skipped_duplicate, we also consume it (it's done).
        # So essentially we clear the processed items.
        # Only if we decided to *defer* would we keep it.
        # For now, all processed items are removed.

    # Update Registry
    registry["approved"] = approved
    registry["updated_at"] = _utc_now()
    _write(registry_path, registry)

    # Update Queue (Flush processed)
    queue_data["queue"] = remaining_queue
    queue_data["generated_at"] = _utc_now()
    _write(queue_path, queue_data)

    # Result Log
    out_path = root / "sandbox" / "logs" / "lab" / "promotion_queue_result.v1.json"
    _write(
        out_path,
        {
            "version": "promotion_queue_result.v1",
            "generated_at": _utc_now(),
            "processed_count": processed,
            "approved_count": approved_count,
            "rejected_count": rejected_count,
            "skipped_count": skipped_count,
            "outcomes": outcomes,
            "evidence_policy": {
                "min_pass_rate_delta": float(args.min_pass_rate_delta),
                "max_retry_count_delta": float(args.max_retry_count_delta),
            },
            "registry_relpath": args.registry_relpath,
            "queue_relpath": args.queue_relpath,
        },
    )
    print(
        f"Processed {processed} candidates. Approved {approved_count}. Wrote {out_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
