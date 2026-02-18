#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
from typing import Any, Dict, List, Optional


def _repo_root() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parents[2]


def _utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _kebab(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def _load_json(path: pathlib.Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _write_json(path: pathlib.Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _safe_rel(path: pathlib.Path, root: pathlib.Path) -> str:
    return str(path.resolve().relative_to(root.resolve())).replace("\\", "/")


def _run(cmd: List[str], cwd: pathlib.Path) -> None:
    proc = subprocess.run(cmd, cwd=str(cwd), text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    print(proc.stdout, end="")
    if proc.returncode != 0:
        raise RuntimeError(f"command failed ({proc.returncode}): {' '.join(cmd)}")


def _find_core_contract(out_dir: pathlib.Path, analysis_id: str, suffix: str) -> Optional[pathlib.Path]:
    p = out_dir / f"{analysis_id}.{suffix}.json"
    return p if p.exists() else None


def _extract_aliases(name: str) -> List[str]:
    base = _kebab(pathlib.Path(name).stem)
    tokens = [t for t in base.split("-") if t]
    aliases = [base]
    if len(tokens) >= 2:
        aliases.append(" ".join(tokens))
    return sorted(set([a for a in aliases if a]))


def _collect_sample_refs(analysis: Dict[str, Any]) -> Dict[str, List[str]]:
    pattern = analysis.get("pattern") if isinstance(analysis.get("pattern"), dict) else {}
    visual = pattern.get("visual_signature") if isinstance(pattern.get("visual_signature"), dict) else {}
    choreography = pattern.get("choreography") if isinstance(pattern.get("choreography"), dict) else {}
    hooks: Dict[str, List[str]] = {
        "hero_refs": [],
        "costume_refs": [],
        "background_refs": [],
        "audio_refs": [],
        "style_tone_refs": [],
    }
    tags = analysis.get("tags")
    if isinstance(tags, list):
        for t in tags:
            if not isinstance(t, str):
                continue
            tl = t.lower()
            if "mochi" in tl or "cat" in tl:
                hooks["hero_refs"].append(t)
            if "costume" in tl:
                hooks["costume_refs"].append(t)
            if "stage" in tl or "background" in tl:
                hooks["background_refs"].append(t)
            if "style" in tl or "tone" in tl or "vibe" in tl:
                hooks["style_tone_refs"].append(t)
    bg = visual.get("background", {}) if isinstance(visual, dict) else {}
    if isinstance(bg, dict):
        for key in ("scene_type", "lighting", "color_theme"):
            v = bg.get(key)
            if isinstance(v, str) and v:
                hooks["background_refs"].append(v)
    motion = choreography.get("motion_style") if isinstance(choreography, dict) else None
    if isinstance(motion, str) and motion:
        hooks["style_tone_refs"].append(motion)

    return {k: sorted(set(v)) for k, v in hooks.items()}


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Lab-first deterministic sample ingest for incoming demo videos.")
    parser.add_argument("--incoming-dir", default="sandbox/assets/demo/incoming")
    parser.add_argument("--processed-dir", default="sandbox/assets/demo/processed")
    parser.add_argument("--canon-dir", default="repo/canon/demo_analyses")
    parser.add_argument("--index", default="repo/canon/demo_analyses/video_analysis_index.v1.json")
    parser.add_argument("--quality-target-relpath", default="repo/examples/quality_target.motion_strict.v1.example.json")
    parser.add_argument("--continuity-pack-relpath", default="repo/examples/episode_continuity_pack.v1.example.json")
    parser.add_argument("--storyboard-relpath", default="repo/examples/storyboard.v1.example.json")
    parser.add_argument("--no-move-processed", action="store_true")
    args = parser.parse_args(argv[1:])

    root = _repo_root()
    incoming_dir = (root / args.incoming_dir).resolve()
    processed_dir = (root / args.processed_dir).resolve()
    canon_dir = (root / args.canon_dir).resolve()
    index_path = (root / args.index).resolve()

    incoming_dir.mkdir(parents=True, exist_ok=True)
    processed_dir.mkdir(parents=True, exist_ok=True)
    canon_dir.mkdir(parents=True, exist_ok=True)

    videos = sorted(
        p for p in incoming_dir.iterdir()
        if p.is_file() and p.suffix.lower() in {".mp4", ".mov", ".mkv", ".webm"}
    )
    if not videos:
        print("INFO ingest_demo_samples no incoming videos")
        return 0

    summaries: List[Dict[str, Any]] = []
    for video_path in videos:
        analysis_id = _kebab(video_path.stem)
        analysis_out = canon_dir / f"{analysis_id}.video_analysis.v1.json"

        _run(
            [
                sys.executable,
                "-m",
                "repo.tools.analyze_video",
                "--input",
                str(video_path),
                "--output",
                str(analysis_out),
                "--analysis-id",
                analysis_id,
                "--index",
                str(index_path),
                "--lane-hint",
                "template_remix",
                "--tag",
                analysis_id,
                "--overwrite",
            ],
            cwd=root,
        )

        _run(
            [
                sys.executable,
                "-m",
                "repo.tools.build_analyzer_core_pack",
                "--input",
                str(video_path),
                "--analysis-id",
                analysis_id,
                "--out-dir",
                str(canon_dir),
                "--overwrite",
            ],
            cwd=root,
        )

        analysis = _load_json(analysis_out) or {}
        refs = _collect_sample_refs(analysis)

        beat = _find_core_contract(canon_dir, analysis_id, "beat_grid.v1")
        pose = _find_core_contract(canon_dir, analysis_id, "pose_checkpoints.v1")
        keyframe = _find_core_contract(canon_dir, analysis_id, "keyframe_checkpoints.v1")
        reverse = _find_core_contract(canon_dir, analysis_id, "caf.video_reverse_prompt.v1")
        frame_labels = _find_core_contract(canon_dir, analysis_id, "frame_labels.v1")
        seg_plan = _find_core_contract(canon_dir, analysis_id, "segment_stitch_plan.v1")

        manifest = {
            "version": "sample_ingest_manifest.v1",
            "sample_id": analysis_id,
            "analysis_id": analysis_id,
            "generated_at": _utc_now(),
            "source": {
                "video_relpath": _safe_rel(video_path, root),
                "reference_aliases": _extract_aliases(video_path.name),
            },
            "contracts": {
                "video_analysis_relpath": _safe_rel(analysis_out, root),
                "reverse_prompt_relpath": _safe_rel(reverse, root) if reverse else None,
                "beat_grid_relpath": _safe_rel(beat, root) if beat else None,
                "pose_checkpoints_relpath": _safe_rel(pose, root) if pose else None,
                "keyframe_checkpoints_relpath": _safe_rel(keyframe, root) if keyframe else None,
                "segment_stitch_plan_relpath": _safe_rel(seg_plan, root) if seg_plan else None,
                "quality_target_relpath": args.quality_target_relpath,
                "continuity_pack_relpath": args.continuity_pack_relpath,
                "storyboard_relpath": args.storyboard_relpath,
                "frame_labels_relpath": _safe_rel(frame_labels, root) if frame_labels else None,
            },
            "assets": {
                "hero_refs": refs.get("hero_refs", []),
                "costume_refs": refs.get("costume_refs", []),
                "background_refs": refs.get("background_refs", []),
                "audio_refs": refs.get("audio_refs", []),
                "style_tone_refs": refs.get("style_tone_refs", []),
            },
            "provenance": {
                "ingest_tool": "repo.tools.ingest_demo_samples",
                "tool_versions": {
                    "analyze_video": "video_analysis.v1",
                    "analyzer_core_pack": "beat_grid.v1+pose_checkpoints.v1+keyframe_checkpoints.v1+segment_stitch_plan.v1",
                },
                "confidence": 0.8,
            },
        }
        manifest_path = canon_dir / f"{analysis_id}.sample_ingest_manifest.v1.json"
        _write_json(manifest_path, manifest)

        if not args.no_move_processed:
            dst = processed_dir / video_path.name
            if dst.exists():
                dst = processed_dir / f"{analysis_id}-{int(dt.datetime.now().timestamp())}{video_path.suffix.lower()}"
            shutil.move(str(video_path), str(dst))
            manifest["source"]["video_relpath"] = _safe_rel(dst, root)
            _write_json(manifest_path, manifest)

        summaries.append(
            {
                "analysis_id": analysis_id,
                "manifest_relpath": _safe_rel(manifest_path, root),
                "video_analysis_relpath": _safe_rel(analysis_out, root),
            }
        )
        print(f"Wrote {manifest_path}")

    summary_path = root / "sandbox" / "logs" / "lab" / "sample_ingest_summary.v1.json"
    _write_json(
        summary_path,
        {
            "version": "sample_ingest_summary.v1",
            "generated_at": _utc_now(),
            "incoming_dir": _safe_rel(incoming_dir, root),
            "processed_dir": _safe_rel(processed_dir, root),
            "samples": summaries,
        },
    )
    print(f"Wrote {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
