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
from .util.engine_routing import route_engine_policy
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


def _load_video_analysis_selection(
    project_root: str,
    prd: Dict[str, Any],
    inbox_list: List[Dict[str, Any]],
    forced_analysis_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    index_path = os.path.join(project_root, "repo", "canon", "demo_analyses", "video_analysis_index.v1.json")
    if not os.path.exists(index_path):
        return None
    try:
        index_data = _load_json(index_path)
        analyses = index_data.get("analyses", [])
        if not isinstance(analyses, list) or not analyses:
            return None

        if isinstance(forced_analysis_id, str) and forced_analysis_id.strip():
            target_id = forced_analysis_id.strip()
            for item in analyses:
                if not isinstance(item, dict):
                    continue
                if str(item.get("analysis_id", "")).strip() != target_id:
                    continue
                relpath = item.get("relpath")
                if not isinstance(relpath, str) or not relpath:
                    raise RuntimeError(f"analysis_id={target_id} missing relpath in index")
                analysis_path = os.path.join(project_root, relpath)
                if not os.path.exists(analysis_path):
                    raise RuntimeError(f"analysis_id={target_id} relpath not found: {relpath}")
                analysis_data = _load_json(analysis_path)
                if not isinstance(analysis_data, dict):
                    raise RuntimeError(f"analysis_id={target_id} relpath unreadable JSON: {relpath}")
                return analysis_data
            raise RuntimeError(f"analysis_id not found in index: {target_id}")

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


def _find_contract_docs(
    project_root: str,
    version_name: str,
    analysis_id: Optional[str],
) -> List[Tuple[str, Dict[str, Any]]]:
    candidates: List[Tuple[str, Dict[str, Any]]] = []
    search_dirs = [
        os.path.join(project_root, "repo", "canon", "demo_analyses"),
        os.path.join(project_root, "repo", "examples"),
    ]
    for base in search_dirs:
        if not os.path.isdir(base):
            continue
        for root, _dirs, files in os.walk(base):
            for name in sorted(files):
                if not name.endswith(".json"):
                    continue
                p = os.path.join(root, name)
                doc = _load_json_if_exists(p)
                if not isinstance(doc, dict):
                    continue
                if doc.get("version") != version_name:
                    continue
                if analysis_id and doc.get("analysis_id") == analysis_id:
                    candidates.append((p, doc))
                elif not analysis_id:
                    candidates.append((p, doc))
    def _sort_key(row: Tuple[str, Dict[str, Any]]) -> Tuple[int, float, str]:
        path = row[0]
        rel = _safe_rel(path, project_root)
        # Prefer canon artifacts over examples when both exist.
        is_example = 1 if rel.startswith("repo/examples/") else 0
        try:
            mtime = os.path.getmtime(path)
        except Exception:
            mtime = 0.0
        # Newer artifacts first within the same source bucket.
        return (is_example, -mtime, rel)

    candidates.sort(key=_sort_key)
    return candidates


def _select_reverse_contracts(project_root: str, selected_analysis: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    analysis_id = None
    if isinstance(selected_analysis, dict):
        aid = selected_analysis.get("analysis_id")
        if isinstance(aid, str) and aid:
            analysis_id = aid

    result: Dict[str, Any] = {
        "analysis_id": analysis_id,
        "reverse_prompt": None,
        "beat_grid": None,
        "pose_checkpoints": None,
        "keyframe_checkpoints": None,
    }

    reverse_rows = _find_contract_docs(project_root, "caf.video_reverse_prompt.v1", analysis_id)
    beat_rows = _find_contract_docs(project_root, "beat_grid.v1", analysis_id)
    pose_rows = _find_contract_docs(project_root, "pose_checkpoints.v1", analysis_id)
    keyframe_rows = _find_contract_docs(project_root, "keyframe_checkpoints.v1", analysis_id)

    if reverse_rows:
        path, doc = reverse_rows[0]
        result["reverse_prompt"] = {"relpath": _safe_rel(path, project_root), "data": doc}
    if beat_rows:
        path, doc = beat_rows[0]
        result["beat_grid"] = {"relpath": _safe_rel(path, project_root), "data": doc}
    if pose_rows:
        path, doc = pose_rows[0]
        result["pose_checkpoints"] = {"relpath": _safe_rel(path, project_root), "data": doc}
    if keyframe_rows:
        path, doc = keyframe_rows[0]
        result["keyframe_checkpoints"] = {"relpath": _safe_rel(path, project_root), "data": doc}
    return result


def _extract_reverse_timestamps(reverse_contracts: Dict[str, Any]) -> List[float]:
    times: List[float] = []

    reverse_prompt = reverse_contracts.get("reverse_prompt", {})
    if isinstance(reverse_prompt, dict):
        data = reverse_prompt.get("data", {})
        if isinstance(data, dict):
            truth = data.get("truth", {})
            if isinstance(truth, dict):
                for shot in truth.get("shots", []):
                    if not isinstance(shot, dict):
                        continue
                    for key in ("start_sec", "end_sec"):
                        v = shot.get(key)
                        if isinstance(v, (int, float)) and v >= 0:
                            times.append(float(v))

    beat_grid = reverse_contracts.get("beat_grid", {})
    if isinstance(beat_grid, dict):
        data = beat_grid.get("data", {})
        if isinstance(data, dict):
            for beat in data.get("beats", []):
                if not isinstance(beat, dict):
                    continue
                t = beat.get("t_sec")
                if isinstance(t, (int, float)) and t >= 0:
                    times.append(float(t))

    pose_doc = reverse_contracts.get("pose_checkpoints", {})
    if isinstance(pose_doc, dict):
        data = pose_doc.get("data", {})
        if isinstance(data, dict):
            for cp in data.get("checkpoints", []):
                if not isinstance(cp, dict):
                    continue
                t = cp.get("t_sec")
                if isinstance(t, (int, float)) and t >= 0:
                    times.append(float(t))

    keyframe_doc = reverse_contracts.get("keyframe_checkpoints", {})
    if isinstance(keyframe_doc, dict):
        data = keyframe_doc.get("data", {})
        if isinstance(data, dict):
            for cp in data.get("keyframes", []):
                if not isinstance(cp, dict):
                    continue
                t = cp.get("t_sec")
                if isinstance(t, (int, float)) and t >= 0:
                    times.append(float(t))

    # Deterministic dedupe with rounded precision.
    unique = sorted({round(t, 3) for t in times})
    return [float(v) for v in unique]


def _select_segment_stitch_plan(project_root: str, analysis_id: Optional[str]) -> Optional[Dict[str, Any]]:
    rows = _find_contract_docs(project_root, "segment_stitch_plan.v1", analysis_id)
    if not rows:
        return None
    path, doc = rows[0]
    return {"relpath": _safe_rel(path, project_root), "data": doc}


def _select_continuity_pack(project_root: str, analysis_id: Optional[str]) -> Optional[Dict[str, Any]]:
    rows = _find_contract_docs(project_root, "episode_continuity_pack.v1", analysis_id)
    if not rows:
        return None
    path, doc = rows[0]
    return {"relpath": _safe_rel(path, project_root), "data": doc}


def _select_storyboard(project_root: str, analysis_id: Optional[str]) -> Optional[Dict[str, Any]]:
    rows = _find_contract_docs(project_root, "storyboard.v1", analysis_id)
    if not rows:
        return None
    path, doc = rows[0]
    return {"relpath": _safe_rel(path, project_root), "data": doc}


def _select_frame_labels(project_root: str, analysis_id: Optional[str]) -> Optional[Dict[str, Any]]:
    rows = _find_contract_docs(project_root, "frame_labels.v1", analysis_id)
    if not rows:
        return None
    path, doc = rows[0]
    return {"relpath": _safe_rel(path, project_root), "data": doc}


def _select_quality_target_contract(project_root: str, analysis_id: Optional[str]) -> Optional[Dict[str, Any]]:
    rows = _find_contract_docs(project_root, "quality_target.v1", analysis_id)
    if rows:
        path, doc = rows[0]
        return {"relpath": _safe_rel(path, project_root), "data": doc}

    # Deterministic fallback to stable examples if no versioned contract is found.
    for rel in (
        "repo/examples/quality_target.motion_strict.v1.example.json",
        "repo/examples/quality_target.v1.example.json",
    ):
        abs_p = os.path.join(project_root, rel)
        doc = _load_json_if_exists(abs_p)
        if isinstance(doc, dict) and doc.get("version") == "quality_target.v1":
            return {"relpath": rel, "data": doc}
    return None


def _facts_only_enabled() -> bool:
    raw = os.environ.get("CAF_PLANNER_FACTS_ONLY", "1").strip().lower()
    return raw not in ("0", "false", "off", "no")


def _replace_word_insensitive(text: str, pattern: str, repl: str) -> str:
    return re.sub(pattern, repl, text, flags=re.IGNORECASE)


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


def _select_engine_adapter_registry(project_root: str) -> Optional[Dict[str, Any]]:
    rel = "repo/shared/engine_adapter_registry.v1.json"
    abs_p = os.path.join(project_root, rel)
    doc = _load_json_if_exists(abs_p)
    if isinstance(doc, dict) and doc.get("version") == "engine_adapter_registry.v1":
        return {"relpath": rel, "data": doc}
    return None


def _collect_terms(prd: Dict[str, Any], inbox_list: List[Dict[str, Any]]) -> set[str]:
    blob = json.dumps({"prd": prd, "inbox": inbox_list}, sort_keys=True, ensure_ascii=True).lower()
    parts = re.split(r"[^a-z0-9]+", blob)
    return {p for p in parts if len(p) >= 3}


def _select_sample_ingest_manifest(
    project_root: str,
    prd: Dict[str, Any],
    inbox_list: List[Dict[str, Any]],
    analysis_id: Optional[str],
) -> Optional[Dict[str, Any]]:
    base = os.path.join(project_root, "repo", "canon", "demo_analyses")
    if not os.path.isdir(base):
        return None
    rows: List[Tuple[int, str, Dict[str, Any]]] = []
    terms = _collect_terms(prd, inbox_list)
    context_blob = json.dumps({"prd": prd, "inbox": inbox_list}, sort_keys=True, ensure_ascii=True).lower()
    for root, _dirs, files in os.walk(base):
        for name in sorted(files):
            if not name.endswith(".sample_ingest_manifest.v1.json"):
                continue
            p = os.path.join(root, name)
            doc = _load_json_if_exists(p)
            if not isinstance(doc, dict) or doc.get("version") != "sample_ingest_manifest.v1":
                continue
            score = 0
            doc_analysis_id = doc.get("analysis_id")
            if isinstance(analysis_id, str) and analysis_id and doc_analysis_id == analysis_id:
                score += 100
            source = doc.get("source", {})
            aliases = source.get("reference_aliases", []) if isinstance(source, dict) else []
            if isinstance(aliases, list):
                for alias in aliases:
                    if not isinstance(alias, str):
                        continue
                    alias_norm = " ".join([t for t in re.split(r"[^a-z0-9]+", alias.lower()) if t])
                    if alias_norm and alias_norm in context_blob:
                        score += 200
                    tokens = [t for t in re.split(r"[^a-z0-9]+", alias.lower()) if t]
                    if tokens and all(t in terms for t in tokens):
                        score += 10
                    score += sum(1 for t in tokens if t in terms)
            rows.append((score, p, doc))
    if not rows:
        return None
    rows.sort(key=lambda x: (-x[0], x[1]))
    best = rows[0]
    if best[0] <= 0 and not (isinstance(analysis_id, str) and analysis_id):
        return None
    return {"relpath": _safe_rel(best[1], project_root), "data": best[2]}


def _load_promotion_registry(project_root: str) -> Optional[Dict[str, Any]]:
    p = os.path.join(project_root, "repo", "shared", "promotion_registry.v1.json")
    doc = _load_json_if_exists(p)
    if isinstance(doc, dict) and doc.get("version") == "promotion_registry.v1":
        return doc
    return None


def _resolve_pointer_overrides(
    project_root: str,
    prd: Dict[str, Any],
    inbox_list: List[Dict[str, Any]],
    selected_analysis: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    analysis_id = None
    if isinstance(selected_analysis, dict):
        raw_id = selected_analysis.get("analysis_id")
        if isinstance(raw_id, str) and raw_id:
            analysis_id = raw_id

    out: Dict[str, Any] = {}
    manifest = _select_sample_ingest_manifest(project_root, prd, inbox_list, analysis_id)
    if isinstance(manifest, dict):
        data = manifest.get("data", {})
        contracts = data.get("contracts", {}) if isinstance(data, dict) else {}
        if isinstance(contracts, dict):
            out["sample_ingest_manifest_relpath"] = manifest.get("relpath")
            out["contracts"] = contracts

    registry = _load_promotion_registry(project_root)
    if isinstance(registry, dict):
        approved = registry.get("approved", [])
        if isinstance(approved, list):
            for row in reversed(approved):
                if not isinstance(row, dict):
                    continue
                proposal = row.get("proposal", {})
                pointers = proposal.get("contract_pointers", {}) if isinstance(proposal, dict) else {}
                if isinstance(pointers, dict) and pointers:
                    out["promoted_contract_pointers"] = pointers
                    break
    return out


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

    reverse_contracts = _select_reverse_contracts(project_root, selected_analysis)
    reverse_prompt = reverse_contracts.get("reverse_prompt", {})
    beat_grid = reverse_contracts.get("beat_grid", {})
    pose_doc = reverse_contracts.get("pose_checkpoints", {})
    keyframe_doc = reverse_contracts.get("keyframe_checkpoints", {})
    reverse_timestamps = _extract_reverse_timestamps(reverse_contracts)
    if any(isinstance(x, dict) and x.get("data") for x in (reverse_prompt, beat_grid, pose_doc, keyframe_doc)):
        reverse_data = reverse_prompt.get("data", {}) if isinstance(reverse_prompt, dict) else {}
        truth = reverse_data.get("truth", {}) if isinstance(reverse_data, dict) else {}
        visual_facts = truth.get("visual_facts", {}) if isinstance(truth, dict) else {}
        ctx["reverse_analysis"] = {
            "analysis_id": reverse_contracts.get("analysis_id"),
            "reverse_prompt_relpath": (reverse_prompt or {}).get("relpath"),
            "beat_grid_relpath": (beat_grid or {}).get("relpath"),
            "pose_checkpoints_relpath": (pose_doc or {}).get("relpath"),
            "keyframe_checkpoints_relpath": (keyframe_doc or {}).get("relpath"),
            "timestamp_count": len(reverse_timestamps),
            "timestamps_preview": reverse_timestamps[:10],
            "visual_facts": visual_facts if isinstance(visual_facts, dict) else {},
            "facts_only_mode": _facts_only_enabled(),
        }
    frame_labels = _select_frame_labels(project_root, reverse_contracts.get("analysis_id"))
    if isinstance(frame_labels, dict):
        fl_doc = frame_labels.get("data", {})
        frames = fl_doc.get("frames", []) if isinstance(fl_doc, dict) else []
        policy = fl_doc.get("policy", {}) if isinstance(fl_doc, dict) else {}
        ctx["frame_labeling"] = {
            "relpath": frame_labels.get("relpath"),
            "frame_count": len(frames) if isinstance(frames, list) else 0,
            "facts_only_or_unknown": bool(policy.get("facts_only_or_unknown")) if isinstance(policy, dict) else False,
            "enrichment_provider": policy.get("enrichment_provider") if isinstance(policy, dict) else None,
        }
    segment_plan = _select_segment_stitch_plan(project_root, reverse_contracts.get("analysis_id"))
    if isinstance(segment_plan, dict):
        segment_doc = segment_plan.get("data", {})
        segments = segment_doc.get("segments", []) if isinstance(segment_doc, dict) else []
        stitch_order = segment_doc.get("stitch_order", []) if isinstance(segment_doc, dict) else []
        retries = 0
        if isinstance(segments, list):
            retries = sum(
                int(seg.get("retry_budget", 0))
                for seg in segments
                if isinstance(seg, dict) and isinstance(seg.get("retry_budget"), int)
            )
        ctx["segment_stitch_plan"] = {
            "relpath": segment_plan.get("relpath"),
            "plan_id": segment_doc.get("plan_id") if isinstance(segment_doc, dict) else None,
            "analysis_id": segment_doc.get("analysis_id") if isinstance(segment_doc, dict) else None,
            "segment_count": len(segments) if isinstance(segments, list) else 0,
            "stitch_order_count": len(stitch_order) if isinstance(stitch_order, list) else 0,
            "total_retry_budget": retries,
            "constraints": segment_doc.get("constraints", {}) if isinstance(segment_doc, dict) else {},
        }
    continuity_pack = _select_continuity_pack(project_root, reverse_contracts.get("analysis_id"))
    if isinstance(continuity_pack, dict):
        cp_doc = continuity_pack.get("data", {})
        hero_id = None
        style_id = None
        costume_id = None
        if isinstance(cp_doc, dict):
            hero = cp_doc.get("hero", {})
            style = cp_doc.get("style", {})
            costume = cp_doc.get("costume", {})
            rules = cp_doc.get("rules", {})
            if isinstance(hero, dict):
                hero_id = hero.get("hero_id")
            if isinstance(style, dict):
                style_id = style.get("style_id")
            if isinstance(costume, dict):
                costume_id = costume.get("costume_profile_id")
            if not isinstance(rules, dict):
                rules = {}
        else:
            rules = {}
        ctx["continuity_pack"] = {
            "relpath": continuity_pack.get("relpath"),
            "pack_id": cp_doc.get("pack_id") if isinstance(cp_doc, dict) else None,
            "hero_id": hero_id,
            "style_id": style_id,
            "costume_profile_id": costume_id,
            "rules": rules,
        }
    quality_target = _select_quality_target_contract(project_root, reverse_contracts.get("analysis_id"))
    if isinstance(quality_target, dict):
        qt_doc = quality_target.get("data", {})
        thresholds = qt_doc.get("thresholds", {}) if isinstance(qt_doc, dict) else {}
        if not isinstance(thresholds, dict):
            thresholds = {}
        ctx["quality_target"] = {
            "relpath": quality_target.get("relpath"),
            "profile_name": qt_doc.get("profile_name") if isinstance(qt_doc, dict) else None,
            "thresholds": thresholds,
        }
    storyboard = _select_storyboard(project_root, reverse_contracts.get("analysis_id"))
    if isinstance(storyboard, dict):
        sb_doc = storyboard.get("data", {})
        frames = sb_doc.get("frames", []) if isinstance(sb_doc, dict) else []
        seed_assets: List[str] = []
        if isinstance(frames, list):
            for frame in frames:
                if not isinstance(frame, dict):
                    continue
                image_asset = frame.get("image_asset")
                if isinstance(image_asset, str) and image_asset.strip():
                    seed_assets.append(image_asset.strip())
        deduped: List[str] = []
        seen_assets = set()
        for asset in seed_assets:
            if asset in seen_assets:
                continue
            seen_assets.add(asset)
            deduped.append(asset)
        ctx["storyboard_i2v"] = {
            "relpath": storyboard.get("relpath"),
            "frame_count": len(frames) if isinstance(frames, list) else 0,
            "seed_frame_assets": deduped[:3],
            "strategy": "storyboard_first_i2v",
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
    registry = _select_engine_adapter_registry(project_root)
    if isinstance(registry, dict):
        reg_doc = registry.get("data", {})
        baseline = reg_doc.get("baseline", {}) if isinstance(reg_doc, dict) else {}
        routing = reg_doc.get("routing", {}) if isinstance(reg_doc, dict) else {}
        if not isinstance(baseline, dict):
            baseline = {}
        if not isinstance(routing, dict):
            routing = {}
        ctx["engine_adapter_policy"] = {
            "relpath": registry.get("relpath"),
            "registry_id": reg_doc.get("registry_id") if isinstance(reg_doc, dict) else None,
            "baseline_video_provider": baseline.get("video_provider"),
            "baseline_frame_provider": baseline.get("frame_provider"),
            "video_provider_order": routing.get("video_provider_order", []),
            "frame_provider_order": routing.get("frame_provider_order", []),
            "lab_challenger_order": routing.get("lab_challenger_order", []),
            "motion_constraints": routing.get("motion_constraints", []),
            "post_process_order": routing.get("post_process_order", []),
            "providers": reg_doc.get("providers", []) if isinstance(reg_doc, dict) else [],
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
    return job


def _apply_engine_adapter_hints(job: Dict[str, Any], quality_context: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(job, dict) or not isinstance(quality_context, dict):
        return job
    if isinstance(job.get("generation_policy"), dict):
        return job
    policy = quality_context.get("engine_adapter_policy")
    if not isinstance(policy, dict):
        return job
    lane = str(job.get("lane", "")).strip() or "ai_video"
    route_mode = os.environ.get("CAF_ENGINE_ROUTE_MODE", "production").strip().lower()
    if route_mode not in ("production", "lab"):
        route_mode = "production"
    route = route_engine_policy(policy, lane=lane, mode=route_mode)
    video_order = policy.get("video_provider_order")
    frame_order = policy.get("frame_provider_order")
    lab_order = route.get("lab_challenger_candidates")
    motion_constraints = route.get("motion_constraints")
    post_process = route.get("post_process_order")
    if not isinstance(video_order, list) or not video_order:
        return job
    if not isinstance(frame_order, list) or not frame_order:
        return job
    motion_contract_relpath: Optional[str] = None
    mc = job.get("motion_contract")
    if isinstance(mc, dict):
        rel = mc.get("relpath")
        if isinstance(rel, str) and rel:
            motion_contract_relpath = rel
    motion_constraints_list = [str(x) for x in (motion_constraints or []) if isinstance(x, str)]
    if motion_contract_relpath:
        token = f"pose_contract:{motion_contract_relpath}"
        if token not in motion_constraints_list:
            motion_constraints_list.append(token)
    job["generation_policy"] = {
        "registry_relpath": policy.get("relpath"),
        "baseline_video_provider": policy.get("baseline_video_provider"),
        "baseline_frame_provider": policy.get("baseline_frame_provider"),
        "route_mode": route.get("mode"),
        "selected_video_provider": route.get("selected_video_provider"),
        "selected_frame_provider": route.get("selected_frame_provider"),
        "video_provider_order": [str(x) for x in route.get("video_candidates", []) if isinstance(x, str)],
        "frame_provider_order": [str(x) for x in route.get("frame_candidates", []) if isinstance(x, str)],
        "lab_challenger_order": [str(x) for x in (lab_order or []) if isinstance(x, str)],
        "motion_constraints": motion_constraints_list,
        "post_process_order": [str(x) for x in (post_process or []) if isinstance(x, str)],
    }
    return job


def _apply_reverse_analysis_hints(job: Dict[str, Any], quality_context: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(job, dict):
        return job
    if not isinstance(quality_context, dict):
        return job
    reverse = quality_context.get("reverse_analysis")
    if not isinstance(reverse, dict):
        return job
    preview = reverse.get("timestamps_preview", [])
    if not isinstance(preview, list) or not preview:
        return job
    shots = job.get("shots", [])
    video = job.get("video", {})
    if not isinstance(shots, list) or not shots:
        return job
    if not isinstance(video, dict):
        return job
    length_seconds = int(video.get("length_seconds", 15))
    max_t = max(0, length_seconds - 1)
    if max_t <= 0:
        return job

    src_max = max(float(x) for x in preview if isinstance(x, (int, float)))
    if src_max <= 0:
        return job
    anchor_norms = sorted(
        {
            min(1.0, max(0.0, float(x) / src_max))
            for x in preview
            if isinstance(x, (int, float)) and float(x) >= 0
        }
    )
    if not anchor_norms:
        return job
    if 1.0 not in anchor_norms:
        anchor_norms.append(1.0)

    prev_t = -1
    count = len(shots)
    for i, shot in enumerate(shots):
        if not isinstance(shot, dict):
            continue
        target = float(i) / float(max(1, count - 1))
        snap = min(anchor_norms, key=lambda n: abs(n - target))
        t = int(round(snap * max_t))
        if t < prev_t:
            t = prev_t
        shot["t"] = min(max(0, t), 60)
        prev_t = shot["t"]
    return job


def _apply_facts_only_guard(job: Dict[str, Any], quality_context: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(job, dict) or not isinstance(quality_context, dict):
        return job
    reverse = quality_context.get("reverse_analysis")
    if not isinstance(reverse, dict):
        return job
    if not bool(reverse.get("facts_only_mode")):
        return job

    visual_facts = reverse.get("visual_facts", {})
    if not isinstance(visual_facts, dict):
        visual_facts = {}
    camera_mode = str(visual_facts.get("camera_movement_mode") or "unknown").lower()
    if camera_mode not in {"locked", "pan", "tilt", "push", "pull", "mixed", "unknown"}:
        camera_mode = "unknown"
    brightness_bucket = str(visual_facts.get("brightness_bucket") or "unknown").lower()
    if brightness_bucket not in {"dark", "mid", "bright", "unknown"}:
        brightness_bucket = "unknown"
    palette = visual_facts.get("palette_top_hex", [])
    palette_hint = "unknown"
    if isinstance(palette, list) and palette and isinstance(palette[0], str):
        palette_hint = palette[0]

    shots = job.get("shots", [])
    if isinstance(shots, list):
        for shot in shots:
            if not isinstance(shot, dict):
                continue
            for key in ("visual", "action", "caption"):
                val = shot.get(key)
                if not isinstance(val, str):
                    continue
                txt = val
                if camera_mode == "unknown":
                    txt = _replace_word_insensitive(txt, r"\\b(pan|tilt|zoom|dolly|push|pull|tracking|handheld|static|locked)\\b", "unknown")
                elif camera_mode == "locked":
                    txt = _replace_word_insensitive(txt, r"\\b(pan|tilt|zoom|dolly|push|pull|tracking|handheld)\\b", "unknown")
                elif camera_mode == "pan":
                    txt = _replace_word_insensitive(txt, r"\\b(tilt|zoom|dolly|push|pull|handheld)\\b", "unknown")
                elif camera_mode == "tilt":
                    txt = _replace_word_insensitive(txt, r"\\b(pan|zoom|dolly|push|pull|tracking|handheld)\\b", "unknown")

                if brightness_bucket == "unknown":
                    txt = _replace_word_insensitive(txt, r"\\b(bright|dark|dim|neon|high-key|low-key)\\b", "unknown")
                shot[key] = txt

            # Deterministic fact stamp for downstream audit in existing schema fields.
            action = shot.get("action")
            if isinstance(action, str) and "| facts:" not in action:
                facts = f"camera={camera_mode},brightness={brightness_bucket},palette={palette_hint}"
                shot["action"] = f"{action} | facts:{facts}"[:240]

    script = job.get("script")
    if isinstance(script, dict):
        voice = script.get("voiceover")
        if isinstance(voice, str):
            txt = voice
            if camera_mode == "unknown":
                txt = _replace_word_insensitive(txt, r"\\b(pan|tilt|zoom|dolly|push|pull|tracking|handheld|static|locked)\\b", "unknown")
            if brightness_bucket == "unknown":
                txt = _replace_word_insensitive(txt, r"\\b(bright|dark|dim|neon|high-key|low-key)\\b", "unknown")
            script["voiceover"] = txt

    return job


def _validate_facts_only_guard(job: Dict[str, Any], quality_context: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    reverse = quality_context.get("reverse_analysis", {}) if isinstance(quality_context, dict) else {}
    if not isinstance(reverse, dict) or not bool(reverse.get("facts_only_mode")):
        return errors
    visual_facts = reverse.get("visual_facts", {}) if isinstance(reverse, dict) else {}
    if not isinstance(visual_facts, dict):
        visual_facts = {}
    camera_mode = str(visual_facts.get("camera_movement_mode") or "unknown").lower()
    brightness_bucket = str(visual_facts.get("brightness_bucket") or "unknown").lower()

    camera_terms = re.compile(r"\\b(pan|tilt|zoom|dolly|push|pull|tracking|handheld|static|locked)\\b", re.IGNORECASE)
    brightness_terms = re.compile(r"\\b(bright|dark|dim|neon|high-key|low-key)\\b", re.IGNORECASE)
    allowed_camera: Dict[str, set[str]] = {
        "unknown": set(),
        "locked": {"locked", "static"},
        "pan": {"pan", "tracking"},
        "tilt": {"tilt"},
        "push": {"push"},
        "pull": {"pull"},
        "mixed": {"pan", "tilt", "zoom", "dolly", "push", "pull", "tracking", "handheld", "static", "locked"},
    }

    texts: List[Tuple[str, str]] = []
    script = job.get("script", {})
    if isinstance(script, dict):
        for k in ("hook", "voiceover", "ending"):
            v = script.get(k)
            if isinstance(v, str):
                texts.append((f"script.{k}", v))
    shots = job.get("shots", [])
    if isinstance(shots, list):
        for i, shot in enumerate(shots):
            if not isinstance(shot, dict):
                continue
            for k in ("visual", "action", "caption"):
                v = shot.get(k)
                if isinstance(v, str):
                    texts.append((f"shots[{i}].{k}", v))

    for label, text in texts:
        for m in camera_terms.finditer(text):
            token = m.group(1).lower()
            if token not in allowed_camera.get(camera_mode, set()):
                errors.append(f"{label}: camera claim '{token}' not supported by camera_movement_mode={camera_mode}")
                break
        if brightness_bucket == "unknown" and brightness_terms.search(text):
            errors.append(f"{label}: brightness claim not allowed when brightness_bucket=unknown")
    return errors


def _apply_segment_stitch_hints(job: Dict[str, Any], quality_context: Dict[str, Any], project_root: str) -> Dict[str, Any]:
    if not isinstance(job, dict) or not isinstance(quality_context, dict):
        return job
    plan_ctx = quality_context.get("segment_stitch_plan")
    if not isinstance(plan_ctx, dict):
        return job
    relpath = plan_ctx.get("relpath")
    if not isinstance(relpath, str) or not relpath:
        return job
    abs_path = os.path.join(project_root, relpath)
    plan = _load_json_if_exists(abs_path)
    if not isinstance(plan, dict):
        return job
    enabled = True
    existing = job.get("segment_stitch")
    if isinstance(existing, dict) and isinstance(existing.get("enabled"), bool):
        enabled = existing["enabled"]
    job["segment_stitch"] = {
        "plan_relpath": relpath,
        "enabled": enabled,
    }

    segments = plan.get("segments", [])
    if not isinstance(segments, list) or not segments:
        return job
    shots = job.get("shots", [])
    video = job.get("video", {})
    if not isinstance(shots, list) or not shots or not isinstance(video, dict):
        return job

    segment_bounds: List[float] = []
    for seg in segments:
        if not isinstance(seg, dict):
            continue
        for k in ("start_sec", "end_sec"):
            v = seg.get(k)
            if isinstance(v, (int, float)) and v >= 0:
                segment_bounds.append(float(v))
    if not segment_bounds:
        return job

    src_max = max(segment_bounds)
    if src_max <= 0:
        return job
    anchor_norms = sorted({min(1.0, max(0.0, t / src_max)) for t in segment_bounds})
    if 1.0 not in anchor_norms:
        anchor_norms.append(1.0)

    length_seconds = int(video.get("length_seconds", 15))
    max_t = max(0, length_seconds - 1)
    prev_t = -1
    count = len(shots)
    for i, shot in enumerate(shots):
        if not isinstance(shot, dict):
            continue
        target = float(i) / float(max(1, count - 1))
        snap = min(anchor_norms, key=lambda n: abs(n - target))
        t = int(round(snap * max_t))
        if t < prev_t:
            t = prev_t
        shot["t"] = min(max(0, t), 60)
        prev_t = shot["t"]
    return job


def _apply_continuity_pack_hints(job: Dict[str, Any], quality_context: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(job, dict) or not isinstance(quality_context, dict):
        return job
    continuity = quality_context.get("continuity_pack")
    if not isinstance(continuity, dict):
        return job
    relpath = continuity.get("relpath")
    if not isinstance(relpath, str) or not relpath:
        return job
    existing = job.get("continuity_pack")
    if isinstance(existing, dict) and isinstance(existing.get("relpath"), str) and existing.get("relpath"):
        return job
    job["continuity_pack"] = {"relpath": relpath}
    return job


def _apply_quality_target_hints(job: Dict[str, Any], quality_context: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(job, dict) or not isinstance(quality_context, dict):
        return job
    existing = job.get("quality_target")
    if isinstance(existing, dict) and isinstance(existing.get("relpath"), str) and existing.get("relpath"):
        return job

    quality_target = quality_context.get("quality_target")
    if not isinstance(quality_target, dict):
        return job
    relpath = quality_target.get("relpath")
    if not isinstance(relpath, str) or not relpath:
        return job

    # Prefer stricter motion profile by default when segment-stitch context is active.
    seg_ctx = quality_context.get("segment_stitch_plan")
    if isinstance(seg_ctx, dict):
        strict_rel = "repo/examples/quality_target.motion_strict.v1.example.json"
        strict_abs = os.path.join(_repo_root(), strict_rel)
        if os.path.exists(strict_abs):
            relpath = strict_rel

    job["quality_target"] = {"relpath": relpath}
    return job


def _apply_motion_contract_hints(job: Dict[str, Any], quality_context: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(job, dict) or not isinstance(quality_context, dict):
        return job
    existing = job.get("motion_contract")
    if isinstance(existing, dict) and isinstance(existing.get("relpath"), str) and existing.get("relpath"):
        return job

    relpath: Optional[str] = None
    reverse = quality_context.get("reverse_analysis")
    if isinstance(reverse, dict):
        candidate = reverse.get("pose_checkpoints_relpath")
        if isinstance(candidate, str) and candidate:
            relpath = candidate
    if not relpath:
        fallback_rel = "repo/examples/pose_checkpoints.v1.example.json"
        fallback_abs = os.path.join(_repo_root(), fallback_rel)
        if os.path.exists(fallback_abs):
            relpath = fallback_rel
    if not relpath:
        return job
    job["motion_contract"] = {
        "relpath": relpath,
        "contract_version": "pose_checkpoints.v1",
    }
    return job


def _apply_pointer_resolver_hints(job: Dict[str, Any], quality_context: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(job, dict) or not isinstance(quality_context, dict):
        return job
    resolver = quality_context.get("pointer_resolver")
    if not isinstance(resolver, dict):
        return job
    contracts = resolver.get("contracts", {})
    if isinstance(contracts, dict):
        # Manifest-derived pointers are explicit operator/promoted intent.
        # They should take precedence over provider defaults or generic fallbacks.
        rel = contracts.get("quality_target_relpath")
        if isinstance(rel, str) and rel:
            job["quality_target"] = {"relpath": rel}
        rel = contracts.get("continuity_pack_relpath")
        if isinstance(rel, str) and rel and not isinstance(job.get("continuity_pack"), dict):
            job["continuity_pack"] = {"relpath": rel}
        rel = contracts.get("pose_checkpoints_relpath")
        if isinstance(rel, str) and rel:
            job["motion_contract"] = {"relpath": rel, "contract_version": "pose_checkpoints.v1"}
        rel = contracts.get("segment_stitch_plan_relpath")
        if isinstance(rel, str) and rel:
            job["segment_stitch"] = {"plan_relpath": rel, "enabled": True}
    promoted = resolver.get("promoted_contract_pointers", {})
    if isinstance(promoted, dict):
        if not isinstance(job.get("motion_contract"), dict):
            mc = promoted.get("motion_contract")
            if isinstance(mc, dict) and isinstance(mc.get("relpath"), str):
                job["motion_contract"] = {
                    "relpath": mc.get("relpath"),
                    "contract_version": str(mc.get("contract_version", "pose_checkpoints.v1")),
                }
        if not isinstance(job.get("quality_target"), dict):
            qt = promoted.get("quality_target")
            if isinstance(qt, dict) and isinstance(qt.get("relpath"), str):
                job["quality_target"] = {"relpath": qt.get("relpath")}
        if not isinstance(job.get("continuity_pack"), dict):
            cp = promoted.get("continuity_pack")
            if isinstance(cp, dict) and isinstance(cp.get("relpath"), str):
                job["continuity_pack"] = {"relpath": cp.get("relpath")}
        if not isinstance(job.get("segment_stitch"), dict):
            seg = promoted.get("segment_stitch")
            if isinstance(seg, dict) and isinstance(seg.get("plan_relpath"), str):
                job["segment_stitch"] = {
                    "plan_relpath": seg.get("plan_relpath"),
                    "enabled": bool(seg.get("enabled", True)),
                }
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
    parser.add_argument(
        "--analysis-id",
        default=None,
        help="Optional deterministic analysis_id override from repo/canon/demo_analyses/video_analysis_index.v1.json",
    )
    parser.add_argument(
        "--ignore-inbox",
        action="store_true",
        help="Ignore inbox artifacts for planner selection/generation context (prevents stale inbox influence).",
    )
    parser.add_argument("--debug", action="store_true", help="Print safe debug info")

    args = parser.parse_args(argv)

    provider = None
    try:
        if args.prompt:
            prd = {"prompt": args.prompt}
        else:
            prd = _load_json(args.prd)

        inbox_list, inbox_with_names = _load_inbox(args.inbox)
        if args.ignore_inbox:
            inbox_list, inbox_with_names = [], []
            print("INFO planner ignore_inbox=true", file=sys.stderr)

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
        video_analysis = _load_video_analysis_selection(
            project_root,
            prd,
            inbox_list,
            forced_analysis_id=args.analysis_id,
        )
        quality_context = _load_quality_context(project_root, video_analysis)
        quality_context["pointer_resolver"] = _resolve_pointer_overrides(project_root, prd, inbox_list, video_analysis)

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
        job = _apply_reverse_analysis_hints(job, quality_context)
        job = _apply_pointer_resolver_hints(job, quality_context)
        job = _apply_segment_stitch_hints(job, quality_context, project_root)
        job = _apply_continuity_pack_hints(job, quality_context)
        job = _apply_quality_target_hints(job, quality_context)
        job = _apply_motion_contract_hints(job, quality_context)
        job = _apply_engine_adapter_hints(job, quality_context)
        job = _apply_quality_policy_hints(job, quality_context)
        job = _apply_facts_only_guard(job, quality_context)
        facts_errors = _validate_facts_only_guard(job, quality_context)
        if facts_errors:
            raise RuntimeError("facts-only guard failed: " + "; ".join(facts_errors[:3]))

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
