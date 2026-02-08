"""
YouTube Publisher (Dry-Run MVP)

This script implements the local-first, idempotent publishing pipeline for YouTube,
adhering to the contracts defined in ADR-0010 through ADR-0013.

It performs the following steps:
1.  Approval Gate: Checks for a valid, recent approval artifact in the inbox.
2.  Artifact Validation: Ensures the required video output exists.
3.  Idempotency Check: Prevents re-publishing content that is already posted.
4.  Payload Generation: Creates the derived distribution artifacts (youtube.json, youtube.state.json).

This MVP version defaults to a dry-run and does not perform any real network calls.
"""
import argparse
import datetime
import glob
import json
import os
import sys
import tempfile
from pathlib import Path

# Exit Codes
EXIT_SUCCESS = 0
EXIT_RUNTIME_ERROR = 1
EXIT_BLOCKED_APPROVAL = 2
EXIT_INVALID_ARTIFACTS = 3

def main():
    """Main execution function."""
    parser = argparse.ArgumentParser(description="YouTube Publishing Adapter (Dry-Run MVP)")
    parser.add_argument("--job-id", required=True, help="The job_id to process.")
    parser.add_argument("--dry-run", action=argparse.BooleanOptionalAction, default=True, help="Run in dry-run mode (no network calls).")
    parser.add_argument("--dist-root", default="sandbox/dist_artifacts", help="Root directory for distribution artifacts.")
    parser.add_argument("--inbox-root", default="sandbox/inbox", help="Root directory for inbox approvals.")
    parser.add_argument("--output-root", default="sandbox/output", help="Root directory for final job outputs.")
    parser.add_argument("--logs-root", default="sandbox/logs", help="Root directory for job logs.")
    args = parser.parse_args()

    try:
        # --- Path Setup ---
        job_id = args.job_id
        dist_root = Path(args.dist_root)
        dist_dir = dist_root / job_id
        output_dir = Path(args.output_root) / job_id
        logs_dir = Path(args.logs_root) / job_id

        payload_path = dist_dir / "youtube.json"
        state_path = dist_dir / "youtube.state.json"
        
        # --- 1. Idempotency Check (Pre-flight) ---
        if state_path.exists():
            with open(state_path, 'r') as f:
                state_data = json.load(f)
            if state_data.get("status") == "POSTED":
                print(f"Idempotency check: Job '{job_id}' already POSTED. No-op. Exiting.", file=sys.stderr)
                sys.exit(EXIT_SUCCESS)
        
        # --- 2. Approval Gate ---
        approval_glob_pattern = str(Path(args.inbox_root) / f"approve-{job_id}-youtube-*.json")
        approval_files = sorted(glob.glob(approval_glob_pattern))

        if not approval_files:
            print(f"Approval gate: FAILED. No approval files found for glob '{approval_glob_pattern}'.", file=sys.stderr)
            sys.exit(EXIT_BLOCKED_APPROVAL)

        # Deterministically select the newest file by lexicographical name
        latest_approval_file = Path(approval_files[-1])
        print(f"Approval gate: Found {len(approval_files)} approvals. Using '{latest_approval_file.name}'.", file=sys.stderr)

        with open(latest_approval_file, 'r') as f:
            approval_data = json.load(f)
        
        if not all([
            approval_data.get("job_id") == job_id,
            approval_data.get("platform") == "youtube",
            approval_data.get("approved") is True
        ]):
            print(f"Approval gate: FAILED. Approval artifact '{latest_approval_file.name}' is invalid, denied, or for wrong job/platform.", file=sys.stderr)
            sys.exit(EXIT_BLOCKED_APPROVAL)
        
        print("Approval gate: PASSED.", file=sys.stderr)
        
        # --- 3. Artifact Validation ---
        video_path = output_dir / "final.mp4"
        caption_path = output_dir / "final.srt"

        if not (video_path.exists() and video_path.stat().st_size > 0):
            print(f"Artifact validation: FAILED. Required artifact '{video_path}' not found or is empty.", file=sys.stderr)
            sys.exit(EXIT_INVALID_ARTIFACTS)
        
        if not caption_path.exists():
            print(f"Artifact validation: WARNING. Optional artifact '{caption_path}' not found.", file=sys.stderr)
            caption_path = None # Ensure it's None if not found
        
        print("Artifact validation: PASSED.", file=sys.stderr)

        # --- 4. Main Action ---
        # Read existing state for retry logic if it exists
        attempts = 0
        if state_path.exists():
            with open(state_path, 'r') as f:
                existing_state = json.load(f)
                if existing_state.get("status") == "FAILED":
                    attempts = existing_state.get("attempts", 0)
        
        # This is where the real publishing would happen
        if not args.dry_run:
            # PR9 does not implement this.
            print("ERROR: --no-dry-run is not implemented in this version.", file=sys.stderr)
            sys.exit(EXIT_RUNTIME_ERROR)

        # Prepare derived artifacts
        dist_dir.mkdir(parents=True, exist_ok=True)
        
        # Minimal metadata from job state if available
        title = f"Video for Job {job_id}"
        state_json_path = logs_dir / "state.json"
        if state_json_path.exists():
            with open(state_json_path, 'r') as f:
                job_state = json.load(f)
                # This is a speculative structure for the title
                title = job_state.get("job_details", {}).get("description", title)

        # Write youtube.json (Payload)
        payload = {
            "job_id": job_id,
            "platform": "youtube",
            "assets": {
                "video_path": str(video_path.resolve()),
                "caption_path": str(caption_path.resolve()) if caption_path else None
            },
            "metadata": {
                "title": title,
                "description": f"Content generated for job_id: {job_id}",
                "tags": ["cat-ai-factory", "ai-generated"]
            },
            "created_at": datetime.datetime.utcnow().isoformat() + "Z"
        }
        with open(payload_path, 'w') as f:
            json.dump(payload, f, indent=2)
        print(f"Wrote payload artifact to '{payload_path}'.", file=sys.stderr)

        # Write youtube.state.json (Authority) atomically
        new_state = {
            "job_id": job_id,
            "platform": "youtube",
            "status": "POSTED", # In dry-run, we simulate success
            "attempts": attempts + 1,
            "last_attempt_at": datetime.datetime.utcnow().isoformat() + "Z"
        }
        
        temp_fd, temp_name = tempfile.mkstemp(dir=dist_dir, text=True)
        with os.fdopen(temp_fd, 'w') as tf:
            json.dump(new_state, tf, indent=2)
        
        os.rename(temp_name, state_path)
        print(f"Wrote authority state artifact to '{state_path}'.", file=sys.stderr)

        # Final dry-run message
        print(f"\nDRY RUN: Would publish '{payload['metadata']['title']}' for job_id={job_id} to YouTube")
        
        sys.exit(EXIT_SUCCESS)

    except json.JSONDecodeError as e:
        print(f"Runtime error: Failed to parse JSON file. Error: {e}", file=sys.stderr)
        sys.exit(EXIT_INVALID_ARTIFACTS)
    except Exception as e:
        print(f"Unexpected runtime error: {e}", file=sys.stderr)
        sys.exit(EXIT_RUNTIME_ERROR)

if __name__ == "__main__":
    main()
