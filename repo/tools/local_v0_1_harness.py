import argparse
import json
import pathlib
import shutil
import subprocess
import sys
import time

REQUIRED_OUTPUTS = ["final.mp4", "final.srt", "result.json"]


def repo_root_from_here() -> pathlib.Path:
    # repo/tools/local_v0_1_harness.py -> <repo_root>
    return pathlib.Path(__file__).resolve().parents[2]


def run_step(name, cmd, log_path: pathlib.Path) -> float:
    start = time.time()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w", encoding="utf-8") as log_file:
        log_file.write(f"STEP {name}\n")
        log_file.write("CMD: " + " ".join(cmd) + "\n\n")
        result = subprocess.run(cmd, stdout=log_file, stderr=subprocess.STDOUT)
    duration = time.time() - start
    if result.returncode != 0:
        raise RuntimeError(f"{name} failed with exit code {result.returncode}. See log: {log_path}")
    return duration


def snapshot_outputs(output_dir: pathlib.Path, label: str, logs_dir: pathlib.Path) -> pathlib.Path:
    if not output_dir.exists():
        raise RuntimeError(f"Expected output directory missing: {output_dir}")
    dest_dir = logs_dir / label
    if dest_dir.exists():
        shutil.rmtree(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    for name in REQUIRED_OUTPUTS:
        src_file = output_dir / name
        if not src_file.exists():
            raise RuntimeError(f"Expected output missing: {src_file}")
        shutil.copy2(src_file, dest_dir / name)
    return dest_dir


def load_job(job_path: str):
    job_file = pathlib.Path(job_path)
    if not job_file.exists():
        raise SystemExit(f"Job file not found: {job_file}")
    job = json.loads(job_file.read_text(encoding="utf-8"))
    job_id = job.get("job_id")
    if not job_id:
        raise SystemExit("job_id missing in job.json")
    return job_file, job_id


def main():
    parser = argparse.ArgumentParser(description="Local v0.1 determinism + lineage harness.")
    parser.add_argument("job_path", help="Path to job.json")
    parser.add_argument(
        "--sandbox-root",
        default=None,
        help="Path to sandbox root. Default: <repo_root>/sandbox (host). Use /sandbox in containers if mounted.",
    )
    args = parser.parse_args()

    root = repo_root_from_here()
    sandbox_root = pathlib.Path(args.sandbox_root) if args.sandbox_root else (root / "sandbox")
    logs_root = sandbox_root / "logs"
    output_root = sandbox_root / "output"

    job_file, job_id = load_job(args.job_path)

    # IMPORTANT: validate first; do not create logs/output dirs until validation passes.
    # We'll still write the validation log to a temp path under repo_root if validation fails.
    tmp_validate_log = root / ".tmp" / "harness" / job_id / "validate_job.log"

    summary = {
        "job_id": job_id,
        "job_path": str(job_file),
        "sandbox_root": str(sandbox_root),
        "steps": [],
        "status": "unknown",
    }

    try:
        duration = run_step(
            "validate_job",
            ["python3", "repo/tools/validate_job.py", str(job_file)],
            tmp_validate_log,
        )
        summary["steps"].append({"name": "validate_job", "status": "ok", "duration_sec": round(duration, 3)})

        # Now that validation succeeded, establish canonical logs dir.
        logs_dir = logs_root / job_id
        logs_dir.mkdir(parents=True, exist_ok=True)

        # Move validation log into canonical logs directory
        canonical_validate_log = logs_dir / "validate_job.log"
        canonical_validate_log.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(tmp_validate_log, canonical_validate_log)

        duration = run_step(
            "worker_run_1",
            ["python3", "repo/worker/render_ffmpeg.py", "--job", str(job_file), "--sandbox-root", str(sandbox_root)],
            logs_dir / "worker_run_1.log",
        )
        summary["steps"].append({"name": "worker_run_1", "status": "ok", "duration_sec": round(duration, 3)})

        out_dir = output_root / job_id
        run1_dir = snapshot_outputs(out_dir, "run1", logs_dir)

        duration = run_step(
            "worker_run_2",
            ["python3", "repo/worker/render_ffmpeg.py", "--job", str(job_file), "--sandbox-root", str(sandbox_root)],
            logs_dir / "worker_run_2.log",
        )
        summary["steps"].append({"name": "worker_run_2", "status": "ok", "duration_sec": round(duration, 3)})

        run2_dir = snapshot_outputs(out_dir, "run2", logs_dir)

        duration = run_step(
            "determinism_check",
            ["python3", "repo/tools/determinism_check.py", str(run1_dir), str(run2_dir)],
            logs_dir / "determinism_check.log",
        )
        summary["steps"].append({"name": "determinism_check", "status": "ok", "duration_sec": round(duration, 3)})

        duration = run_step(
            "lineage_verify",
            ["python3", "repo/tools/lineage_verify.py", str(job_file), "--sandbox-root", str(sandbox_root)],
            logs_dir / "lineage_verify.log",
        )
        summary["steps"].append({"name": "lineage_verify", "status": "ok", "duration_sec": round(duration, 3)})

        summary["status"] = "ok"

        summary["qc"] = run_qc_step(job_id, str(job_file), sandbox_root)

        summary_path = logs_dir / "harness_summary.json"
        summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")

        print(f"LOCAL v0.1 harness OK for job_id={job_id}")
        print(f"Summary: {summary_path}")
        return 0

    except Exception as exc:
        summary["status"] = "failed"
        summary["error"] = str(exc)

        # Best-effort write summary: prefer canonical logs dir if possible, else temp.
        logs_dir = (logs_root / job_id)
        try:
            logs_dir.mkdir(parents=True, exist_ok=True)
            summary_path = logs_dir / "harness_summary.json"
        except Exception:
            tmp_dir = root / ".tmp" / "harness" / job_id
            tmp_dir.mkdir(parents=True, exist_ok=True)
            summary_path = tmp_dir / "harness_summary.json"

        summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
        print("Harness failed:", exc)
        print(f"Summary: {summary_path}")
        return 1


def run_qc_step(job_id: str, job_path: str, sandbox_root: pathlib.Path) -> dict:
    qc_summary = {
        "ran": True,
        "status": "ERROR",
        "summary_path": f"sandbox/logs/{job_id}/qc/qc_summary.json",
        "log_path": f"sandbox/logs/{job_id}/qc/qc.log",
        "exit_code": -1,
        "details": "QC step not run",
    }
    try:
        cmd = ["python3", "-m", "repo.tools.qc_verify", job_path, "--sandbox-root", str(sandbox_root)]
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)

        qc_summary["exit_code"] = result.returncode
        if result.returncode == 0:
            qc_summary["status"] = "PASS"
            qc_summary["details"] = "QC passed."
        elif result.returncode == 2:
            qc_summary["status"] = "FAIL"
            qc_summary["details"] = "QC checks failed."
        else:
            qc_summary["status"] = "ERROR"
            qc_summary["details"] = f"QC tool returned an unexpected exit code. Stderr: {result.stderr.strip()}"

    except FileNotFoundError:
        qc_summary["details"] = "QC tool not found or python3 is not in PATH."
    except Exception as e:
        qc_summary["details"] = f"An exception occurred while running QC: {e}"

    return qc_summary


if __name__ == "__main__":
    raise SystemExit(main())
