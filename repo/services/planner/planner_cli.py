from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from typing import Any, Dict, List, Optional, Tuple

from .providers import get_provider, list_providers
from .util.redact import redact_text


def _repo_root() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.normpath(os.path.join(here, "..", "..", ".."))


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
    import subprocess
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
    raw_text = ""
    if hasattr(provider, "debug_snapshot"):
        snapshot = provider.debug_snapshot()
        raw_text = snapshot.get("raw_text", "") if isinstance(snapshot, dict) else ""
        provider_name = snapshot.get("provider", provider_name)
        model = snapshot.get("model", model)
    print(f"DEBUG provider={provider_name} model={model}", file=sys.stderr)
    if raw_text:
        snippet = raw_text[:240].replace("\n", " ")
        print(
            f"DEBUG raw_text_len={len(raw_text)} raw_text_snippet={snippet}",
            file=sys.stderr,
        )
    else:
        print("DEBUG raw_text_len=0 raw_text_snippet=", file=sys.stderr)


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(description="Cat AI Factory planner CLI")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--prd", help="Path to PRD.json")
    group.add_argument("--prompt", help="A simple text prompt to generate a job from")

    parser.add_argument("--inbox", default="sandbox/inbox", help="Inbox directory (optional)")
    parser.add_argument("--out", default="sandbox/jobs", help="Output directory for job.json")
    parser.add_argument("--provider", default="ai_studio", choices=list_providers(), help="Planner provider")
    parser.add_argument("--job-id", default=None, help="Optional job_id override")
    parser.add_argument("--debug", action="store_true", help="Print safe debug info")

    args = parser.parse_args(argv)

    provider = None
    try:
        if args.prompt:
            prd = {"prompt": args.prompt}
        else:
            prd = _load_json(args.prd)

        inbox_list, inbox_with_names = _load_inbox(args.inbox)

        # PR21: Load hero registry (reference only)
        hero_registry = None
        
        # _repo_root() returns project root (directory containing 'repo' package)
        project_root = _repo_root()
        registry_path = os.path.join(project_root, "repo", "shared", "hero_registry.v1.json")
        schema_path = os.path.join(project_root, "repo", "shared", "hero_registry.v1.schema.json")
        
        # Validate existence of registry file first to avoid noise if it's plainly missing
        if os.path.exists(registry_path):
            try:
                # Ensure project root is on sys.path so `import repo...` works
                if project_root not in sys.path:
                    sys.path.insert(0, project_root)

                from repo.shared.hero_registry_validate import validate_registry_data
                
                # Single-pass load and validate
                reg_data = _load_json(registry_path)
                
                # Schema might strictly exist if registry does (co-located), but safely check
                if os.path.exists(schema_path):
                    schema_data = _load_json(schema_path)
                    is_valid, errs = validate_registry_data(reg_data, schema_data)
                    
                    if is_valid:
                        hero_registry = reg_data
                    else:
                        print(f"WARNING: Hero registry found but invalid. Proceeding without it.", file=sys.stderr)
                        # Show first few errors to avoid log noise
                        for i, e in enumerate(errs):
                            if i >= 5:
                                print(f"  ... ({len(errs) - 5} more)", file=sys.stderr)
                                break
                            print(f"  - {e}", file=sys.stderr)
                else:
                     print(f"WARNING: Hero registry schema not found at {schema_path}. Ignoring registry.", file=sys.stderr)

            except ImportError as ie:
                print(f"WARNING: Hero registry validation unavailable; ignoring registry. (Error: {ie})", file=sys.stderr)
            except Exception as ex:
                print(f"WARNING: Failed to load/validate hero registry: {ex}", file=sys.stderr)

        provider = get_provider(args.provider)
        job = provider.generate_job(prd, inbox_list, hero_registry=hero_registry)
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
