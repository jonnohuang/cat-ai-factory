from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
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
    validate_script = os.path.join(_repo_root(), "repo", "tools", "validate_job.py")
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


def _kebab(value: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return value


def _load_video_analysis_selection(project_root: str, prd: Dict[str, Any], inbox_list: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    index_path = os.path.join(project_root, "repo", "canon", "demo_analyses", "video_analysis_index.v1.json")
    if not os.path.exists(index_path):
        return None
    try:
        index_data = _load_json(index_path)
        analyses = index_data.get("analyses", [])
        if not isinstance(analyses, list) or not analyses:
            return None

        context_blob = json.dumps({"prd": prd, "inbox": inbox_list}, sort_keys=True, ensure_ascii=True).lower()
        is_dance_context = any(tok in context_blob for tok in ("dance", "loop", "choreo", "groove", "beat"))

        ranked: List[Tuple[int, int, Dict[str, Any]]] = []
        for item in analyses:
            if not isinstance(item, dict):
                continue
            tags = [str(t).lower() for t in item.get("tags", []) if isinstance(t, str)]
            lane_hints = [str(x) for x in item.get("lane_hints", []) if isinstance(x, str)]
            score = 0
            for tag in tags:
                if tag and tag in context_blob:
                    score += 3
                parts = [p for p in tag.split("-") if p]
                if parts and any(p in context_blob for p in parts):
                    score += 1
            if is_dance_context and any(x in ("dance_swap", "template_remix", "image_motion") for x in lane_hints):
                score += 3
            priority = int(item.get("priority", 0))
            ranked.append((score, priority, item))
        if not ranked:
            return None
        ranked.sort(key=lambda row: (-row[0], -row[1], str(row[2].get("analysis_id", ""))))
        selected = ranked[0][2]
        relpath = selected.get("relpath")
        if not isinstance(relpath, str) or not relpath:
            return None
        analysis_path = os.path.join(project_root, relpath)
        if not os.path.exists(analysis_path):
            return None
        analysis_data = _load_json(analysis_path)
        if not isinstance(analysis_data, dict):
            return None
        return analysis_data
    except Exception as ex:
        print(f"WARNING: Failed to load planner video analysis references: {ex}", file=sys.stderr)
        return None


def _apply_video_analysis_hints(job: Dict[str, Any], analysis: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(job, dict) or not isinstance(analysis, dict):
        return job

    pattern = analysis.get("pattern", {})
    if not isinstance(pattern, dict):
        return job

    lane_hints = pattern.get("lane_hints", [])
    if not job.get("lane") and isinstance(lane_hints, list):
        for lane in lane_hints:
            if lane in ("ai_video", "image_motion", "template_remix", "dance_swap"):
                job["lane"] = lane
                break

    looping = pattern.get("looping", {})
    choreography = pattern.get("choreography", {})
    if not isinstance(looping, dict) or not isinstance(choreography, dict):
        return job

    loop_end = looping.get("loop_end_sec")
    beats = choreography.get("beats", [])
    shots = job.get("shots", [])
    video = job.get("video", {})
    if not isinstance(shots, list) or not isinstance(video, dict):
        return job
    if not isinstance(loop_end, (int, float)) or loop_end <= 0:
        return job
    if not isinstance(beats, list) or not beats:
        return job

    beat_norms: List[float] = []
    for beat in beats:
        if not isinstance(beat, dict):
            continue
        start = beat.get("start_sec")
        if isinstance(start, (int, float)) and 0 <= start < loop_end:
            beat_norms.append(float(start) / float(loop_end))
    if not beat_norms:
        return job
    beat_norms = sorted(set(beat_norms + [1.0]))

    length_seconds = int(video.get("length_seconds", 15))
    max_t = max(0, length_seconds - 1)
    count = len(shots)
    if count <= 0:
        return job

    prev_t = -1
    for i, shot in enumerate(shots):
        if not isinstance(shot, dict):
            continue
        target = float(i) / float(max(1, count - 1))
        snap = min(beat_norms, key=lambda n: abs(n - target))
        t = int(round(snap * max_t))
        if t < prev_t:
            t = prev_t
        shot["t"] = min(max(0, t), 60)
        prev_t = shot["t"]

    tags = pattern.get("tags", [])
    if isinstance(tags, list):
        current = [h for h in job.get("hashtags", []) if isinstance(h, str)]
        seen = set(current)
        for raw in tags:
            if not isinstance(raw, str):
                continue
            kebab = _kebab(raw)
            if not kebab:
                continue
            tag = f"#{kebab.replace('-', '_')}"
            if tag in seen:
                continue
            if len(current) >= 20:
                break
            current.append(tag)
            seen.add(tag)
        if current:
            job["hashtags"] = current
    return job


def _safe_rel(path: str, project_root: str) -> str:
    rel = os.path.relpath(path, project_root).replace("\\", "/")
    return rel


def _load_json_if_exists(path: str) -> Optional[Dict[str, Any]]:
    if not os.path.exists(path):
        return None
    try:
        data = _load_json(path)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _latest_matching_file(base_dir: str, filename: str) -> Optional[str]:
    matches: List[str] = []
    if not os.path.isdir(base_dir):
        return None
    for root, _dirs, files in os.walk(base_dir):
        if filename in files:
            matches.append(os.path.join(root, filename))
    if not matches:
        return None
    matches.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    return matches[0]


def _load_quality_context(project_root: str, selected_analysis: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    ctx: Dict[str, Any] = {}

    if selected_analysis:
        ctx["video_analysis"] = {
            "analysis_id": selected_analysis.get("analysis_id"),
            "duration_bucket": selected_analysis.get("pattern", {}).get("duration_bucket"),
            "lane_hints": selected_analysis.get("pattern", {}).get("lane_hints", []),
            "tags": selected_analysis.get("pattern", {}).get("tags", []),
            "looping": selected_analysis.get("pattern", {}).get("looping", {}),
            "beat_count": len(selected_analysis.get("pattern", {}).get("choreography", {}).get("beats", []) or []),
        }

    bench_report_path = os.path.join(
        project_root, "sandbox", "logs", "benchmarks", "recast-regression-smoke", "recast_benchmark_report.v1.json"
    )
    bench = _load_json_if_exists(bench_report_path)
    if bench:
        summary = bench.get("summary", {})
        cases = bench.get("cases", [])
        hitl_score = None
        baseline_score = None
        if isinstance(cases, list):
            for item in cases:
                if not isinstance(item, dict):
                    continue
                case_id = str(item.get("case_id", ""))
                score = item.get("overall_score")
                if case_id == "hitl-viggle-output":
                    hitl_score = score
                elif case_id == "baseline-worker-output":
                    baseline_score = score
        ctx["recast_benchmark"] = {
            "relpath": _safe_rel(bench_report_path, project_root),
            "avg_overall_score": summary.get("avg_overall_score"),
            "all_pass": summary.get("all_pass"),
            "hitl_score": hitl_score,
            "baseline_score": baseline_score,
        }

    latest_quality = _latest_matching_file(os.path.join(project_root, "sandbox", "logs"), "recast_quality_report.v1.json")
    if latest_quality:
        qual = _load_json_if_exists(latest_quality)
        if qual:
            overall = qual.get("overall", {})
            ctx["latest_quality_gate"] = {
                "relpath": _safe_rel(latest_quality, project_root),
                "overall_score": overall.get("score"),
                "overall_pass": overall.get("pass"),
                "failed_metrics": overall.get("failed_metrics", []),
            }

    latest_render_manifest = _latest_matching_file(os.path.join(project_root, "sandbox", "output"), "render_manifest.v1.json")
    if latest_render_manifest:
        render = _load_json_if_exists(latest_render_manifest) or {}
        root_dir = os.path.dirname(os.path.dirname(latest_render_manifest))
        frame_p = os.path.join(root_dir, "frames", "frame_manifest.v1.json")
        audio_p = os.path.join(root_dir, "audio", "audio_manifest.v1.json")
        timeline_p = os.path.join(root_dir, "edit", "timeline.v1.json")
        frame = _load_json_if_exists(frame_p) or {}
        audio = _load_json_if_exists(audio_p) or {}
        timeline = _load_json_if_exists(timeline_p) or {}
        ctx["media_stack"] = {
            "output_root": _safe_rel(root_dir, project_root),
            "render_manifest": _safe_rel(latest_render_manifest, project_root),
            "frame_count": frame.get("frame_count"),
            "has_audio_mix": bool(audio.get("mix_audio_relpath")),
            "timeline_segments": len(timeline.get("segments", []) or []),
            "final_duration_sec": render.get("output", {}).get("duration_sec"),
        }
    return ctx


def _apply_quality_policy_hints(job: Dict[str, Any], quality_context: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(job, dict):
        return job
    bench = quality_context.get("recast_benchmark")
    if not isinstance(bench, dict):
        return job
    all_pass = bench.get("all_pass")
    if all_pass is False and job.get("lane") == "dance_swap":
        job.pop("lane", None)
        job.pop("dance_swap", None)
        script = job.get("script")
        if isinstance(script, dict):
            ending = str(script.get("ending", "")).strip()
            suffix = " (external recast HITL recommended)."
            if ending:
                if ending.endswith("."):
                    ending = ending[:-1]
                max_base = max(0, 120 - len(suffix))
                ending = ending[:max_base].rstrip()
                script["ending"] = f"{ending}{suffix}" if ending else "External recast HITL recommended."
            else:
                script["ending"] = "External recast HITL recommended."
            if len(script["ending"]) > 120:
                script["ending"] = script["ending"][:120].rstrip()
    return job


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
        video_analysis = _load_video_analysis_selection(project_root, prd, inbox_list)
        quality_context = _load_quality_context(project_root, video_analysis)

        job = provider.generate_job(
            prd,
            inbox_list,
            hero_registry=hero_registry,
            quality_context=quality_context,
        )
        if not isinstance(job, dict):
            raise RuntimeError("Provider returned non-object JSON")

        if video_analysis is not None:
            job = _apply_video_analysis_hints(job, video_analysis)
            selected_id = video_analysis.get("analysis_id")
            if isinstance(selected_id, str) and selected_id:
                print(f"INFO planner video_analysis_applied={selected_id}", file=sys.stderr)
        job = _apply_quality_policy_hints(job, quality_context)

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
