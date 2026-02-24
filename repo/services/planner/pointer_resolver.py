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

    def _resolve_core_pointer(
        self,
        tags: List[str],
        key: str,
        pointers: Dict[str, str],
        rejected: List[Dict[str, Any]],
    ):
        """Helper to resolve a core contract pointer via AssetResolver."""
        paths = self.asset_resolver.find_assets(tags, asset_type="contract")
        if paths:
            # Verify existence on disk to be extra safe
            if self._exists(paths[0]):
                pointers[key] = paths[0]
                return
            else:
                rejected.append(
                    {
                        "candidate_relpath": paths[0],
                        "reason": "file_missing_on_disk",
                        "tags": tags,
                    }
                )
        else:
            rejected.append(
                {
                    "candidate_relpath": f"tag_query:{tags}",
                    "reason": "not_found_in_manifest",
                    "tags": tags,
                }
            )

    def resolve(
        self,
        job_id: str,
        brief: Dict[str, Any],
        policy: str = "prefer_canon_strict_motion",
        hero_registry: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Deterministically resolves contract pointers based on brief intent and policy.
        Authority derived solely from AssetRAG manifest.
        """
        pointers: Dict[str, str] = {}
        rejected: List[Dict[str, Any]] = []

        # 0. Auto-discovery from prompt if structured fields are missing
        prompt_text = str(brief.get("prompt", "")).lower()

        # Discover heroes from registry if not explicitly provided
        if not brief.get("heroes") and hero_registry:
            discovered_heroes = []
            for hero in hero_registry.get("heroes", []):
                hid = hero.get("hero_id")
                name = str(hero.get("name", {}).get("en", "")).lower()
                if hid and (hid in prompt_text or (name and name in prompt_text)):
                    discovered_heroes.append(hid)
            if discovered_heroes:
                brief["heroes"] = discovered_heroes

        # Discover style_id if not explicitly provided
        if not brief.get("style_id"):
            # Resolve the style registry first to scan it
            style_reg_paths = self.asset_resolver.find_assets(["style", "registry"], asset_type="contract")
            if style_reg_paths and self._exists(style_reg_paths[0]):
                try:
                    with open(self.repo_root / style_reg_paths[0], "r") as f:
                        style_registry = json.load(f)
                    for style in style_registry.get("styles", []):
                        sid = style.get("style_id")
                        if sid and sid in prompt_text.replace("_", "-"):
                            brief["style_id"] = sid
                            break
                except Exception:
                    pass

        # 1. Canon / Shared Contracts (Resolved via RAG)
        self._resolve_core_pointer(
            ["hero", "registry"], "hero_registry", pointers, rejected
        )
        self._resolve_core_pointer(
            ["bible", "series"], "series_bible", pointers, rejected
        )
        self._resolve_core_pointer(
            ["engine", "registry"], "engine_adapter_registry", pointers, rejected
        )
        self._resolve_core_pointer(
            ["promotion", "registry"], "promotion_registry", pointers, rejected
        )

        # Special Case: Audio Manifest (Dynamic Asset)
        audio_paths = self.asset_resolver.find_assets(
            ["audio", "manifest"], asset_type="contract"
        )
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
            std_qt = self.asset_resolver.find_assets(
                ["quality", "target"], asset_type="contract"
            )
            if std_qt:
                pointers["quality_target"] = std_qt[0]
                if "strict" in target_tags:
                    rejected.append(
                        {
                            "candidate_relpath": "strict_quality_target",
                            "reason": "missing_falling_back_to_std",
                        }
                    )
            else:
                rejected.append(
                    {
                        "candidate_relpath": "quality_target_query",
                        "reason": "not_found_in_manifest",
                    }
                )

        # 3. Motion / Analyzer Artifacts (Keyword Heuristic)
        motion_intent = str(brief.get("motion", "")).lower()
        prompt_text = str(brief.get("prompt", "")).lower()
        combined_intent = f"{motion_intent} {prompt_text}"

        if "dance" in combined_intent or "loop" in combined_intent:
            # 3a. Check for explicit motion template via RAG
            templates = self.asset_resolver.find_assets(
                ["motion", "template", "dance", "loop"], asset_type="contract"
            )
            if templates and self._exists(templates[0]):
                template_path = templates[0]
                pointers["motion_template"] = template_path

                # Recursively resolve template-locked contracts if possible
                try:
                    with open(self.repo_root / template_path, "r") as f:
                        template_data = json.load(f)
                    constraints = template_data.get("constraints", {})

                    # Resolve pose from template reference
                    pose_ref = constraints.get("pose_checkpoints_ref")
                    if pose_ref and self._exists(pose_ref):
                        pointers["pose_checkpoint"] = pose_ref

                    # Resolve beat from template reference
                    beat_ref = constraints.get("beat_grid_ref")
                    if beat_ref and self._exists(beat_ref):
                        pointers["beat_grid"] = beat_ref

                except Exception as e:
                    rejected.append({
                        "candidate_relpath": template_path,
                        "reason": f"error_parsing_motion_template: {str(e)}"
                    })
            else:
                # Fallback to legacy individual resolution
                # Resolve pose via RAG
                poses = self.asset_resolver.find_assets(
                    ["dance", "loop", "pose"], asset_type="contract"
                )
                if poses:
                    pointers["pose_checkpoint"] = poses[0]
                else:
                    rejected.append(
                        {
                            "candidate_relpath": "dance_loop_pose_contract_rag",
                            "reason": "not_found_in_asset_manifest",
                        }
                    )

                # Resolve beat via RAG
                beats = self.asset_resolver.find_assets(
                    ["dance", "loop", "beat"], asset_type="contract"
                )
                if beats:
                    pointers["beat_grid"] = beats[0]
                else:
                    rejected.append(
                        {
                            "candidate_relpath": "dance_loop_beat_contract_rag",
                            "reason": "not_found_in_asset_manifest",
                        }
                    )

        # 4. Hero Identity Anchors (Constraint-first Stabilization)
        # Identify heroes from the brief and resolve their identity pack references.
        brief_heroes = brief.get("heroes", [])
        if not isinstance(brief_heroes, list):
            brief_heroes = []

        if hero_registry and brief_heroes:
            registry_heroes = hero_registry.get("heroes", [])
            for hid in brief_heroes:
                # Find matching hero in registry
                hero_data = next((h for h in registry_heroes if h.get("hero_id") == hid), None)
                if hero_data:
                    id_pack = hero_data.get("identity_pack")
                    if id_pack:
                        pack_ref = id_pack.get("ref")
                        if pack_ref and self._exists(pack_ref):
                            # Store in pointers; suffix with hero_id to handle multi-hero briefs
                            pointers[f"identity_pack_{hid}"] = pack_ref
                        else:
                            rejected.append({
                                "candidate_relpath": pack_ref or f"identity_pack:{hid}",
                                "reason": "identity_pack_missing_or_invalid",
                                "hero_id": hid
                            })

        # 5. Modular Style / Light / Camera Packs
        style_id = brief.get("style_id")
        if style_id:
            # Resolve the style registry first
            style_reg_path = pointers.get("style_registry")
            if not style_reg_path:
                style_reg_paths = self.asset_resolver.find_assets(["style", "registry"], asset_type="contract")
                if style_reg_paths and self._exists(style_reg_paths[0]):
                    style_reg_path = style_reg_paths[0]
                    pointers["style_registry"] = style_reg_path

            if style_reg_path:
                try:
                    with open(self.repo_root / style_reg_path, "r") as f:
                        style_registry = json.load(f)

                    styles = style_registry.get("styles", [])
                    style_data = next((s for s in styles if s.get("style_id") == style_id), None)

                    if style_data:
                        fragments = style_data.get("prompt_fragments", [])
                        for frag in fragments:
                            # If fragment looks like a pack ID, resolve it
                            if any(frag.startswith(prefix) for prefix in ["style-pack-", "light-pack-", "camera-pack-"]):
                                pack_paths = self.asset_resolver.find_assets([frag], asset_type="contract")
                                if pack_paths and self._exists(pack_paths[0]):
                                    pointers[f"pack_{frag}"] = pack_paths[0]
                                else:
                                    rejected.append({
                                        "candidate_relpath": f"pack:{frag}",
                                        "reason": "modular_pack_not_found_in_manifest",
                                        "style_id": style_id
                                    })
                    else:
                        rejected.append({
                            "candidate_relpath": f"style_id:{style_id}",
                            "reason": "style_id_not_found_in_registry"
                        })
                except Exception as e:
                    rejected.append({
                        "candidate_relpath": style_reg_path,
                        "reason": f"error_parsing_style_registry: {str(e)}"
                    })

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
