#!/usr/bin/env python3
"""
finalize_viggle_reingest.py

Deterministically finalize an external Viggle re-ingest video into CAF output path:
  sandbox/output/<job_id>/final.mp4
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import subprocess
import sys
import time
from typing import Any

PADDING_PX = 24
OPACITY = 0.35
WM_WIDTH = 129


def _repo_root() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parents[2]


def _sha256_file(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _atomic_write_json(path: pathlib.Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    tmp.replace(path)


def _has_audio_stream(path: pathlib.Path) -> bool:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "a:0",
        "-show_entries",
        "stream=codec_type",
        "-of",
        "csv=p=0",
        str(path),
    ]
    try:
        out = subprocess.check_output(cmd, text=True).strip()
    except subprocess.CalledProcessError:
        return False
    return bool(out)


def _run_ffmpeg(cmd: list[str], out_mp4: pathlib.Path) -> list[str]:
    tmp_out = out_mp4.with_name(out_mp4.name + ".tmp" + out_mp4.suffix)
    if tmp_out.exists():
        tmp_out.unlink()
    cmd2 = list(cmd)
    cmd2[-1] = str(tmp_out)
    print("Running:", " ".join(cmd2))
    subprocess.check_call(cmd2)
    tmp_out.replace(out_mp4)
    return cmd2


def _enhance_video_in_place(path: pathlib.Path) -> list[str]:
    return _enhance_video_in_place_with_preset(path, "mild")


def _enhance_video_in_place_with_preset(path: pathlib.Path, preset: str) -> list[str]:
    enhanced = path.with_name(path.stem + ".enhanced" + path.suffix)
    if enhanced.exists():
        enhanced.unlink()
    if preset == "strong":
        vf = "hqdn3d=1.2:1.2:4:4,unsharp=7:7:0.80:5:5:0.00,eq=contrast=1.03:saturation=1.03"
    else:
        vf = "hqdn3d=0.8:0.8:3:3,unsharp=5:5:0.40:3:3:0.00"
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(path),
        "-vf",
        vf,
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "copy",
        "-movflags",
        "+faststart",
        "-map_metadata",
        "-1",
        "-map_chapters",
        "-1",
        str(enhanced),
    ]
    print("Running:", " ".join(cmd))
    subprocess.check_call(cmd)
    backup = path.with_name(path.stem + ".pre_enhance" + path.suffix)
    if not backup.exists():
        path.replace(backup)
    else:
        path.unlink(missing_ok=True)
    enhanced.replace(path)
    return cmd


def _resolve_input(root: pathlib.Path, p: str) -> pathlib.Path:
    pp = pathlib.Path(p)
    if pp.is_absolute():
        return pp
    return root / p


def _run_costume_gate(
    root: pathlib.Path,
    job_id: str,
    final_video: pathlib.Path,
    costume_ref: str,
    tracks_relpath: str,
    subject_id: str | None,
    threshold: float,
) -> dict[str, Any]:
    report = (
        root / "sandbox" / "logs" / job_id / "qc" / "costume_fidelity_report.v1.json"
    )
    cmd = [
        sys.executable,
        "-m",
        "repo.tools.score_costume_fidelity",
        "--job-id",
        job_id,
        "--video-relpath",
        str(final_video),
        "--costume-image-relpath",
        costume_ref,
        "--tracks-relpath",
        tracks_relpath,
        "--threshold",
        f"{threshold:.4f}",
        "--out",
        str(report),
    ]
    if subject_id:
        cmd.extend(["--subject-id", subject_id])
    print("Running:", " ".join(cmd))
    subprocess.check_call(cmd)
    return json.loads(report.read_text(encoding="utf-8"))


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Finalize external Viggle output into CAF final output path"
    )
    parser.add_argument("--job-id", required=True, help="Job ID")
    parser.add_argument(
        "--input-relpath",
        help="Input relpath from repo root. Default: sandbox/inbox/viggle_results/<job_id>/viggle.mp4",
    )
    parser.add_argument(
        "--compose-mode",
        choices=["pad", "crop"],
        default="pad",
        help="Video composition strategy for 9:16 output. 'pad' preserves full frame; 'crop' fills frame by center crop.",
    )
    parser.add_argument(
        "--enhance",
        action="store_true",
        help="Apply deterministic post-process enhancement (denoise + mild sharpen) after finalize render.",
    )
    parser.add_argument(
        "--enhance-preset",
        choices=["mild", "strong"],
        default="mild",
        help="Enhancement preset used when --enhance is enabled.",
    )
    parser.add_argument(
        "--costume-ref-relpath",
        help="Optional costume reference image relpath for fidelity gate",
    )
    parser.add_argument(
        "--tracks-relpath",
        help="Optional tracks artifact relpath; default sandbox/output/<job_id>/contracts/tracks.json when available",
    )
    parser.add_argument(
        "--subject-id", help="Optional tracked subject id for costume gate"
    )
    parser.add_argument(
        "--costume-threshold",
        type=float,
        default=0.52,
        help="Pass threshold for costume gate",
    )
    parser.add_argument(
        "--require-costume-pass",
        action="store_true",
        help="Fail finalize if costume fidelity gate does not pass",
    )
    args = parser.parse_args(argv[1:])

    root = _repo_root()
    job_id = args.job_id
    input_rel = (
        args.input_relpath or f"sandbox/inbox/viggle_results/{job_id}/viggle.mp4"
    )
    in_video = _resolve_input(root, input_rel)
    if not in_video.exists():
        raise SystemExit(f"Input video not found: {in_video}")

    wm = root / "repo/assets/watermarks/caf-watermark.png"
    if not wm.exists():
        raise SystemExit(f"Watermark not found: {wm}")

    out_dir = root / "sandbox/output" / job_id
    out_dir.mkdir(parents=True, exist_ok=True)
    out_mp4 = out_dir / "final.mp4"
    out_srt = out_dir / "final.srt"
    result_json = out_dir / "result.json"

    # Keep previous baseline render for traceability.
    if out_mp4.exists():
        backup = out_dir / "final.worker_baseline.mp4"
        if not backup.exists():
            out_mp4.replace(backup)

    audio_present = _has_audio_stream(in_video)

    if audio_present:
        inputs = ["-i", str(in_video), "-i", str(wm)]
        audio_map = ["-map", "0:a:0"]
    else:
        inputs = [
            "-i",
            str(in_video),
            "-f",
            "lavfi",
            "-i",
            "anullsrc=channel_layout=stereo:sample_rate=48000",
            "-i",
            str(wm),
        ]
        audio_map = ["-map", "1:a:0"]

    wm_input_idx = 1 if audio_present else 2
    if args.compose_mode == "crop":
        compose_filter = (
            "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,"
            "crop=1080:1920,setsar=1[v]"
        )
    else:
        compose_filter = (
            "[0:v]scale=1080:1920:force_original_aspect_ratio=decrease,"
            "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black,setsar=1[v]"
        )
    filter_complex = (
        f"{compose_filter};"
        f"[{wm_input_idx}:v]format=rgba,colorchannelmixer=aa={OPACITY},scale={WM_WIDTH}:-1[wm];"
        f"[v][wm]overlay=W-w-{PADDING_PX}:H-h-{PADDING_PX}[out]"
    )

    cmd = [
        "ffmpeg",
        "-y",
        *inputs,
        "-filter_complex",
        filter_complex,
        "-map",
        "[out]",
        *audio_map,
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-ar",
        "48000",
        "-ac",
        "2",
        "-movflags",
        "+faststart",
        "-map_metadata",
        "-1",
        "-map_chapters",
        "-1",
        str(out_mp4),
    ]
    cmd_executed = _run_ffmpeg(cmd, out_mp4)
    enhance_cmd: list[str] | None = None
    if args.enhance:
        enhance_cmd = _enhance_video_in_place_with_preset(out_mp4, args.enhance_preset)

    costume_gate: dict[str, Any] | None = None
    if args.costume_ref_relpath:
        tracks_rel = (
            args.tracks_relpath or f"sandbox/output/{job_id}/contracts/tracks.json"
        )
        costume_gate = _run_costume_gate(
            root=root,
            job_id=job_id,
            final_video=out_mp4,
            costume_ref=args.costume_ref_relpath,
            tracks_relpath=tracks_rel,
            subject_id=args.subject_id,
            threshold=float(args.costume_threshold),
        )

    out_srt.write_text("", encoding="utf-8")

    result = {
        "job_id": job_id,
        "lane": "external_recast_finalize",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source_video": str(in_video),
        "outputs": {
            "final_mp4": str(out_mp4),
            "final_srt": str(out_srt),
        },
        "hashes": {
            "final_mp4_sha256": _sha256_file(out_mp4),
            "final_srt_sha256": _sha256_file(out_srt),
        },
        "audio_source": "input_audio" if audio_present else "silence_fallback",
        "compose_mode": args.compose_mode,
        "enhance_applied": bool(args.enhance),
        "enhance_preset": args.enhance_preset if args.enhance else None,
        "ffmpeg_cmd_executed": cmd_executed,
    }
    if enhance_cmd is not None:
        result["ffmpeg_enhance_cmd_executed"] = enhance_cmd
    if costume_gate is not None:
        result["costume_gate"] = {
            "enabled": True,
            "report_relpath": f"sandbox/logs/{job_id}/qc/costume_fidelity_report.v1.json",
            "threshold": float(args.costume_threshold),
            "pass": bool(costume_gate.get("pass")),
            "score": costume_gate.get("score"),
            "available": bool(costume_gate.get("available")),
            "reason": costume_gate.get("reason"),
        }
    _atomic_write_json(result_json, result)
    if (
        args.require_costume_pass
        and costume_gate is not None
        and not bool(costume_gate.get("pass"))
    ):
        raise SystemExit(
            "Costume fidelity gate failed; finalize aborted by --require-costume-pass"
        )
    print("Wrote", out_mp4)
    print("Wrote", out_srt)
    print("Wrote", result_json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
