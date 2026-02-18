#!/usr/bin/env python3
from __future__ import annotations

import os
import pathlib
import re
import subprocess
import sys


def _run(cmd: list[str], *, env: dict[str, str]) -> tuple[int, str]:
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env)
    out = p.stdout or ""
    print(out, end="")
    return p.returncode, out


def _extract_job_path(output: str) -> pathlib.Path | None:
    m = re.search(r"Wrote\s+(.+\.job\.json)", output)
    if not m:
        return None
    return pathlib.Path(m.group(1).strip())


def main(argv: list[str]) -> int:
    _ = argv
    env = dict(os.environ)
    env["CAF_ENGINE_ROUTE_MODE"] = "production"
    env["COMFYUI_WORKFLOW_ID"] = "caf_dance_loop_v1"
    cmd = [
        sys.executable,
        "-m",
        "repo.services.planner.planner_cli",
        "--prompt",
        "Mochi comfyui provider smoke",
        "--provider",
        "comfyui_video",
        "--inbox",
        "sandbox/inbox",
        "--out",
        "sandbox/jobs",
    ]
    rc, output = _run(cmd, env=env)
    if rc != 0:
        print("ERROR: planner_cli failed for comfyui provider smoke", file=sys.stderr)
        return 1
    job_path = _extract_job_path(output)
    if job_path is None or not job_path.exists():
        print("ERROR: could not locate generated job path", file=sys.stderr)
        return 1
    vrc, _ = _run([sys.executable, "-m", "repo.tools.validate_job", str(job_path)], env=env)
    if vrc != 0:
        print("ERROR: generated comfyui job failed validate_job", file=sys.stderr)
        return 1
    print("OK: planner comfyui provider smoke")
    print("job_path:", job_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
