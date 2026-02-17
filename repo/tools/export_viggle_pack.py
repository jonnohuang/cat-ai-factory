#!/usr/bin/env python3
"""
export_viggle_pack.py

Exports deterministic external HITL recast pack artifacts under:
  sandbox/dist_artifacts/<job_id>/viggle_pack/**
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


def _write_text(path: pathlib.Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _resolve_asset(rel_or_abs: str, sandbox_root: pathlib.Path) -> pathlib.Path:
    p = pathlib.Path(rel_or_abs)
    if p.is_absolute():
        return p
    if rel_or_abs.startswith("sandbox/"):
        return sandbox_root.parent / rel_or_abs
    return sandbox_root / rel_or_abs


def main() -> int:
    parser = argparse.ArgumentParser(description="Export viggle pack under dist_artifacts")
    parser.add_argument("--job", required=True, help="Path to job JSON")
    parser.add_argument("--hero-image", required=True, help="Hero image asset path (relative to sandbox or sandbox/*)")
    parser.add_argument("--motion-video", required=True, help="Motion source video asset path (relative to sandbox or sandbox/*)")
    parser.add_argument("--prompt", required=True, help="Prompt text for external recast tool")
    args = parser.parse_args()

    root = _repo_root()
    sandbox = root / "sandbox"
    job = _load(pathlib.Path(args.job).resolve())
    job_id = str(job["job_id"])

    hero_src = _resolve_asset(args.hero_image, sandbox)
    motion_src = _resolve_asset(args.motion_video, sandbox)
    if not hero_src.exists():
        raise SystemExit(f"Hero image not found: {hero_src}")
    if not motion_src.exists():
        raise SystemExit(f"Motion video not found: {motion_src}")

    pack_root = sandbox / "dist_artifacts" / job_id / "viggle_pack"
    pack_root.mkdir(parents=True, exist_ok=True)
    hero_dst = pack_root / f"hero{hero_src.suffix.lower()}"
    motion_dst = pack_root / f"motion{motion_src.suffix.lower()}"
    prompt_path = pack_root / "prompt.txt"
    instructions_path = pack_root / "instructions.md"

    shutil.copy2(hero_src, hero_dst)
    shutil.copy2(motion_src, motion_dst)
    _write_text(prompt_path, args.prompt.strip() + "\n")
    _write_text(
        instructions_path,
        (
            "External HITL recast instructions\n"
            "1) Upload hero.* and motion.* to Viggle\n"
            "2) Use prompt.txt content\n"
            "3) Export result video\n"
            "4) Place result under sandbox/inbox/viggle_results/<job_id>/viggle.mp4\n"
            "5) Create re-ingest pointer via repo/tools/create_viggle_reingest_pointer.py\n"
        ),
    )

    ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    pack_manifest = {
        "version": "viggle_pack.v1",
        "job_id": job_id,
        "pack_root": f"sandbox/dist_artifacts/{job_id}/viggle_pack",
        "hero_image": f"sandbox/dist_artifacts/{job_id}/viggle_pack/{hero_dst.name}",
        "motion_video": f"sandbox/dist_artifacts/{job_id}/viggle_pack/{motion_dst.name}",
        "prompt_file": f"sandbox/dist_artifacts/{job_id}/viggle_pack/prompt.txt",
        "instructions_file": f"sandbox/dist_artifacts/{job_id}/viggle_pack/instructions.md",
        "created_at": ts,
    }
    lifecycle = {
        "version": "external_recast_lifecycle.v1",
        "job_id": job_id,
        "state": "VIGGLE_EXPORTED",
        "updated_at": ts,
        "notes": "Viggle pack exported and ready for external HITL recast.",
        "reingest_pointer": None,
        "reingest_result_video": None,
    }
    _write_json(pack_root / "viggle_pack.v1.json", pack_manifest)
    _write_json(pack_root / "external_recast_lifecycle.v1.json", lifecycle)

    print("Wrote", pack_root / "viggle_pack.v1.json")
    print("Wrote", pack_root / "external_recast_lifecycle.v1.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

