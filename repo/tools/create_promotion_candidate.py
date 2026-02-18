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


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Create promotion_candidate.v1 from lab summary + sample ingest manifest")
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--sample-manifest-relpath", required=True)
    parser.add_argument("--pass-rate-delta", type=float, default=0.0)
    parser.add_argument("--retry-count-delta", type=float, default=0.0)
    args = parser.parse_args(argv[1:])

    root = _repo_root()
    summary_path = root / "sandbox" / "logs" / args.job_id / "qc" / "lab_qc_loop_summary.v1.json"
    sample_manifest_path = root / args.sample_manifest_relpath
    summary = _load(summary_path)
    manifest = _load(sample_manifest_path)
    if not isinstance(summary, dict):
        print(f"ERROR: missing lab summary: {summary_path}", file=sys.stderr)
        return 1
    if not isinstance(manifest, dict) or manifest.get("version") != "sample_ingest_manifest.v1":
        print(f"ERROR: invalid sample manifest: {sample_manifest_path}", file=sys.stderr)
        return 1

    candidate_id = f"{args.job_id}-{manifest.get('sample_id', 'sample')}-candidate"
    proposal = {
        "contract_pointers": {
            "motion_contract": {
                "relpath": manifest.get("contracts", {}).get("pose_checkpoints_relpath"),
                "contract_version": "pose_checkpoints.v1",
            },
            "quality_target": {"relpath": manifest.get("contracts", {}).get("quality_target_relpath")},
            "continuity_pack": {"relpath": manifest.get("contracts", {}).get("continuity_pack_relpath")},
            "segment_stitch": {
                "plan_relpath": manifest.get("contracts", {}).get("segment_stitch_plan_relpath"),
                "enabled": True,
            },
        },
        "workflow_preset": {
            "workflow_id": "caf_dance_loop_v1",
            "preset_id": "motion_safe_v1",
        },
        "qc_policy_relpath": "repo/shared/qc_policy.v1.json",
    }

    payload = {
        "version": "promotion_candidate.v1",
        "candidate_id": candidate_id,
        "generated_at": _utc_now(),
        "source": {
            "job_id": args.job_id,
            "summary_relpath": _rel(summary_path, root),
        },
        "proposal": proposal,
        "evidence": {
            "quality_lift": {
                "pass_rate_delta": float(args.pass_rate_delta),
                "retry_count_delta": float(args.retry_count_delta),
            }
        },
    }

    out_path = root / "sandbox" / "logs" / "lab" / "promotions" / f"{candidate_id}.promotion_candidate.v1.json"
    _write(out_path, payload)
    print(f"Wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
