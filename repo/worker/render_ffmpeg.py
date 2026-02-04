import argparse
import datetime as dt
import hashlib
import json
import os
import pathlib
import shutil
import subprocess

CREATION_TIME = "1970-01-01T00:00:00Z"


def detect_sandbox_root() -> pathlib.Path:
    """
    Resolve sandbox root for both host and container runs.

    Priority:
      1) SANDBOX_ROOT env var (explicit override)
      2) /sandbox if it exists and is writable (container mount)
      3) repo_root/sandbox (local dev)
    """
    env = os.environ.get("SANDBOX_ROOT")
    if env:
        return pathlib.Path(env).expanduser().resolve()

    p = pathlib.Path("/sandbox")
    try:
        if p.exists() and os.access(str(p), os.W_OK):
            return p
    except Exception:
        pass

    # repo_root inferred from this file: repo/worker/render_ffmpeg.py -> repo_root is parents[2]
    repo_root = pathlib.Path(__file__).resolve().parents[2]
    return (repo_root / "sandbox").resolve()


SANDBOX = detect_sandbox_root()
JOBS = SANDBOX / "jobs"
OUTPUT = SANDBOX / "output"
LOGS = SANDBOX / "logs"


def sha256_file(path: pathlib.Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def stable_json_dumps(data: dict) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def atomic_replace(src: pathlib.Path, dst: pathlib.Path) -> None:
    os.replace(str(src), str(dst))


def make_srt(captions, out_path: pathlib.Path) -> None:
    # naive 3s per caption
    def ts(sec):
        h = sec // 3600
        m = (sec % 3600) // 60
        s = sec % 60
        return f"{h:02}:{m:02}:{s:02},000"

    lines = []
    t = 0
    for i, cap in enumerate(captions, start=1):
        start = ts(t)
        end = ts(t + 3)
        lines += [str(i), f"{start} --> {end}", cap, ""]
        t += 3
    out_path.write_text("\n".join(lines), encoding="utf-8")


def ffmpeg_escape_path(path: pathlib.Path) -> str:
    # ffmpeg filter args need escaping for ":" and "\" on some platforms
    return str(path).replace("\\", "\\\\").replace(":", "\\:")

def ffmpeg_has_filter(name: str) -> bool:
    if not shutil.which("ffmpeg"):
        return False
    proc = subprocess.run(
        ["ffmpeg", "-hide_banner", "-filters"],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    return proc.returncode == 0 and f" {name} " in proc.stdout


def get_ffmpeg_version() -> str | None:
    if not shutil.which("ffmpeg"):
        return None
    proc = subprocess.run(
        ["ffmpeg", "-version"],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    if proc.stdout:
        return proc.stdout.splitlines()[0].strip()
    return None


def resolve_job_path(arg_path: str | None) -> pathlib.Path:
    if arg_path:
        return pathlib.Path(arg_path)
    job_files = sorted(JOBS.glob("*.job.json"))
    if not job_files:
        raise SystemExit(f"No job files found in {JOBS}")
    return job_files[-1]


def resolve_asset(path_str: str) -> pathlib.Path:
    candidate = pathlib.Path(path_str)
    if candidate.is_absolute():
        return candidate
    return SANDBOX / candidate


def main() -> None:
    parser = argparse.ArgumentParser(description="Deterministic FFmpeg worker.")
    parser.add_argument("--job", dest="job_path", help="Path to job.json")
    args = parser.parse_args()

    # Ensure base directories exist
    OUTPUT.mkdir(parents=True, exist_ok=True)
    LOGS.mkdir(parents=True, exist_ok=True)

    job_path = resolve_job_path(args.job_path)
    job = json.loads(job_path.read_text(encoding="utf-8"))

    job_id = job["job_id"]
    schema_version = job.get("schema_version")

    bg = resolve_asset(job["render"]["background_asset"])
    if not bg.exists():
        raise SystemExit(f"Missing background asset: {bg}")

    out_dir = OUTPUT / job_id
    out_dir.mkdir(parents=True, exist_ok=True)

    # Prefer per-job log directory (stable, avoids collisions)
    log_dir = LOGS / job_id
    log_dir.mkdir(parents=True, exist_ok=True)

    out_mp4 = out_dir / "final.mp4"
    srt_path = out_dir / "final.srt"
    result_path = out_dir / "result.json"
    log_path = log_dir / "worker.log"

    tmp_mp4 = out_dir / "final.tmp.mp4"
    tmp_srt = out_dir / "final.tmp.srt"
    tmp_result = out_dir / "result.tmp.json"

    start_ts = dt.datetime.now(dt.timezone.utc).isoformat()

    # Generate SRT -> atomic replace
    make_srt(job["captions"], tmp_srt)
    atomic_replace(tmp_srt, srt_path)

    subs = str(srt_path).replace("\\", "\\\\").replace("'", "\\'")
    vf = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920"

    burn = os.environ.get("BURN_SUBTITLES", "").strip() in ("1", "true", "TRUE", "yes", "YES")
    if burn:
        if not ffmpeg_has_filter("subtitles"):
            raise SystemExit(
                "BURN_SUBTITLES=1 but ffmpeg has no 'subtitles' filter. "
                "Install ffmpeg with libass, or unset BURN_SUBTITLES."
            )
        subs = str(srt_path).replace("\\", "\\\\").replace("'", "\\'")
        vf = vf + f",subtitles=filename='{subs}'"

    cmd = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "info",
        "-fflags",
        "+bitexact",
        "-i",
        str(bg),
        "-vf",
        vf,
        "-t",
        str(job["video"]["length_seconds"]),
        "-r",
        str(job["video"]["fps"]),
        "-fps_mode",
        "cfr",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-flags:v",
        "+bitexact",
        "-map_metadata",
        "-1",
        "-metadata",
        f"creation_time={CREATION_TIME}",
        str(tmp_mp4),
    ]

    # Best-effort cleanup of old temp files from prior failed runs
    for p in (tmp_mp4, tmp_srt, tmp_result):
        try:
            if p.exists():
                p.unlink()
        except Exception:
            pass

    with log_path.open("w", encoding="utf-8") as log_handle:
        log_handle.write(f"job_id={job_id}\n")
        log_handle.write(f"schema_version={schema_version}\n")
        log_handle.write(f"sandbox_root={SANDBOX}\n")
        log_handle.write(f"job_path={job_path}\n")
        log_handle.write(f"bg_asset={bg}\n")
        log_handle.write("command=" + " ".join(cmd) + "\n")
        log_handle.flush()
        subprocess.check_call(cmd, stdout=log_handle, stderr=log_handle)

    # Atomic replace for mp4
    atomic_replace(tmp_mp4, out_mp4)

    # Checksums
    mp4_sha = sha256_file(out_mp4)
    srt_sha = sha256_file(srt_path)

    deterministic = {
        "job_id": job_id,
        "schema_version": schema_version,
        "inputs": {
            "job_path": str(job_path),
            "asset_paths": [str(bg)],
        },
        "outputs": {
            "mp4": str(out_mp4),
            "srt": str(srt_path),
            "result_json": str(result_path),
        },
        "output_checksums": {
            "mp4_sha256": mp4_sha,
            "srt_sha256": srt_sha,
        },
    }

    deterministic_hash = hashlib.sha256(
        stable_json_dumps(deterministic).encode("utf-8")
    ).hexdigest()

    end_ts = dt.datetime.now(dt.timezone.utc).isoformat()

    result = {
        "deterministic": deterministic,
        "deterministic_sha256": deterministic_hash,
        "runtime": {
            "started_at": start_ts,
            "ended_at": end_ts,
            "ffmpeg_version": get_ffmpeg_version(),
            "log_path": str(log_path),
        },
    }

    tmp_result.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    atomic_replace(tmp_result, result_path)

    print("Sandbox root:", SANDBOX)
    print("Wrote", out_mp4)
    print("Wrote", srt_path)
    print("Wrote", result_path)
    print("Log", log_path)


if __name__ == "__main__":
    main()
