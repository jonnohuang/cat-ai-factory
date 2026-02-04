import argparse
import hashlib
import json
import pathlib
import subprocess
import sys
import os

def detect_sandbox_root() -> pathlib.Path:
    env = os.environ.get("SANDBOX_ROOT")
    if env:
        return pathlib.Path(env).expanduser().resolve()

    p = pathlib.Path("/sandbox")
    try:
        if p.exists() and os.access(str(p), os.W_OK):
            return p
    except Exception:
        pass

    repo_root = pathlib.Path(__file__).resolve().parents[2]
    return (repo_root / "sandbox").resolve()

SANDBOX = detect_sandbox_root()
OUTPUT = SANDBOX / "output"

def sha256_file(path: pathlib.Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()

def load_result(path: pathlib.Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))

def run_worker(job_path: pathlib.Path) -> None:
    subprocess.check_call([
        sys.executable,
        "repo/worker/render_ffmpeg.py",
        "--job",
        str(job_path),
    ])

def main() -> None:
    parser = argparse.ArgumentParser(description="Run worker twice and compare outputs.")
    parser.add_argument("job_path", help="Path to job.json")
    args = parser.parse_args()

    job_path = pathlib.Path(args.job_path)
    job = json.loads(job_path.read_text(encoding="utf-8"))
    job_id = job["job_id"]

    out_dir = OUTPUT / job_id
    mp4_path = out_dir / "final.mp4"
    srt_path = out_dir / "final.srt"
    result_path = out_dir / "result.json"

    print("Run 1")
    run_worker(job_path)
    mp4_sha_1 = sha256_file(mp4_path)
    srt_sha_1 = sha256_file(srt_path)
    result_1 = load_result(result_path)

    print("Run 2")
    run_worker(job_path)
    mp4_sha_2 = sha256_file(mp4_path)
    srt_sha_2 = sha256_file(srt_path)
    result_2 = load_result(result_path)

    ok = True

    if mp4_sha_1 != mp4_sha_2:
        print("MP4 checksum mismatch")
        ok = False
    if srt_sha_1 != srt_sha_2:
        print("SRT checksum mismatch")
        ok = False
    if result_1.get("deterministic") != result_2.get("deterministic"):
        print("Result deterministic section mismatch")
        ok = False
    if result_1.get("deterministic_sha256") != result_2.get("deterministic_sha256"):
        print("Result deterministic hash mismatch")
        ok = False

    print("mp4_sha256:", mp4_sha_1)
    print("srt_sha256:", srt_sha_1)
    print("deterministic_sha256:", result_2.get("deterministic_sha256"))

    if not ok:
        raise SystemExit(1)

if __name__ == "__main__":
    main()
