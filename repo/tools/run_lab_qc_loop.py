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
from typing import Any, Dict, List, Optional


def _repo_root() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parents[2]


def _utc_now() -> str:
    return (
        dt.datetime.now(dt.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _run(
    cmd: List[str], *, cwd: pathlib.Path, env: Dict[str, str]
) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(
        cmd,
        cwd=str(cwd),
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    print(proc.stdout, end="")
    return proc


def _extract_job_path(output: str) -> Optional[pathlib.Path]:
    for line in reversed(output.splitlines()):
        m = re.match(r"^Wrote\s+(.+\.job\.json)\s*$", line.strip())
        if m:
            return pathlib.Path(m.group(1).strip())
    return None


def _load_json(path: pathlib.Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _write_json(path: pathlib.Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _read_qc_action(repo_root: pathlib.Path, job_id: str) -> tuple[str, str]:
    decision_path = (
        repo_root / "sandbox" / "logs" / job_id / "qc" / "quality_decision.v1.json"
    )
    payload = _load_json(decision_path) or {}
    decision = (
        payload.get("decision") if isinstance(payload.get("decision"), dict) else {}
    )
    action = str(decision.get("action", "unknown"))
    reason = str(decision.get("reason", ""))
    return action, reason


def _parse_providers(single_provider: str, providers_csv: str) -> List[str]:
    names: List[str] = []
    if providers_csv.strip():
        for raw in providers_csv.split(","):
            name = raw.strip()
            if name and name not in names:
                names.append(name)
    else:
        names.append(single_provider.strip() or "vertex_veo")
    return names


def _action_score(action: str) -> int:
    # Lower is better.
    scores = {
        "proceed_finalize": 0,
        "retry_motion": 1,
        "retry_recast": 2,
        "escalate_hitl": 3,
        "block_for_costume": 4,
        "unknown": 5,
    }
    return scores.get(action, 6)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Run bounded autonomous lab QC loop (planner + controller)."
    )
    parser.add_argument(
        "--prompt", required=True, help="Planner prompt for this lab run."
    )
    parser.add_argument(
        "--provider",
        default="vertex_veo",
        help="Planner provider (e.g., vertex_veo, wan_dashscope).",
    )
    parser.add_argument(
        "--providers",
        default="",
        help="Comma-separated provider matrix (e.g., vertex_veo,wan_dashscope,sora_lab,meta_ai_lab).",
    )
    parser.add_argument("--inbox", default="sandbox/inbox", help="Planner inbox path.")
    parser.add_argument(
        "--out", default="sandbox/jobs", help="Planner jobs output directory."
    )
    parser.add_argument(
        "--max-attempts", type=int, default=5, help="Max controller loop attempts."
    )
    parser.add_argument(
        "--max-retries", type=int, default=2, help="Controller max retries per run."
    )
    parser.add_argument(
        "--route-mode",
        choices=["production", "lab"],
        default=os.environ.get("CAF_ENGINE_ROUTE_MODE", "lab"),
        help="Engine route mode for this run.",
    )
    parser.add_argument(
        "--authority-trial",
        action="store_true",
        help="Enable guarded authority trial (sets CAF_QC_AUTHORITY_TRIAL=1 for subprocesses).",
    )
    args = parser.parse_args(argv[1:])

    root = _repo_root()
    env = dict(os.environ)
    env["CAF_ENGINE_ROUTE_MODE"] = args.route_mode
    if args.authority_trial:
        env["CAF_QC_AUTHORITY_TRIAL"] = "1"

    provider_list = _parse_providers(args.provider, args.providers)
    terminal_actions = {"proceed_finalize", "block_for_costume", "escalate_hitl"}
    run_summaries: List[Dict[str, Any]] = []

    for provider_name in provider_list:
        planner_cmd = [
            sys.executable,
            "-m",
            "repo.services.planner.planner_cli",
            "--prompt",
            args.prompt,
            "--provider",
            provider_name,
            "--inbox",
            args.inbox,
            "--out",
            args.out,
        ]
        planner_proc = _run(planner_cmd, cwd=root, env=env)
        if planner_proc.returncode != 0:
            run_summaries.append(
                {
                    "provider": provider_name,
                    "status": "planner_failed",
                    "controller_exit_code": planner_proc.returncode,
                    "attempts": [],
                }
            )
            continue

        job_path = _extract_job_path(planner_proc.stdout)
        if job_path is None:
            run_summaries.append(
                {
                    "provider": provider_name,
                    "status": "planner_no_job_path",
                    "attempts": [],
                }
            )
            continue
        if not job_path.is_absolute():
            job_path = (root / job_path).resolve()
        if not job_path.exists():
            run_summaries.append(
                {
                    "provider": provider_name,
                    "status": "planner_missing_job",
                    "attempts": [],
                }
            )
            continue

        job_payload = _load_json(job_path)
        job_id = str(job_payload.get("job_id")) if isinstance(job_payload, dict) else ""
        if not job_id:
            run_summaries.append(
                {
                    "provider": provider_name,
                    "status": "planner_missing_job_id",
                    "attempts": [],
                }
            )
            continue

        attempt_rows: List[Dict[str, Any]] = []
        final_status = "max_attempts_reached"
        for idx in range(1, max(1, args.max_attempts) + 1):
            print(
                f"INFO lab_loop provider={provider_name} attempt={idx}/{args.max_attempts} job_id={job_id}"
            )
            ctrl_cmd = [
                sys.executable,
                "-m",
                "repo.services.orchestrator.ralph_loop",
                "--job",
                str(job_path),
                "--max-retries",
                str(max(0, args.max_retries)),
            ]
            ctrl_proc = _run(ctrl_cmd, cwd=root, env=env)
            action, reason = _read_qc_action(root, job_id)
            row = {
                "attempt": idx,
                "controller_exit_code": ctrl_proc.returncode,
                "quality_action": action,
                "quality_reason": reason,
                "ts": _utc_now(),
            }
            attempt_rows.append(row)

            if action in terminal_actions:
                final_status = f"terminal_action:{action}"
                break
            if action in {"retry_motion", "retry_recast"}:
                continue
            if ctrl_proc.returncode != 0:
                final_status = "controller_failed_without_quality_action"
                break

        run_summaries.append(
            {
                "provider": provider_name,
                "job_id": job_id,
                "job_relpath": str(
                    job_path.resolve().relative_to(root.resolve())
                ).replace("\\", "/"),
                "status": final_status,
                "attempts": attempt_rows,
            }
        )

    ranked_runs = sorted(
        run_summaries,
        key=lambda r: (
            _action_score(
                str((r.get("attempts") or [{}])[-1].get("quality_action", "unknown"))
                if r.get("attempts")
                else "unknown"
            ),
            len(r.get("attempts", [])),
            str(r.get("provider", "")),
        ),
    )
    best_run = ranked_runs[0] if ranked_runs else {}
    best_job_id = str(best_run.get("job_id", ""))
    summary = {
        "version": "lab_qc_loop_summary.v1",
        "generated_at": _utc_now(),
        "settings": {
            "providers": provider_list,
            "prompt": args.prompt,
            "max_attempts": max(1, args.max_attempts),
            "max_retries": max(0, args.max_retries),
            "route_mode": args.route_mode,
            "authority_trial": args.authority_trial,
        },
        "best_provider": best_run.get("provider"),
        "best_job_id": best_job_id,
        "runs": run_summaries,
    }

    if best_job_id:
        out_path = (
            root
            / "sandbox"
            / "logs"
            / best_job_id
            / "qc"
            / "lab_qc_loop_summary.v1.json"
        )
    else:
        out_path = root / "sandbox" / "logs" / "lab_qc_loop_summary.v1.json"
    _write_json(out_path, summary)
    print(f"Wrote {out_path}")
    print(f"INFO lab_loop best_provider={best_run.get('provider', 'none')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
