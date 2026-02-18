#!/usr/bin/env python3
from __future__ import annotations

import json
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


def _load(path: pathlib.Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def main(argv: list[str]) -> int:
    _ = argv
    env = dict(os.environ)
    env["CAF_ENGINE_ROUTE_MODE"] = "production"
    env["COMFYUI_BASE_URL"] = "http://127.0.0.1:8188"
    env["COMFYUI_WORKFLOW_ID"] = "caf_dance_loop_v1"
    cmd = [
        sys.executable,
        "-m",
        "repo.services.planner.planner_cli",
        "--prompt",
        "Mochi motion contract smoke",
        "--provider",
        "comfyui_video",
        "--analysis-id",
        "dance-loop",
        "--ignore-inbox",
        "--inbox",
        "sandbox/inbox",
        "--out",
        "sandbox/jobs",
    ]
    rc, output = _run(cmd, env=env)
    if rc != 0:
        print("ERROR: planner_cli failed for motion_contract smoke", file=sys.stderr)
        return 1
    job_path = _extract_job_path(output)
    if job_path is None or not job_path.exists():
        print("ERROR: could not locate generated job path", file=sys.stderr)
        return 1

    vrc, _ = _run([sys.executable, "-m", "repo.tools.validate_job", str(job_path)], env=env)
    if vrc != 0:
        print("ERROR: generated job failed validate_job", file=sys.stderr)
        return 1

    job = _load(job_path)
    motion_contract = job.get("motion_contract")
    if not isinstance(motion_contract, dict):
        print("ERROR: missing motion_contract in generated job", file=sys.stderr)
        return 1
    relpath = motion_contract.get("relpath")
    if not isinstance(relpath, str) or not relpath.startswith("repo/"):
        print(f"ERROR: invalid motion_contract.relpath: {relpath!r}", file=sys.stderr)
        return 1
    if motion_contract.get("contract_version") != "pose_checkpoints.v1":
        print(
            f"ERROR: expected motion_contract.contract_version='pose_checkpoints.v1', got {motion_contract.get('contract_version')!r}",
            file=sys.stderr,
        )
        return 1

    gen = job.get("generation_policy")
    if isinstance(gen, dict):
        constraints = gen.get("motion_constraints", [])
        token = f"pose_contract:{relpath}"
        if isinstance(constraints, list) and constraints and token not in constraints:
            print("ERROR: expected pose_contract token in generation_policy.motion_constraints", file=sys.stderr)
            return 1

    print("OK: planner motion_contract smoke")
    print("job_path:", job_path)
    print("motion_contract_relpath:", relpath)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
