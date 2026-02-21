from __future__ import annotations

import datetime
import json
import os
import pathlib
from typing import Any, Dict, List, Optional
from .asset_resolver import AssetResolver


class PointerResolver:
    def __init__(self, repo_root: pathlib.Path):
        self.repo_root = repo_root
        self.asset_resolver = AssetResolver(repo_root)

    def _exists(self, relpath: str) -> bool:
        return (self.repo_root / relpath).exists()

    def _resolve_core_pointer(self, tags: List[str], key: str, pointers: Dict[str, str], rejected: List[Dict[str, Any]]):
        """Helper to resolve a core contract pointer via AssetResolver."""
        paths = self.asset_resolver.find_assets(tags, asset_type="contract")
        if paths:
            # Verify existence on disk to be extra safe
            if self._exists(paths[0]):
                pointers[key] = paths[0]
                return
            else:
                rejected.append({"candidate_relpath": paths[0], "reason": "file_missing_on_disk", "tags": tags})
        else:
            rejected.append({"candidate_relpath": f"tag_query:{tags}", "reason": "not_found_in_manifest", "tags": tags})

    def resolve(
        self,
        job_id: str,
        brief: Dict[str, Any],
        policy: str = "prefer_canon_strict_motion",
    ) -> Dict[str, Any]:
        """
        Deterministically resolves contract pointers based on brief intent and policy.
        Authority derived solely from AssetRAG manifest.
        """
        pointers: Dict[str, str] = {}
        rejected: List[Dict[str, Any]] = []

        # 1. Canon / Shared Contracts (Resolved via RAG)
        self._resolve_core_pointer(["hero", "registry"], "hero_registry", pointers, rejected)
        self._resolve_core_pointer(["bible", "series"], "series_bible", pointers, rejected)
        self._resolve_core_pointer(["engine", "registry"], "engine_adapter_registry", pointers, rejected)
        self._resolve_core_pointer(["promotion", "registry"], "promotion_registry", pointers, rejected)

        # Special Case: Audio Manifest (Dynamic Asset)
        audio_paths = self.asset_resolver.find_assets(["audio", "manifest"], asset_type="contract")
        if audio_paths:
             pointers["audio_manifest"] = audio_paths[0]
        else:
            # Fallback legacy check for audio manifest since it's in sandbox
            audio_man = "sandbox/assets/audio/audio_manifest.v1.json"
            if self._exists(audio_man):
                pointers["audio_manifest"] = audio_man
            else:
                rejected.append({"candidate_relpath": audio_man, "reason": "not_found"})

        # 2. Quality Target (Policy Driven)
        target_tags = ["quality", "target"]
        if "strict_motion" in policy:
            target_tags.append("strict")
            
        qt_paths = self.asset_resolver.find_assets(target_tags, asset_type="contract")
        if qt_paths:
            pointers["quality_target"] = qt_paths[0]
        else:
            # Fallback to standard quality target if strict is missing
            std_qt = self.asset_resolver.find_assets(["quality", "target"], asset_type="contract")
            if std_qt:
                pointers["quality_target"] = std_qt[0]
                if "strict" in target_tags:
                    rejected.append({"candidate_relpath": "strict_quality_target", "reason": "missing_falling_back_to_std"})
            else:
                rejected.append({"candidate_relpath": "quality_target_query", "reason": "not_found_in_manifest"})

        # 3. Motion / Analyzer Artifacts (Keyword Heuristic)
        motion_intent = str(brief.get("motion", "")).lower()
        prompt_text = str(brief.get("prompt", "")).lower()
        combined_intent = f"{motion_intent} {prompt_text}"

        if "dance" in combined_intent or "loop" in combined_intent:
            # Resolve pose via RAG
            poses = self.asset_resolver.find_assets(["dance", "loop", "pose"], asset_type="contract")
            if poses:
                pointers["pose_checkpoint"] = poses[0]
            else:
                rejected.append({"candidate_relpath": "dance_loop_pose_contract_rag", "reason": "not_found_in_asset_manifest"})

            # Resolve beat via RAG
            beats = self.asset_resolver.find_assets(["dance", "loop", "beat"], asset_type="contract")
            if beats:
                pointers["beat_grid"] = beats[0]
            else:
                rejected.append({"candidate_relpath": "dance_loop_beat_contract_rag", "reason": "not_found_in_asset_manifest"})

        return {
            "version": "pointer_resolution.v1",
            "job_id": job_id,
            "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "brief_intent": brief,
            "resolution_policy": policy,
            "pointers": pointers,
            "rejected_candidates": rejected,
            "fallback_path_used": len(rejected) > 0,
        }