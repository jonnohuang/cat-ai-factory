from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from typing import Any, Dict, List, Optional, Tuple

from .providers import get_provider
from .util.redact import redact_text


def _repo_root() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.normpath(os.path.join(here, "..", ".."))


def _load_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_inbox(inbox_dir: str) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    if not os.path.exists(inbox_dir):
        return [], []
    if not os.path.isdir(inbox_dir):
        raise ValueError(f"Inbox path is not a directory: {inbox_dir}")

    entries: List[Tuple[str, Dict[str, Any]]] = []
    for name in sorted(os.listdir(inbox_dir)):
        if not name.endswith(".json"):
            continue
        path = os.path.join(inbox_dir, name)
        if not os.path.isfile(path):
            continue
        data = _load_json(path)
        entries.append((name, data))

    inbox_list = [item for _, item in entries]
    inbox_with_names = [{"file": name, "data": data} for name, data in entries]
    return inbox_list, inbox_with_names


def _canonical_payload(prd: Dict[str, Any], inbox_with_names: List[Dict[str, Any]]) -> str:
    payload = {"prd": prd, "inbox": inbox_with_names}
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _derive_job_id(prd: Dict[str, Any], inbox_with_names: List[Dict[str, Any]]) -> str:
    payload = _canonical_payload(prd, inbox_with_names)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"job-{digest[:12]}"


def _sanitize_job_id(value: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in value)
    safe = safe.strip("-")
    if len(safe) < 6:
        safe = f"job-{safe}" if safe else "job-000000"
    return safe


def _final_job_path(out_dir: str, job_id: str) -> str:
    base = os.path.join(out_dir, f"{job_id}.job.json")
    if not os.path.exists(base):
        return base
    version = 2
    while True:
        candidate = os.path.join(out_dir, f"{job_id}-v{version}.job.json")
        if not os.path.exists(candidate):
            return candidate
        version += 1


def _stem_from_job_path(path: str) -> str:
    name = os.path.basename(path)
    if name.endswith(".job.json"):
        return name[: -len(".job.json")]
    return os.path.splitext(name)[0]


def _validate_job(temp_path: str) -> None:
    validate_script = os.path.join(_repo_root(), "tools", "validate_job.py")
    result = subprocess.run(
        ["python3", validate_script, temp_path],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        msg = result.stderr.strip() or result.stdout.strip() or "Job validation failed"
        raise RuntimeError(msg)


def _write_job_atomic(job: Dict[str, Any], final_path: str) -> None:
    out_dir = os.path.dirname(final_path)
    os.makedirs(out_dir, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(prefix=".job-", suffix=".tmp", dir=out_dir)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(job, f, indent=2)
            f.write("\n")
        _validate_job(temp_path)
        os.replace(temp_path, final_path)
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)


def _choose_job_id(
    args_job_id: Optional[str],
    returned_job_id: Optional[str],
    prd: Dict[str, Any],
    inbox_with_names: List[Dict[str, Any]],
) -> str:
    if args_job_id:
        return _sanitize_job_id(args_job_id)
    if returned_job_id and isinstance(returned_job_id, str) and len(returned_job_id.strip()) >= 6:
        return _sanitize_job_id(returned_job_id)
    return _derive_job_id(prd, inbox_with_names)


def _print_debug(provider: Any) -> None:
    provider_name = provider.__class__.__name__
    model = getattr(provider, "model", "unknown")
    raw_len = 0

    if hasattr(provider, "debug_snapshot"):
        snapshot = provider.debug_snapshot()
        if isinstance(snapshot, dict):
            provider_name = snapshot.get("provider", provider_name)
            model = snapshot.get("model", model)
            raw_len = int(snapshot.get("raw_text_len", 0) or 0)

    print(
        f"DEBUG provider={provider_name} model={model} raw_text_len={raw_len}",
        file=sys.stderr,
    )


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(description="Cat AI Factory planner CLI")
    parser.add_argument("--prd", required=True, help="Path to PRD.json")
    parser.add_argument("--inbox", default="sandbox/inbox", help="Inbox directory (optional)")
    parser.add_argument("--out", default="sandbox/jobs", help="Output directory for job.json")
    parser.add_argument("--provider", default="gemini_ai_studio", help="Planner provider")
    parser.add_argument("--job-id", default=None, help="Optional job_id override")
    parser.add_argument("--debug", action="store_true", help="Print safe debug info")

    args = parser.parse_args(argv)

    provider = None
    try:
        prd = _load_json(args.prd)
        inbox_list, inbox_with_names = _load_inbox(args.inbox)
        provider = get_provider(args.provider)
        job = provider.plan(prd, inbox_list)
        if not isinstance(job, dict):
            raise RuntimeError("Provider returned non-object JSON")

        base_job_id = _choose_job_id(args.job_id, job.get("job_id"), prd, inbox_with_names)
        final_path = _final_job_path(args.out, base_job_id)
        stem = _stem_from_job_path(final_path)
        job["job_id"] = stem

        if args.debug and provider is not None:
            _print_debug(provider)

        _write_job_atomic(job, final_path)
        print(f"Wrote {final_path}")
        return 0
    except Exception as ex:
        if args.debug and provider is not None:
            _print_debug(provider)
        env_name = "GEMINI_" + "API" + "_" + "KEY"
        safe = redact_text(str(ex), [os.environ.get(env_name, "")])
        print(f"ERROR: {safe}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
