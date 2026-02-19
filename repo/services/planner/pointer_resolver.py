from __future__ import annotations

import datetime
import json
import os
import pathlib
from typing import Any, Dict, List, Optional


class PointerResolver:
    def __init__(self, repo_root: pathlib.Path):
        self.repo_root = repo_root

    def _exists(self, relpath: str) -> bool:
        return (self.repo_root / relpath).exists()

    def _load_json(self, relpath: str) -> Optional[Dict[str, Any]]:
        path = self.repo_root / relpath
        if not path.exists():
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    def resolve(
        self,
        job_id: str,
        brief: Dict[str, Any],
        policy: str = "prefer_canon_strict_motion",
    ) -> Dict[str, Any]:
        """
        Deterministically resolves contract pointers based on brief intent and policy.
        """
        pointers: Dict[str, str] = {}
        rejected: List[Dict[str, Any]] = []

        # 1. Canon / Shared Contracts
        hero_reg = "repo/shared/hero_registry.v1.json"
        if self._exists(hero_reg):
            pointers["hero_registry"] = hero_reg
        else:
            rejected.append({"candidate_relpath": hero_reg, "reason": "not_found"})

        audio_man = "sandbox/assets/audio/audio_manifest.v1.json"
        if self._exists(audio_man):
            pointers["audio_manifest"] = audio_man
        else:
            rejected.append({"candidate_relpath": audio_man, "reason": "not_found"})

        bible = "repo/shared/series_bible.v1.json"
        if self._exists(bible):
            pointers["series_bible"] = bible
        else:
            rejected.append({"candidate_relpath": bible, "reason": "not_found"})

        # 2. Quality Target (Policy Driven)
        if "strict_motion" in policy:
            qt_strict = "repo/examples/quality_target.motion_strict.v1.example.json"
            if self._exists(qt_strict):
                pointers["quality_target"] = qt_strict
            else:
                # Fallback to standard if strict is missing
                qt_std = "repo/examples/quality_target.v1.example.json"
                if self._exists(qt_std):
                    pointers["quality_target"] = qt_std
                    rejected.append(
                        {"candidate_relpath": qt_strict, "reason": "missing_strict_target_fallback"}
                    )
                else:
                    rejected.append({"candidate_relpath": qt_std, "reason": "not_found"})
        else:
            qt_std = "repo/examples/quality_target.v1.example.json"
            if self._exists(qt_std):
                pointers["quality_target"] = qt_std
            else:
                rejected.append({"candidate_relpath": qt_std, "reason": "not_found"})

        # 3. Motion / Analyzer Artifacts (Keyword Heuristic for v1)
        motion_intent = str(brief.get("motion", "")).lower()
        prompt_text = str(brief.get("prompt", "")).lower()
        combined_intent = f"{motion_intent} {prompt_text}"

        if "dance" in combined_intent or "loop" in combined_intent:
            # Check for demo dance loop analysis
            pose = "repo/canon/demo_analyses/dance_loop.pose_checkpoints.v1.json"
            if self._exists(pose):
                pointers["pose_checkpoint"] = pose
            else:
                 rejected.append({"candidate_relpath": "repo/canon/demo_analyses/dance_loop.pose_checkpoints.v1.json", "reason": "dance_context_missing_pose"})

            beat = "repo/canon/demo_analyses/dance_loop.beat_grid.v1.json"
            if self._exists(beat):
                pointers["beat_grid"] = beat
            else:
                rejected.append({"candidate_relpath": "repo/canon/demo_analyses/dance_loop.beat_grid.v1.json", "reason": "dance_context_missing_beat"})

        # 4. Engine Adapter Registry
        engine_reg = "repo/shared/engine_adapter_registry.v1.json"
        if self._exists(engine_reg):
            pointers["engine_adapter_registry"] = engine_reg
        else:
             rejected.append({"candidate_relpath": engine_reg, "reason": "not_found"})

        # 5. Promotion Registry
        promo_reg = "repo/shared/promotion_registry.v1.json"
        if self._exists(promo_reg):
            pointers["promotion_registry"] = promo_reg

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