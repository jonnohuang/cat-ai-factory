#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import re
import subprocess
import sys
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional


def _repo_root() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parents[2]


def _utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _kebab(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def _run(cmd: List[str], cwd: pathlib.Path) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(cmd, cwd=str(cwd), text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    print(proc.stdout, end="")
    return proc


def _extract_job_path(output: str) -> Optional[pathlib.Path]:
    for line in reversed(output.splitlines()):
        m = re.match(r"^Wrote\s+(.+\.job\.json)\s*$", line.strip())
        if m:
            return pathlib.Path(m.group(1).strip())
    return None


def _write_json(path: pathlib.Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _read_json(path: pathlib.Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _event(
    run_doc: Dict[str, Any],
    *,
    state: str,
    step: str,
    message: str,
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    row: Dict[str, Any] = {
        "ts": _utc_now(),
        "state": state,
        "step": step,
        "message": message,
    }
    if isinstance(extra, dict) and extra:
        row.update(extra)
    events = run_doc.setdefault("events", [])
    if isinstance(events, list):
        events.append(row)
    run_doc["state"] = state
    run_doc["updated_at"] = row["ts"]


def _is_pointer_resolution_failure(output: str) -> bool:
    return "pointer resolution failed:" in output.lower()


def _comfy_reachable(base_url: str) -> bool:
    try:
        with urllib.request.urlopen(f"{base_url.rstrip('/')}/system_stats", timeout=3):
            return True
    except Exception:
        return False


def _planner_cmd(args: argparse.Namespace) -> List[str]:
    cmd = [
        sys.executable,
        "-m",
        "repo.services.planner.planner_cli",
        "--prompt",
        args.prompt,
        "--provider",
        args.provider,
        "--inbox",
        args.inbox,
        "--out",
        args.out,
    ]
    if args.analysis_id:
        cmd += ["--analysis-id", args.analysis_id]
    if args.ignore_inbox:
        cmd += ["--ignore-inbox"]
    return cmd


def _orchestrator_cmd(args: argparse.Namespace, job_path: pathlib.Path) -> List[str]:
    return [
        sys.executable,
        "-m",
        "repo.services.orchestrator.ralph_loop",
        "--job",
        str(job_path),
        "--max-retries",
        str(max(0, args.max_retries)),
        "--worker-timeout-sec",
        str(max(1, args.worker_timeout_sec)),
    ]


def _ingest_cmd(args: argparse.Namespace) -> List[str]:
    return [
        sys.executable,
        "-m",
        "repo.tools.ingest_demo_samples",
        "--incoming-dir",
        args.incoming_dir,
        "--processed-dir",
        args.processed_dir,
        "--canon-dir",
        args.canon_dir,
        "--index",
        args.analysis_index,
        "--quality-target-relpath",
        args.quality_target_relpath,
        "--continuity-pack-relpath",
        args.continuity_pack_relpath,
        "--storyboard-relpath",
        args.storyboard_relpath,
    ]


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(
        description="One-command autonomous brief run: brief -> planner resolve/bootstrap -> orchestrator -> lifecycle artifact."
    )
    parser.add_argument("--prompt", required=True, help="High-level user brief.")
    parser.add_argument("--provider", default="comfyui_video", help="Planner provider.")
    parser.add_argument("--analysis-id", default=None, help="Optional deterministic analysis_id override.")
    parser.add_argument("--inbox", default="sandbox/inbox")
    parser.add_argument("--out", default="sandbox/jobs")
    parser.add_argument("--ignore-inbox", action="store_true", help="Ignore inbox for planner context.")
    parser.add_argument("--max-retries", type=int, default=1, help="Controller max retries.")
    parser.add_argument("--worker-timeout-sec", type=int, default=900, help="Controller worker timeout.")
    parser.add_argument("--bootstrap-on-pointer-fail", action="store_true", help="Run lab bootstrap if planner pointer resolution fails.")
    parser.add_argument("--auto-start-comfy", action="store_true", help="Attempt managed Comfy start if unreachable.")
    parser.add_argument("--dry-run", action="store_true", help="Stop after planner success and lifecycle write.")

    parser.add_argument("--incoming-dir", default="sandbox/assets/demo/incoming")
    parser.add_argument("--processed-dir", default="sandbox/assets/demo/processed")
    parser.add_argument("--canon-dir", default="repo/canon/demo_analyses")
    parser.add_argument("--analysis-index", default="repo/canon/demo_analyses/video_analysis_index.v1.json")
    parser.add_argument("--quality-target-relpath", default="repo/examples/quality_target.motion_strict.v1.example.json")
    parser.add_argument("--continuity-pack-relpath", default="repo/examples/episode_continuity_pack.v1.example.json")
    parser.add_argument("--storyboard-relpath", default="repo/examples/storyboard.v1.example.json")

    args = parser.parse_args(argv)
    root = _repo_root()

    run_id = f"autonomous-brief-{_kebab(args.prompt)[:48] or 'run'}-{int(dt.datetime.now().timestamp())}"
    lifecycle_path = root / "sandbox" / "logs" / "lab" / "autonomous_brief_runs" / f"{run_id}.autonomous_brief_run.v1.json"
    run_doc: Dict[str, Any] = {
        "version": "autonomous_brief_run.v1",
        "run_id": run_id,
        "prompt": args.prompt,
        "provider": args.provider,
        "state": "INIT",
        "created_at": _utc_now(),
        "updated_at": _utc_now(),
        "job_relpath": None,
        "job_id": None,
        "events": [],
    }
    _event(run_doc, state="PLANNER_START", step="planner", message="Running planner for brief.")
    _write_json(lifecycle_path, run_doc)

    if args.provider.strip().lower() == "comfyui_video":
        base_url = "http://127.0.0.1:8188"
        raw = str(os.environ.get("COMFYUI_BASE_URL", "")).strip()
        if raw:
            base_url = raw
        if not _comfy_reachable(base_url):
            if args.auto_start_comfy:
                _event(
                    run_doc,
                    state="COMFY_START",
                    step="preflight",
                    message="ComfyUI unreachable; starting managed runtime.",
                    extra={"comfy_base_url": base_url},
                )
                _write_json(lifecycle_path, run_doc)
                start_proc = _run([sys.executable, "-m", "repo.tools.manage_comfy_runtime", "start"], root)
                if start_proc.returncode != 0 or not _comfy_reachable(base_url):
                    _event(
                        run_doc,
                        state="FAILED_PREFLIGHT",
                        step="preflight",
                        message="ComfyUI preflight failed after auto-start attempt.",
                        extra={"comfy_base_url": base_url, "start_exit_code": start_proc.returncode},
                    )
                    _write_json(lifecycle_path, run_doc)
                    return 2
            else:
                _event(
                    run_doc,
                    state="FAILED_PREFLIGHT",
                    step="preflight",
                    message="ComfyUI unreachable. Pass --auto-start-comfy or start runtime manually.",
                    extra={"comfy_base_url": base_url},
                )
                _write_json(lifecycle_path, run_doc)
                return 2

    planner_proc = _run(_planner_cmd(args), root)
    planner_out = planner_proc.stdout or ""
    if planner_proc.returncode != 0:
        if args.bootstrap_on_pointer_fail and _is_pointer_resolution_failure(planner_out):
            _event(
                run_doc,
                state="BOOTSTRAP_START",
                step="bootstrap",
                message="Planner pointer resolution failed; running lab bootstrap ingest.",
            )
            _write_json(lifecycle_path, run_doc)
            ingest_proc = _run(_ingest_cmd(args), root)
            if ingest_proc.returncode != 0:
                _event(
                    run_doc,
                    state="FAILED_BOOTSTRAP",
                    step="bootstrap",
                    message="Lab bootstrap ingest failed.",
                    extra={"bootstrap_exit_code": ingest_proc.returncode},
                )
                _write_json(lifecycle_path, run_doc)
                return ingest_proc.returncode

            _event(run_doc, state="PLANNER_RETRY", step="planner", message="Retrying planner after bootstrap ingest.")
            _write_json(lifecycle_path, run_doc)
            planner_proc = _run(_planner_cmd(args), root)
            planner_out = planner_proc.stdout or ""

        if planner_proc.returncode != 0:
            _event(
                run_doc,
                state="FAILED_PLANNER",
                step="planner",
                message="Planner failed.",
                extra={"planner_exit_code": planner_proc.returncode},
            )
            _write_json(lifecycle_path, run_doc)
            return planner_proc.returncode

    job_path = _extract_job_path(planner_out)
    if job_path is None:
        _event(run_doc, state="FAILED_PLANNER_NO_JOB", step="planner", message="Planner succeeded but no job path emitted.")
        _write_json(lifecycle_path, run_doc)
        return 1
    if not job_path.is_absolute():
        job_path = (root / job_path).resolve()
    if not job_path.exists():
        _event(run_doc, state="FAILED_MISSING_JOB", step="planner", message=f"Planner job file missing: {job_path}")
        _write_json(lifecycle_path, run_doc)
        return 1

    job_rel = str(job_path.resolve().relative_to(root.resolve())).replace("\\", "/")
    job_payload = _read_json(job_path) or {}
    job_id = str(job_payload.get("job_id") or job_path.name.replace(".job.json", ""))
    run_doc["job_relpath"] = job_rel
    run_doc["job_id"] = job_id
    _event(run_doc, state="PLANNER_DONE", step="planner", message="Planner completed and job contract written.")
    _write_json(lifecycle_path, run_doc)

    if args.dry_run:
        _event(run_doc, state="COMPLETED_DRY_RUN", step="runner", message="Dry run complete; orchestrator skipped.")
        _write_json(lifecycle_path, run_doc)
        print(f"Wrote {lifecycle_path}")
        return 0

    _event(run_doc, state="ORCHESTRATOR_START", step="orchestrator", message="Running Ralph loop.")
    _write_json(lifecycle_path, run_doc)
    orch_proc = _run(_orchestrator_cmd(args, job_path), root)
    if orch_proc.returncode != 0:
        _event(
            run_doc,
            state="FAILED_ORCHESTRATOR",
            step="orchestrator",
            message="Ralph loop failed.",
            extra={"orchestrator_exit_code": orch_proc.returncode},
        )
        _write_json(lifecycle_path, run_doc)
        return orch_proc.returncode

    _event(
        run_doc,
        state="COMPLETED",
        step="orchestrator",
        message="Autonomous brief run completed.",
        extra={
            "state_relpath": f"sandbox/logs/{job_id}/state.json",
            "quality_decision_relpath": f"sandbox/logs/{job_id}/qc/quality_decision.v1.json",
            "result_relpath": f"sandbox/output/{job_id}/result.json",
        },
    )
    _write_json(lifecycle_path, run_doc)
    print(f"Wrote {lifecycle_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
