#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import pathlib
import re
import subprocess
import sys
import urllib.error
import urllib.request


def _run(cmd: list[str], cwd: pathlib.Path) -> tuple[int, str]:
    p = subprocess.run(cmd, cwd=str(cwd), text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    out = p.stdout or ""
    print(out, end="")
    return p.returncode, out


def _extract_job_path(output: str) -> pathlib.Path | None:
    m = re.search(r"Wrote\s+(.+\.job\.json)", output)
    if not m:
        return None
    return pathlib.Path(m.group(1).strip())


def _repo_root() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parents[2]


def _comfy_reachable(base_url: str) -> bool:
    try:
        with urllib.request.urlopen(f"{base_url.rstrip('/')}/system_stats", timeout=3):
            return True
    except Exception:
        return False


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="One-command Comfy planner+orchestrator runner pinned to demo dance-loop analysis."
    )
    parser.add_argument("--prompt", required=True, help="User brief/prompt")
    parser.add_argument("--provider", default="comfyui_video", help="Planner provider (default: comfyui_video)")
    parser.add_argument("--analysis-id", default="dance-loop", help="Analysis id (default: dance-loop)")
    parser.add_argument("--inbox", default="sandbox/inbox")
    parser.add_argument("--out", default="sandbox/jobs")
    parser.add_argument("--max-retries", type=int, default=0)
    parser.add_argument("--worker-timeout-sec", type=int, default=300)
    parser.add_argument("--auto-start-comfy", action="store_true", help="Attempt CAF-managed Comfy start if unreachable.")
    parser.add_argument(
        "--allow-inbox",
        action="store_true",
        help="Allow planner inbox auto-resolution. Default is ignore inbox for deterministic analysis-id pinning.",
    )
    args = parser.parse_args(argv)

    root = _repo_root()
    base_url = os.environ.get("COMFYUI_BASE_URL", "http://127.0.0.1:8188").strip() or "http://127.0.0.1:8188"
    if not _comfy_reachable(base_url):
        if args.auto_start_comfy:
            rc, _ = _run([sys.executable, "-m", "repo.tools.manage_comfy_runtime", "start"], root)
            if rc != 0 or not _comfy_reachable(base_url):
                print(
                    "ERROR: ComfyUI still unreachable after auto-start. "
                    "Run: python3 -m repo.tools.manage_comfy_runtime status",
                    file=sys.stderr,
                )
                return 2
        else:
            print(
                "ERROR: ComfyUI is unreachable. "
                "Run `python3 -m repo.tools.manage_comfy_runtime start` or pass --auto-start-comfy.",
                file=sys.stderr,
            )
            return 2

    planner_cmd = [
        sys.executable,
        "-m",
        "repo.services.planner.planner_cli",
        "--prompt",
        args.prompt,
        "--provider",
        args.provider,
        "--analysis-id",
        args.analysis_id,
        "--inbox",
        args.inbox,
        "--out",
        args.out,
    ]
    if not args.allow_inbox:
        planner_cmd.append("--ignore-inbox")

    rc, planner_out = _run(planner_cmd, root)
    if rc != 0:
        print("ERROR: planner failed", file=sys.stderr)
        return rc

    job_path = _extract_job_path(planner_out)
    if job_path is None:
        print("ERROR: planner did not emit job path", file=sys.stderr)
        return 1
    if not job_path.is_absolute():
        job_path = (root / job_path).resolve()
    if not job_path.exists():
        print(f"ERROR: job file missing: {job_path}", file=sys.stderr)
        return 1

    orch_cmd = [
        sys.executable,
        "-m",
        "repo.services.orchestrator.ralph_loop",
        "--job",
        str(job_path),
        "--max-retries",
        str(args.max_retries),
        "--worker-timeout-sec",
        str(args.worker_timeout_sec),
    ]
    rc, _ = _run(orch_cmd, root)

    job_id = job_path.name.replace(".job.json", "")
    print(f"job_path: {job_path}")
    print(f"job_id: {job_id}")
    print(f"state_path: sandbox/logs/{job_id}/state.json")
    print(f"video_path: sandbox/output/{job_id}/final.mp4")
    print(f"result_path: sandbox/output/{job_id}/result.json")
    return rc


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
