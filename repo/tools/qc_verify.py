import argparse
import json
import logging
import pathlib
import subprocess
import sys
import time

# Exit codes
# 0: PASS (includes warnings in non-strict mode)
# 1: Runtime Error (e.g., unexpected exception)
# 2: FAIL (critical failure, or warning in --strict mode)
EXIT_PASS = 0
EXIT_ERROR = 1
EXIT_FAIL = 2


def setup_logging(log_dir: pathlib.Path):
    """Sets up logging to file and console, overwriting the log file."""
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "qc.log"

    # Get the root logger, set level, and remove any existing handlers
    # to ensure we don't append across runs or duplicate logs.
    log = logging.getLogger()
    log.setLevel(logging.INFO)
    if log.hasHandlers():
        log.handlers.clear()

    # Create new handlers with 'w' mode for overwriting the file
    file_handler = logging.FileHandler(log_file, mode="w")
    stream_handler = logging.StreamHandler(sys.stdout)

    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    file_handler.setFormatter(formatter)
    stream_handler.setFormatter(formatter)

    log.addHandler(file_handler)
    log.addHandler(stream_handler)


def get_job_id_from_path(job_path: pathlib.Path) -> str:
    """Extracts the job_id from the job.json filename, handling multiple extensions."""
    # e.g., "my-job.job.json" -> "my-job"
    return job_path.name.removesuffix(".job.json")


def run_subprocess(command: list[str], log_path: pathlib.Path, cwd: str) -> bool:
    """Runs a command, captures its output, and returns success."""
    logging.info(f"Running command: {' '.join(command)}")
    with open(log_path, "w") as f:
        result = subprocess.run(
            command,
            stdout=f,
            stderr=subprocess.STDOUT,
            cwd=cwd,
        )
    if result.returncode != 0:
        logging.error(
            f"Command failed with exit code {result.returncode}. See {log_path}"
        )
        return False
    logging.info(f"Command succeeded. Log: {log_path}")
    return True


def main():
    """Main entry point for the QC verification tool."""
    start_time = time.time()
    parser = argparse.ArgumentParser(
        description="Deterministic QC Agent for Cat AI Factory."
    )
    parser.add_argument(
        "job_json_path",
        type=pathlib.Path,
        help="Path to the job.json file to verify.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Treat warnings as failures, exiting with code 2.",
    )
    args = parser.parse_args()

    repo_root = pathlib.Path(__file__).resolve().parent.parent.parent
    job_path = args.job_json_path.resolve()
    job_id = get_job_id_from_path(job_path)

    # Define paths and set up logging first
    sandbox_root = repo_root / "sandbox"
    log_dir = sandbox_root / "logs" / job_id / "qc"
    setup_logging(log_dir)

    # Now that logging is active, check for the job file
    if not job_path.exists():
        logging.critical(f"Job file not found at {job_path}")
        sys.exit(EXIT_FAIL)

    output_dir = sandbox_root / "output" / job_id

    logging.info(f"Starting QC verification for job_id: {job_id}")
    logging.info(f"Strict mode: {args.strict}")

    summary = {"job_id": job_id, "checks": []}
    critical_failures = []
    warnings = []

    # 1. Job Validation Check
    check_job_validation = {"name": "job_schema_validation", "status": "FAIL"}
    validate_log = log_dir / "validate_job.log"
    validate_cmd = [sys.executable, "-m", "repo.tools.validate_job", str(job_path)]
    if run_subprocess(validate_cmd, validate_log, str(repo_root)):
        check_job_validation["status"] = "PASS"
    else:
        critical_failures.append("job_schema_validation")
    summary["checks"].append(check_job_validation)

    # 2. Lineage Verification Check
    check_lineage = {"name": "artifact_lineage_verification", "status": "FAIL"}
    lineage_log = log_dir / "lineage_verify.log"
    lineage_cmd = [sys.executable, "-m", "repo.tools.lineage_verify", str(job_path)]
    if run_subprocess(lineage_cmd, lineage_log, str(repo_root)):
        check_lineage["status"] = "PASS"
    else:
        critical_failures.append("artifact_lineage_verification")
    summary["checks"].append(check_lineage)

    # 3. Output Presence Check
    check_output_presence = {"name": "output_presence", "status": "PASS", "details": []}
    critical_files_missing = False
    # Critical files
    for fname in ["final.mp4", "result.json"]:
        fpath = output_dir / fname
        if not fpath.exists() or fpath.stat().st_size == 0:
            critical_files_missing = True
            msg = f"CRITICAL: Missing or empty required output: {fpath}"
            logging.error(msg)
            check_output_presence["details"].append(msg)
            critical_failures.append(f"missing_{fname}")

    # After checking critical files, scan for hints if any were missing.
    if critical_files_missing:
        versioned_candidates = []
        output_parent_dir = output_dir.parent
        if output_parent_dir.exists():
            for item in output_parent_dir.iterdir():
                if item.is_dir() and item.name.startswith(f"{job_id}-v"):
                    version_part = item.name.split("-v")[-1]
                    if version_part.isdigit():
                        versioned_candidates.append(item.name)

        if versioned_candidates:
            versioned_candidates.sort()  # Deterministic sort
            best_candidate = versioned_candidates[0]  # Pick lowest version
            hint_msg = (
                f'Found versioned outputs directory "{best_candidate}". '
                f'Did you mean to QC "{best_candidate}.job.json"?'
            )
            logging.warning(hint_msg)
            check_output_presence["details"].append(f"HINT: {hint_msg}")

    # Optional files (warnings)
    srt_path = output_dir / "final.srt"
    if not srt_path.exists() or srt_path.stat().st_size == 0:
        msg = "WARN: Optional file final.srt is missing or empty."
        logging.warning(msg)
        check_output_presence["details"].append(msg)
        warnings.append("missing_final.srt")
    else:
        check_output_presence["details"].append("Found optional final.srt")

    if any(
        f in critical_failures for f in ["missing_final.mp4", "missing_result.json"]
    ):
        check_output_presence["status"] = "FAIL"
    elif "missing_final.srt" in warnings:
        check_output_presence["status"] = "WARN"
    summary["checks"].append(check_output_presence)

    # 4. JSON Integrity Check
    check_json_integrity = {
        "name": "result_json_integrity",
        "status": "PASS",
        "details": [],
    }
    result_json_path = output_dir / "result.json"
    if not result_json_path.exists() or result_json_path.stat().st_size == 0:
        msg = "CRITICAL: result.json missing; cannot validate integrity"
        logging.error(msg)
        check_json_integrity["details"].append(msg)
        critical_failures.append("result_json_integrity_missing")
        check_json_integrity["status"] = "FAIL"
    else:
        try:
            with open(result_json_path, "r") as f:
                data = json.load(f)

            if data.get("job_id") != job_id:
                msg = f"CRITICAL: result.json job_id mismatch: expected '{job_id}', got '{data.get('job_id')}'"
                logging.error(msg)
                check_json_integrity["details"].append(msg)
                critical_failures.append("result_json_integrity_mismatch")
                check_json_integrity["status"] = "FAIL"

        except json.JSONDecodeError as e:
            msg = f"CRITICAL: result.json is not valid JSON: {e}"
            logging.error(msg)
            check_json_integrity["details"].append(msg)
            critical_failures.append("result_json_integrity_decode_error")
            check_json_integrity["status"] = "FAIL"
    summary["checks"].append(check_json_integrity)

    # Finalize and write summary
    duration = time.time() - start_time
    logging.info(f"QC finished in {duration:.2f} seconds.")

    if critical_failures:
        summary["final_status"] = "FAIL"
    elif warnings:
        summary["final_status"] = "WARN"
    else:
        summary["final_status"] = "PASS"

    summary_path = log_dir / "qc_summary.json"
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)
    logging.info(f"QC summary written to {summary_path}")

    # Determine exit code based on new logic
    if critical_failures:
        logging.critical(
            f"QC failed with {len(critical_failures)} critical failures: {', '.join(critical_failures)}"
        )
        sys.exit(EXIT_FAIL)

    if warnings:
        if args.strict:
            logging.error(
                f"QC failed with {len(warnings)} warnings in strict mode: {', '.join(warnings)}"
            )
            sys.exit(EXIT_FAIL)
        else:
            logging.warning(
                f"QC passed with {len(warnings)} warnings: {', '.join(warnings)}"
            )

    logging.info("QC verification PASSED.")
    sys.exit(EXIT_PASS)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logging.critical(f"A runtime error occurred: {e}", exc_info=True)
        sys.exit(EXIT_ERROR)
