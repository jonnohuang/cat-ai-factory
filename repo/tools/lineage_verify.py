import argparse
import json
import pathlib


def repo_root_from_here() -> pathlib.Path:
    # repo/tools/lineage_verify.py -> <repo_root>
    return pathlib.Path(__file__).resolve().parents[2]


def load_job(job_path: pathlib.Path):
    if not job_path.exists():
        raise SystemExit(f"Job file not found: {job_path}")
    return job_path, json.loads(job_path.read_text(encoding="utf-8"))


def resolve_job(job_path_or_id: str, jobs_dir: pathlib.Path):
    path = pathlib.Path(job_path_or_id)

    # If caller passed an existing file path, use it.
    if path.exists() and path.is_file() and path.suffix == ".json":
        return load_job(path)

    # Otherwise treat as job_id.
    job_id = job_path_or_id
    job_file = jobs_dir / f"{job_id}.job.json"
    return load_job(job_file)


def main():
    parser = argparse.ArgumentParser(description="Verify artifact lineage for a job.")
    parser.add_argument("job_path_or_id", help="Job path or job_id")
    parser.add_argument(
        "--sandbox-root",
        default=None,
        help="Path to sandbox root. Default: <repo_root>/sandbox (host). Use /sandbox in containers if mounted.",
    )
    args = parser.parse_args()

    root = repo_root_from_here()
    sandbox_root = pathlib.Path(args.sandbox_root) if args.sandbox_root else (root / "sandbox")

    jobs_dir = sandbox_root / "jobs"
    output_root = sandbox_root / "output"
    logs_root = sandbox_root / "logs"

    job_path, job = resolve_job(args.job_path_or_id, jobs_dir)
    job_id = job.get("job_id")
    if not job_id:
        raise SystemExit("job_id missing in job.json")

    missing = []

    # Job contract must exist either at the provided path or in canonical jobs_dir.
    canonical_job = jobs_dir / f"{job_id}.job.json"
    if not job_path.exists() and not canonical_job.exists():
        missing.append(f"job contract: {canonical_job}")

    # Outputs must exist at canonical location keyed by job_id.
    out_dir = output_root / job_id
    for name in ["final.mp4", "final.srt", "result.json"]:
        out_file = out_dir / name
        if not out_file.exists():
            missing.append(f"output: {out_file}")

    # Logs must exist: either a directory logs/<job_id>/ with at least one file,
    # or a single file logs/<job_id>*, to allow legacy patterns.
    logs_ok = False
    if logs_root.exists():
        log_path = logs_root / job_id
        if log_path.exists():
            if log_path.is_dir():
                logs_ok = any(log_path.iterdir())
            else:
                logs_ok = True
        else:
            matches = list(logs_root.glob(f"{job_id}*"))
            logs_ok = len(matches) > 0

    if not logs_ok:
        missing.append(f"logs under {logs_root} keyed by {job_id}")

    if missing:
        print("Lineage verification failed:")
        for item in missing:
            print(f"- Missing {item}")
        raise SystemExit(1)

    print(f"Lineage verification OK for job_id={job_id}")


if __name__ == "__main__":
    raise SystemExit(main())
