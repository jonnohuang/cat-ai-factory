from __future__ import annotations

from typing import Any, Dict, List


def _as_str_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    return [str(x) for x in value if isinstance(x, str) and x.strip()]


def _is_enabled_provider(provider: Dict[str, Any]) -> bool:
    return bool(isinstance(provider, dict) and provider.get("enabled") is True)


def _provider_matches(
    provider: Dict[str, Any], *, kind: str, mode: str, lane: str
) -> bool:
    if not _is_enabled_provider(provider):
        return False
    if str(provider.get("kind", "")).strip() != kind:
        return False
    p_mode = str(provider.get("mode", "")).strip()
    if mode == "production":
        if p_mode != "production":
            return False
    else:
        if p_mode not in ("production", "lab"):
            return False
    lanes = _as_str_list(provider.get("lane_support"))
    return lane in lanes


def route_engine_policy(
    policy: Dict[str, Any], lane: str, mode: str = "production"
) -> Dict[str, Any]:
    lane = lane.strip() or "ai_video"
    mode = "lab" if mode == "lab" else "production"
    providers = policy.get("providers", [])
    routing = policy.get("routing", {})
    if not isinstance(routing, dict):
        routing = {}
    if not isinstance(providers, list):
        return {
            "mode": mode,
            "selected_video_provider": None,
            "selected_frame_provider": None,
            "video_candidates": [],
            "frame_candidates": [],
            "lab_challenger_candidates": [],
            "motion_constraints": [],
            "post_process_order": [],
        }

    provider_by_id: Dict[str, Dict[str, Any]] = {}
    for row in providers:
        if not isinstance(row, dict):
            continue
        pid = str(row.get("provider_id", "")).strip()
        if pid:
            provider_by_id[pid] = row

    video_order = _as_str_list(routing.get("video_provider_order")) or _as_str_list(
        policy.get("video_provider_order")
    )
    frame_order = _as_str_list(routing.get("frame_provider_order")) or _as_str_list(
        policy.get("frame_provider_order")
    )
    lab_order = _as_str_list(routing.get("lab_challenger_order")) or _as_str_list(
        policy.get("lab_challenger_order")
    )
    motion_order = _as_str_list(routing.get("motion_constraints")) or _as_str_list(
        policy.get("motion_constraints")
    )
    post_order = _as_str_list(routing.get("post_process_order")) or _as_str_list(
        policy.get("post_process_order")
    )

    video_candidates: List[str] = []
    for pid in video_order:
        row = provider_by_id.get(pid)
        if not isinstance(row, dict):
            continue
        if _provider_matches(row, kind="video", mode=mode, lane=lane):
            video_candidates.append(pid)

    frame_candidates: List[str] = []
    for pid in frame_order:
        row = provider_by_id.get(pid)
        if not isinstance(row, dict):
            continue
        if _provider_matches(row, kind="frame", mode=mode, lane=lane):
            frame_candidates.append(pid)

    lab_candidates: List[str] = []
    if mode == "lab":
        for pid in lab_order:
            row = provider_by_id.get(pid)
            if not isinstance(row, dict):
                continue
            if _provider_matches(row, kind="video", mode="lab", lane=lane):
                # Keep lab challengers explicit (exclude production rows with same id).
                if str(row.get("mode", "")).strip() == "lab":
                    lab_candidates.append(pid)

    motion_constraints: List[str] = []
    for pid in motion_order:
        row = provider_by_id.get(pid)
        if not isinstance(row, dict):
            continue
        if _provider_matches(row, kind="motion_constraint", mode=mode, lane=lane):
            motion_constraints.append(pid)

    post_process: List[str] = []
    for pid in post_order:
        row = provider_by_id.get(pid)
        if not isinstance(row, dict):
            continue
        if _provider_matches(row, kind="post_process", mode=mode, lane=lane):
            post_process.append(pid)

    return {
        "mode": mode,
        "selected_video_provider": video_candidates[0] if video_candidates else None,
        "selected_frame_provider": frame_candidates[0] if frame_candidates else None,
        "video_candidates": video_candidates,
        "frame_candidates": frame_candidates,
        "lab_challenger_candidates": lab_candidates,
        "motion_constraints": motion_constraints,
        "post_process_order": post_process,
    }
