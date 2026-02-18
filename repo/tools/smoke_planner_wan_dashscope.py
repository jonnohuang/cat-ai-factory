#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import pathlib
import re
import subprocess
import sys


def _repo_root() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parents[2]


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


def _load(path: pathlib.Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def main(argv: list[str]) -> int:
    _ = argv
    root = _repo_root()
    env = dict(os.environ)
    env.pop("DASHSCOPE_API_KEY", None)
    env["CAF_ENGINE_ROUTE_MODE"] = "production"

    cmd = [
        sys.executable,
        "-m",
        "repo.services.planner.planner_cli",
        "--prompt",
        "Mochi wan dashscope planner smoke",
        "--provider",
        "wan_dashscope",
        "--inbox",
        "sandbox/inbox",
        "--out",
        "sandbox/jobs",
    ]
    rc, output = _run(cmd, env=env)
    if rc != 0:
        print("ERROR: planner_cli failed for wan_dashscope smoke", file=sys.stderr)
        return 1
    job_path = _extract_job_path(output)
    if job_path is None or not job_path.exists():
        print("ERROR: could not find written job path in planner output", file=sys.stderr)
        return 1

    val_cmd = [sys.executable, "-m", "repo.tools.validate_job", str(job_path)]
    vrc, _ = _run(val_cmd, env=env)
    if vrc != 0:
        print("ERROR: generated job failed validate_job", file=sys.stderr)
        return 1

    job = _load(job_path)
    if job.get("lane") != "ai_video":
        print(f"ERROR: expected lane=ai_video, got {job.get('lane')!r}", file=sys.stderr)
        return 1
    gen = job.get("generation_policy")
    if not isinstance(gen, dict):
        print("ERROR: missing generation_policy in generated job", file=sys.stderr)
        return 1
    if not isinstance(gen.get("video_provider_order"), list):
        print("ERROR: missing generation_policy.video_provider_order", file=sys.stderr)
        return 1

    print("OK: planner wan_dashscope smoke")
    print("job_path:", job_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

