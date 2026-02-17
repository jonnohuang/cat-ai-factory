#!/usr/bin/env python3
from __future__ import annotations

import argparse
import glob
import json
import os
import pathlib
import re
import subprocess
import sys
from typing import List, Optional


def _repo_root() -> pathlib.Path:
    # repo/tools/plan_and_run.py -> <repo_root>
    return pathlib.Path(__file__).resolve().parents[2]


def _latest_job_path(out_dir: str) -> Optional[str]:
    paths = sorted(glob.glob(os.path.join(out_dir, "*.job.json")))
    if not paths:
        return None
    paths.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    return paths[0]


def _extract_written_job_path(stdout: str) -> Optional[str]:
    # planner_cli prints: "Wrote <path>"
    for line in reversed(stdout.splitlines()):
        match = re.match(r"^Wrote\s+(.+\.job\.json)\s*$", line.strip())
        if match:
            return match.group(1)
    return None


def _run(cmd: List[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, text=True, capture_output=True, check=False)


def _job_uses_demo_background(job_path: str) -> bool:
    try:
        data = json.loads(pathlib.Path(job_path).read_text(encoding="utf-8"))
    except Exception:
        return False
    render = data.get("render")
    if not isinstance(render, dict):
        return False
    bg = render.get("background_asset")
    if not isinstance(bg, str):
        return False
    s = bg.strip().lower()
    return s.startswith("assets/demo/") or s.startswith("sandbox/assets/demo/")


def _build_duet_job(source_job_path: str, out_dir: str) -> Optional[str]:
    src_path = pathlib.Path(source_job_path)
    if not src_path.exists():
        print(f"ERROR: source job not found: {source_job_path}", file=sys.stderr)
        return None

    try:
        src = json.loads(src_path.read_text(encoding="utf-8"))
    except Exception as ex:
        print(f"ERROR: cannot parse source job json: {ex}", file=sys.stderr)
        return None

    src_job_id = str(src.get("job_id", "")).strip()
    if not src_job_id:
        print("ERROR: source job missing job_id", file=sys.stderr)
        return None

    fg_asset = f"assets/generated/{src_job_id}/veo-0001.mp4"
    fg_abs = _repo_root() / "sandbox" / fg_asset
    if not fg_abs.exists():
        print(f"ERROR: expected Veo asset missing: {fg_abs}", file=sys.stderr)
        return None

    video = src.get("video") if isinstance(src.get("video"), dict) else {}
    fps = int(video.get("fps", 30))
    resolution = str(video.get("resolution", "1080x1920"))
    length_seconds = int(video.get("length_seconds", 10))
    if length_seconds < 10:
        length_seconds = 10

    duet_job_id = f"{src_job_id}-duet"
    duet = {
        "job_id": duet_job_id,
        "date": str(src.get("date", "2024-05-15")),
        "lane": "template_remix",
        "niche": str(src.get("niche", "cat_dance_comedy")),
        "video": {
            "length_seconds": length_seconds,
            "aspect_ratio": "9:16",
            "fps": fps,
            "resolution": resolution,
        },
        "script": {
            "hook": "Mochi joins the group dance loop.",
            "voiceover": "Mochi drops into the party and dances with the crew in a duet-style remix.",
            "ending": "Loop ready.",
        },
        "shots": [
            {"t": 0, "visual": "group dance", "action": "group starts", "caption": "Dance squad"},
            {"t": 1, "visual": "mochi joins", "action": "duet starts", "caption": "Mochi enters"},
            {"t": 2, "visual": "duet groove", "action": "sync moves", "caption": "On beat"},
            {"t": 3, "visual": "duet groove", "action": "comedy move", "caption": "Funny move"},
            {"t": 4, "visual": "duet groove", "action": "energy up", "caption": "Keep dancing"},
            {"t": 5, "visual": "duet ending", "action": "loop finish", "caption": "Replay"},
        ],
        "captions": [
            "Mochi joins the crew!",
            "Duet mode on!",
            "Dance loop remix!",
            "Replay this one!",
        ],
        "hashtags": ["#MochiDance", "#CatDance", "#DanceLoop"],
        "render": {
            "background_asset": fg_asset,
            "subtitle_style": "big_bottom",
            "output_basename": f"{duet_job_id}_overlay",
        },
        "audio": {
            "audio_asset": "assets/audio/beds/caf_bed_dance_loop_01.wav",
        },
        "template": {
            "template_id": "dance_duet_mochi",
            "params": {"duration_seconds": length_seconds},
        },
    }

    out_path = pathlib.Path(out_dir) / f"{duet_job_id}.job.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(duet, indent=2), encoding="utf-8")
    return str(out_path)


def _build_motion_bootstrap_job(
    source_job_path: str, out_dir: str, motion_source_asset: str
) -> Optional[str]:
    src_path = pathlib.Path(source_job_path)
    if not src_path.exists():
        print(f"ERROR: source job not found: {source_job_path}", file=sys.stderr)
        return None
    try:
        src = json.loads(src_path.read_text(encoding="utf-8"))
    except Exception as ex:
        print(f"ERROR: cannot parse source job json: {ex}", file=sys.stderr)
        return None

    src_job_id = str(src.get("job_id", "")).strip()
    if not src_job_id:
        print("ERROR: source job missing job_id", file=sys.stderr)
        return None

    fg_asset = ""
    render = src.get("render")
    if isinstance(render, dict):
        bg_asset = render.get("background_asset")
        if isinstance(bg_asset, str) and bg_asset.strip().endswith(".mp4"):
            fg_asset = bg_asset.strip()
    if not fg_asset:
        fg_asset = f"assets/generated/{src_job_id}/veo-0001.mp4"
    fg_abs = _repo_root() / "sandbox" / fg_asset
    if not fg_abs.exists():
        print(f"ERROR: expected foreground Veo asset missing: {fg_abs}", file=sys.stderr)
        return None

    bg_abs = _repo_root() / "sandbox" / motion_source_asset
    if not bg_abs.exists():
        print(f"ERROR: motion source asset missing: {bg_abs}", file=sys.stderr)
        return None

    video = src.get("video") if isinstance(src.get("video"), dict) else {}
    fps = int(video.get("fps", 30))
    resolution = str(video.get("resolution", "1080x1920"))
    length_seconds = int(video.get("length_seconds", 18))
    if length_seconds < 10:
        length_seconds = 10

    job_id = f"{src_job_id}-bootstrap"
    remix = {
        "job_id": job_id,
        "date": str(src.get("date", "2024-05-15")),
        "lane": "template_remix",
        "niche": str(src.get("niche", "cat_dance_comedy")),
        "video": {
            "length_seconds": length_seconds,
            "aspect_ratio": "9:16",
            "fps": fps,
            "resolution": resolution,
        },
        "script": {
            "hook": "Mochi remixes a dance sequence using source choreography.",
            "voiceover": "Motion-source bootstrap: keep the groove from the base dance while compositing Mochi for cat-hero output.",
            "ending": "Loop ready.",
        },
        "shots": [
            {"t": 0, "visual": "motion source dance", "action": "start on beat", "caption": "Groove starts"},
            {"t": 2, "visual": "mochi overlay", "action": "step and paw pop", "caption": "Mochi joins"},
            {"t": 5, "visual": "sync rhythm", "action": "choreo in cadence", "caption": "On beat"},
            {"t": 8, "visual": "dance continuation", "action": "looping moves", "caption": "Keep dancing"},
            {"t": 12, "visual": "end pose", "action": "return to start pose", "caption": "Loop it"},
            {"t": 16, "visual": "hold loop seam", "action": "seamless reset", "caption": "Replay"},
        ],
        "captions": [
            "Motion-source bootstrap",
            "Mochi on the beat",
            "Dance loop remix",
            "Replay this groove",
        ],
        "hashtags": ["#MochiDance", "#CatDance", "#TemplateRemix", "#DanceLoop"],
        "render": {
            "background_asset": motion_source_asset,
            "subtitle_style": "big_bottom",
            "output_basename": f"{job_id}_motion_bootstrap",
        },
        "audio": {
            "audio_asset": "assets/audio/beds/caf_bed_dance_loop_01.wav",
        },
        "template": {
            "template_id": "motion_source_overlay_mochi",
            "params": {
                "foreground_asset": fg_asset,
                "duration_seconds": length_seconds,
            },
        },
    }

    out_path = pathlib.Path(out_dir) / f"{job_id}.job.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(remix, indent=2), encoding="utf-8")
    return str(out_path)


def _build_dino_replace_job(
    source_job_path: str,
    out_dir: str,
    motion_source_asset: str,
    foreground_override: str = "",
    variant_suffix: str = "",
) -> Optional[str]:
    src_path = pathlib.Path(source_job_path)
    if not src_path.exists():
        print(f"ERROR: source job not found: {source_job_path}", file=sys.stderr)
        return None
    try:
        src = json.loads(src_path.read_text(encoding="utf-8"))
    except Exception as ex:
        print(f"ERROR: cannot parse source job json: {ex}", file=sys.stderr)
        return None

    src_job_id = str(src.get("job_id", "")).strip()
    if not src_job_id:
        print("ERROR: source job missing job_id", file=sys.stderr)
        return None

    fg_asset = foreground_override.strip() if isinstance(foreground_override, str) else ""
    if not fg_asset:
        render = src.get("render")
        if isinstance(render, dict):
            bg_asset = render.get("background_asset")
            if isinstance(bg_asset, str) and bg_asset.strip().endswith(".mp4"):
                fg_asset = bg_asset.strip()
    if not fg_asset:
        fg_asset = f"assets/generated/{src_job_id}/veo-0001.mp4"
    fg_abs = _repo_root() / "sandbox" / fg_asset
    if not fg_abs.exists():
        print(f"ERROR: expected foreground Veo asset missing: {fg_abs}", file=sys.stderr)
        return None

    bg_abs = _repo_root() / "sandbox" / motion_source_asset
    if not bg_abs.exists():
        print(f"ERROR: motion source asset missing: {bg_abs}", file=sys.stderr)
        return None

    video = src.get("video") if isinstance(src.get("video"), dict) else {}
    fps = int(video.get("fps", 30))
    resolution = str(video.get("resolution", "1080x1920"))
    length_seconds = int(video.get("length_seconds", 18))
    if length_seconds < 10:
        length_seconds = 10

    suffix = variant_suffix.strip()
    if suffix:
        job_id = f"{src_job_id}-replace-dino-{suffix}"
    else:
        job_id = f"{src_job_id}-replace-dino"
    remix = {
        "job_id": job_id,
        "date": str(src.get("date", "2024-05-15")),
        "lane": "template_remix",
        "niche": str(src.get("niche", "cat_dance_comedy")),
        "video": {
            "length_seconds": length_seconds,
            "aspect_ratio": "9:16",
            "fps": fps,
            "resolution": resolution,
        },
        "script": {
            "hook": "Mochi takes the dino slot in the dance loop.",
            "voiceover": "Slot replacement remix: replace the dino-costume dancer with Mochi while preserving source choreography.",
            "ending": "Loop ready.",
        },
        "shots": [
            {"t": 0, "visual": "dance loop", "action": "start", "caption": "Start"},
            {"t": 2, "visual": "dino slot", "action": "mochi replacement", "caption": "Mochi dino"},
            {"t": 5, "visual": "group rhythm", "action": "stay in slot", "caption": "On beat"},
            {"t": 8, "visual": "group rhythm", "action": "keep cadence", "caption": "Groove"},
            {"t": 12, "visual": "group rhythm", "action": "hold replacement", "caption": "Still dancing"},
            {"t": 16, "visual": "loop seam", "action": "reset", "caption": "Replay"},
        ],
        "captions": ["Mochi replaces dino", "Slot remix", "On beat", "Replay"],
        "hashtags": ["#MochiDance", "#TemplateRemix", "#DanceLoop", "#DinoMochi"],
        "render": {
            "background_asset": motion_source_asset,
            "subtitle_style": "big_bottom",
            "output_basename": f"{job_id}_slot_replace",
        },
        "audio": {
            "audio_asset": "assets/audio/beds/caf_bed_dance_loop_01.wav",
        },
        "template": {
            "template_id": "dance_loop_replace_dino_with_mochi",
            "params": {
                "foreground_asset": fg_asset,
                "duration_seconds": length_seconds,
            },
        },
    }

    out_path = pathlib.Path(out_dir) / f"{job_id}.job.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(remix, indent=2), encoding="utf-8")
    return str(out_path)


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(description="One-command local planner -> orchestrator runner.")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--prompt", help="Prompt to send to planner")
    source.add_argument("--prd", help="Path to PRD json")
    parser.add_argument("--provider", default="ai_studio", help="Planner provider")
    parser.add_argument("--inbox", default="sandbox/inbox", help="Inbox directory")
    parser.add_argument("--out", default="sandbox/jobs", help="Planner output directory")
    parser.add_argument("--job-id", default=None, help="Optional job_id override")
    parser.add_argument("--dry-run", action="store_true", help="Generate job only; skip orchestrator run")
    parser.add_argument(
        "--duet-overlay",
        action="store_true",
        help="After base run, auto-create and render template_remix duet overlay job",
    )
    parser.add_argument(
        "--motion-bootstrap",
        action="store_true",
        help="After base run, create/render Lane C motion-source bootstrap remix job",
    )
    parser.add_argument(
        "--motion-source",
        default="assets/demo/dance_loop.mp4",
        help="Sandbox-relative motion source clip for --motion-bootstrap",
    )
    parser.add_argument(
        "--replace-dino",
        action="store_true",
        help="After base run, create/render Lane C slot replacement job (replace dino slot with Mochi)",
    )
    parser.add_argument(
        "--replace-dino-ab",
        action="store_true",
        help="After base run, render both replace-dino variants: video_keyed and image_puppet",
    )
    parser.add_argument(
        "--replace-dino-image-asset",
        default="",
        help="Optional sandbox-relative still image asset for --replace-dino foreground (enables image_puppet mode)",
    )
    args = parser.parse_args(argv)

    root = _repo_root()
    os.chdir(root)

    planner_cmd = ["python3", "-m", "repo.services.planner.planner_cli"]
    if args.prompt:
        prompt = args.prompt
        if args.duet_overlay:
            prompt = (
                f"{prompt}. "
                "Match demo dance-loop choreography timing: side-step and paw-swing groove on steady beat. "
                "Use fixed full-body framing and continuous movement, no idle pauses. "
                "Render single subject isolated on clean solid cyan studio background for compositing. "
                "No props, no extra characters, no text overlay, no camera zoom, no cut edits, "
                "no transparency holes in body, clean silhouette edges."
            )
        planner_cmd += ["--prompt", prompt]
    else:
        planner_cmd += ["--prd", args.prd]
    planner_cmd += ["--provider", args.provider, "--inbox", args.inbox, "--out", args.out]
    if args.job_id:
        planner_cmd += ["--job-id", args.job_id]

    print("STEP planner:", " ".join(planner_cmd))
    planner_res = _run(planner_cmd)
    if planner_res.stdout:
        print(planner_res.stdout, end="")
    if planner_res.stderr:
        print(planner_res.stderr, file=sys.stderr, end="")
    if planner_res.returncode != 0:
        return planner_res.returncode

    job_path = _extract_written_job_path(planner_res.stdout) or _latest_job_path(args.out)
    if not job_path:
        print("ERROR: planner succeeded but no job.json path found", file=sys.stderr)
        return 1

    print(f"STEP planner output: {job_path}")
    if args.provider == "vertex_veo" and _job_uses_demo_background(job_path):
        print(
            "ERROR: planner output is using demo background_asset for vertex_veo. "
            "Refusing to run orchestrator. This indicates fallback/non-generated output.",
            file=sys.stderr,
        )
        return 3
    if args.dry_run:
        print("DRY RUN: skipping orchestrator")
        return 0
    selected_remix_modes = sum(
        [
            1 if args.duet_overlay else 0,
            1 if args.motion_bootstrap else 0,
            1 if (args.replace_dino or args.replace_dino_ab) else 0,
        ]
    )
    if selected_remix_modes > 1:
        print(
            "ERROR: use only one remix mode: --duet-overlay or --motion-bootstrap or --replace-dino/--replace-dino-ab",
            file=sys.stderr,
        )
        return 2

    orch_cmd = ["python3", "-m", "repo.services.orchestrator", "--job", job_path]
    print("STEP orchestrator:", " ".join(orch_cmd))
    orch_res = _run(orch_cmd)
    if orch_res.stdout:
        print(orch_res.stdout, end="")
    if orch_res.stderr:
        print(orch_res.stderr, file=sys.stderr, end="")
    if orch_res.returncode != 0:
        return orch_res.returncode

    if not args.duet_overlay and not args.motion_bootstrap and not args.replace_dino and not args.replace_dino_ab:
        return 0

    if args.duet_overlay:
        duet_job_path = _build_duet_job(job_path, args.out)
        if not duet_job_path:
            return 1
        print(f"STEP duet job: {duet_job_path}")
        remix_cmd = ["python3", "-m", "repo.worker.render_ffmpeg", "--job", duet_job_path]
        print("STEP duet render:", " ".join(remix_cmd))
        remix_res = _run(remix_cmd)
        if remix_res.stdout:
            print(remix_res.stdout, end="")
        if remix_res.stderr:
            print(remix_res.stderr, file=sys.stderr, end="")
        return remix_res.returncode
    elif args.motion_bootstrap:
        motion_job_path = _build_motion_bootstrap_job(job_path, args.out, args.motion_source)
        if not motion_job_path:
            return 1
        print(f"STEP motion bootstrap job: {motion_job_path}")
        remix_cmd = ["python3", "-m", "repo.worker.render_ffmpeg", "--job", motion_job_path]
        print("STEP motion bootstrap render:", " ".join(remix_cmd))
        remix_res = _run(remix_cmd)
        if remix_res.stdout:
            print(remix_res.stdout, end="")
        if remix_res.stderr:
            print(remix_res.stderr, file=sys.stderr, end="")
        return remix_res.returncode
    elif args.replace_dino:
        replace_job_path = _build_dino_replace_job(
            job_path, args.out, args.motion_source, args.replace_dino_image_asset
        )
        if not replace_job_path:
            return 1
        print(f"STEP dino-replace job: {replace_job_path}")
        remix_cmd = ["python3", "-m", "repo.worker.render_ffmpeg", "--job", replace_job_path]
        print("STEP dino-replace render:", " ".join(remix_cmd))
        remix_res = _run(remix_cmd)
        if remix_res.stdout:
            print(remix_res.stdout, end="")
        if remix_res.stderr:
            print(remix_res.stderr, file=sys.stderr, end="")
        return remix_res.returncode
    else:
        image_asset = args.replace_dino_image_asset.strip() or "assets/demo/mochi_front.png"
        jobs = [
            (
                "video",
                _build_dino_replace_job(job_path, args.out, args.motion_source, "", "video"),
            ),
            (
                "image",
                _build_dino_replace_job(job_path, args.out, args.motion_source, image_asset, "image"),
            ),
        ]
        for label, p in jobs:
            if not p:
                return 1
            print(f"STEP dino-replace-{label} job: {p}")
            cmd = ["python3", "-m", "repo.worker.render_ffmpeg", "--job", p]
            print(f"STEP dino-replace-{label} render:", " ".join(cmd))
            res = _run(cmd)
            if res.stdout:
                print(res.stdout, end="")
            if res.stderr:
                print(res.stderr, file=sys.stderr, end="")
            if res.returncode != 0:
                return res.returncode
        return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
