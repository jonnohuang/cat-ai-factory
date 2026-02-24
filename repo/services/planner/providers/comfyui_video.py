from __future__ import annotations

import json
import os
import pathlib
import re
import uuid
from typing import Any, Dict, List, Optional

from repo.shared.demo_asset_resolver import (
    DANCE_LOOP_CANDIDATES,
    GENERAL_BACKGROUND_CANDIDATES,
    resolve_first_existing,
)

from .base import BaseProvider, today_utc


def _slug(text: str) -> str:
    clean = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return clean[:48] or "comfyui-job"


def _prompt_text(prd: Dict[str, Any]) -> str:
    for key in ("prompt", "concept", "title"):
        v = prd.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return "Mochi comfyui continuity test"


def _is_dance_loop_intent(prd: Dict[str, Any]) -> bool:
    blob = " ".join(
        str(prd.get(k, "")) for k in ("prompt", "concept", "title", "niche")
    ).lower()
    return any(
        tok in blob
        for tok in ("dance", "loop", "choreo", "choreography", "groove", "beat")
    )


class ComfyUIVideoProvider(BaseProvider):
    @property
    def name(self) -> str:
        return "comfyui_video"

    @property
    def default_model(self) -> str:
        return "comfyui-video-stub"

    def __init__(self) -> None:
        self.model = self.default_model
        self.base_url = os.environ.get("COMFYUI_BASE_URL", "").strip()
        self.workflow_id = (
            os.environ.get("COMFYUI_WORKFLOW_ID", "").strip() or "caf_dance_loop_v1"
        )
        self.workflow_path = self._resolve_workflow_path(self.workflow_id)

    @staticmethod
    def _repo_root() -> pathlib.Path:
        # .../repo/services/planner/providers/comfyui_video.py -> workspace root at parents[4]
        return pathlib.Path(__file__).resolve().parents[4]

    def _resolve_workflow_path(self, workflow_id: str) -> Optional[pathlib.Path]:
        if not workflow_id:
            return None
        path = (
            self._repo_root() / "repo" / "workflows" / "comfy" / f"{workflow_id}.json"
        )
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict) or not payload:
                return None
        except Exception:
            return None
        return path

    def _load_json_rel(self, relpath: str) -> Optional[Dict[str, Any]]:
        if not isinstance(relpath, str) or not relpath:
            return None
        if relpath.startswith("/"):
            return None
        p = self._repo_root() / relpath
        if not p.exists():
            return None
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else None
        except Exception:
            return None

    def _pick_background_asset(
        self, quality_context: Optional[Dict[str, Any]], *, dance_intent: bool
    ) -> str:
        # Prefer sample-ingest source video when available.
        if isinstance(quality_context, dict):
            resolver = quality_context.get("pointer_resolver")
            if isinstance(resolver, dict):
                manifest_rel = resolver.get("sample_ingest_manifest_relpath")
                manifest = (
                    self._load_json_rel(str(manifest_rel))
                    if isinstance(manifest_rel, str)
                    else None
                )
                if isinstance(manifest, dict):
                    source = manifest.get("source")
                    if isinstance(source, dict):
                        src_rel = source.get("video_relpath")
                        if isinstance(src_rel, str) and src_rel.strip():
                            src = src_rel.strip()
                            if not src.startswith("sandbox/") and not src.startswith("repo/"):
                                src = f"sandbox/{src}"
                            return src

        # Fail-loud for dance-loop intent: do not silently route to unrelated fight composite.
        sandbox_root = self._repo_root() / "sandbox"
        if dance_intent:
            selected = resolve_first_existing(
                sandbox_root=sandbox_root, candidates=DANCE_LOOP_CANDIDATES
            )
        else:
            selected = resolve_first_existing(
                sandbox_root=sandbox_root, candidates=GENERAL_BACKGROUND_CANDIDATES
            )
        if selected:
            if not selected.startswith("sandbox/") and not selected.startswith("repo/"):
                return f"sandbox/{selected}"
            return selected

        # Fail loud early: do not provide a 'pretend' baseline video if resolution fails.
        msg = (
            f"Failed to resolve background asset for intent (dance={dance_intent}). "
            f"Expected one of {GENERAL_BACKGROUND_CANDIDATES if not dance_intent else DANCE_LOOP_CANDIDATES} "
            "to exist under sandbox/"
        )
        raise RuntimeError(msg)

    def _pick_identity_asset(self, quality_context: Optional[Dict[str, Any]]) -> str:
        # Prefer sample-ingest identity anchor when available.
        if isinstance(quality_context, dict):
            resolver = quality_context.get("pointer_resolver")
            if isinstance(resolver, dict):
                manifest_rel = resolver.get("sample_ingest_manifest_relpath")
                manifest = (
                    self._load_json_rel(str(manifest_rel))
                    if isinstance(manifest_rel, str)
                    else None
                )
                if isinstance(manifest, dict):
                    assets = manifest.get("assets", {})
                    identity = assets.get("identity_anchor")
                    if isinstance(identity, dict):
                        rel = identity.get("relpath")
                        if isinstance(rel, str) and rel.strip():
                            return rel.strip()
        # Fallback to repo-anchored Mochi portrait
        rel = "repo/assets/identity/mochi/front.png"
        full = self._repo_root() / rel
        if not full.exists():
            print(f"WARNING: Preferred identity anchor not found: {full}")
        return rel

    def generate_job(
        self,
        prd: Dict[str, Any],
        inbox: Optional[List[Dict[str, Any]]] = None,
        hero_registry: Optional[Dict[str, Any]] = None,
        quality_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        _ = inbox, hero_registry
        if not self.base_url:
            raise RuntimeError(
                "planner provider=comfyui_video requires COMFYUI_BASE_URL "
                "(set and export it in the current shell before running planner_cli)"
            )
        if self.workflow_path is None:
            raise RuntimeError(
                "planner provider=comfyui_video requires a valid repo workflow JSON for "
                f"COMFYUI_WORKFLOW_ID={self.workflow_id!r} under repo/workflows/comfy/"
            )
        print(
            "INFO planner provider=comfyui_video "
            f"workflow_id={self.workflow_id} workflow_path={self.workflow_path.as_posix()}"
        )
        prompt = _prompt_text(prd)
        basename = _slug(prompt)
        date = prd.get("date") if isinstance(prd.get("date"), str) else today_utc()
        niche = prd.get("niche") if isinstance(prd.get("niche"), str) else "cats"
        workflow_tag = self.workflow_id.replace("_", "-")
        is_dance = _is_dance_loop_intent(prd)
        background_asset = self._pick_background_asset(
            quality_context, dance_intent=is_dance
        )
        identity_asset = self._pick_identity_asset(quality_context)
        pose_video_asset = (
            background_asset
            if is_dance
            else "sandbox/assets/demo/processed/dance_loop.mp4"
        )

        # Resolve Hero and Costume (Existing Logic)
        hero_id = "mochi-grey-tabby"  # Default fallback
        if isinstance(hero_registry, dict):
            pass

        # Construct Dynamic Prompt (Existing Logic)
        hero = None
        costume = None
        if isinstance(hero_registry, dict):
            # ... (keep existing registry lookup) ...
            heroes = hero_registry.get("heroes", [])
            hero = next((h for h in heroes if h["hero_id"] == hero_id), None)
            pass

        # ... (keep existing local registry loading) ...
        shared_root = self._repo_root() / "repo" / "shared"
        hero_reg_path = shared_root / "hero_registry.v1.json"
        costume_reg_path = shared_root / "costume_profiles.v1.json"

        hero_data = self._load_json_rel("repo/shared/hero_registry.v1.json") or {}
        costume_data = self._load_json_rel("repo/shared/costume_profiles.v1.json") or {}

        prompt_lower = prompt.lower()
        selected_hero = None
        for h in hero_data.get("heroes", []):
            if h["hero_id"] in prompt_lower or h["name"]["en"].lower() in prompt_lower:
                selected_hero = h
                break
        if not selected_hero:
            selected_hero = next(
                (
                    h
                    for h in hero_data.get("heroes", [])
                    if h["hero_id"] == "mochi-grey-tabby"
                ),
                None,
            )

        traits_str = "cute cat"
        costume_str = "costume"

        if selected_hero:
            t = selected_hero.get("traits", {})
            traits_str = f"{selected_hero['name']['en']} {t.get('primary_color','')} {t.get('coat_type','')}"
            if t.get("eye_color"):
                traits_str += f", {t['eye_color']} eyes"
            c_def = selected_hero.get("costume", {})
            c_id = c_def.get("id")
            c_profile = next(
                (c for c in costume_data.get("profiles", []) if c["id"] == c_id), None
            )
            if c_profile:
                costume_str = ", ".join(c_profile.get("cues", []))
            else:
                costume_str = c_def.get("notes", "costume")

        # --- NEW: Inject Analysis Style Tokens ---
        style_tokens = []
        reverse_prompt_data = None
        if isinstance(quality_context, dict):
            reverse_prompt_data = quality_context.get("reverse_prompt")
            if isinstance(reverse_prompt_data, dict):
                suggestions = reverse_prompt_data.get("suggestions", {})
                style_tokens = suggestions.get("vendor_style_tokens", [])

        style_suffix = ", ".join(style_tokens) if style_tokens else "high fidelity, 8k"

        # Refined prompt for individual shots: strip "cast" and character lists to avoid hallucinations
        refined_prompt = prompt
        # 1. Strip "hero kitten cast"
        pattern_cast = re.compile(re.escape("hero kitten cast"), re.IGNORECASE)
        refined_prompt = pattern_cast.sub("Hero Kitten", refined_prompt)

        # 2. Strip parenthetical character lists like "(Mochi, Ronnie, Mione)" or "(Ronnie, Mochi, Mione)"
        # This prevents the single-hero AI from trying to generate multiple cats.
        pattern_list = re.compile(r"\s*\(.*?\)", re.IGNORECASE)
        refined_prompt = pattern_list.sub("", refined_prompt)

        comfy_positive = (
            f"{refined_prompt}. "
            f"masterpiece, best quality, single hero character, {traits_str}, "
            f"{costume_str}, "
            f"full body, smooth motion, {style_suffix}."
        )

        comfy_negative = (
            "human, person, woman, man, human face, human body, multiple characters, crowd, duplicate subject, "
            "extra limbs, giant ears, mouse ears, identity drift, costume drift, flicker, background drift, "
            "blur, low detail, deformed face"
        )
        comfy_seed = 123456
        # Duration extraction
        length_seconds = 12
        if "24s" in prompt_lower or "24 seconds" in prompt_lower:
            length_seconds = 24
        elif "16s" in prompt_lower or "16 seconds" in prompt_lower:
            length_seconds = 16

        job: Dict[str, Any] = {
            "job_id": f"{basename[:34]}-comfy",
            "date": date,
            "lane": "ai_video",
            "niche": niche,
            "video": {
                "length_seconds": length_seconds,
                "aspect_ratio": "9:16",
                "fps": 30,
                "resolution": "1080x1920",
            },
            "script": {
                "hook": "Mochi dance loop test",
                "voiceover": (
                    f"ComfyUI adapter scaffold run for: {prompt}. "
                    f"Use workflow {self.workflow_id} and keep continuity stable for QC gates."
                ),
                "ending": "Loop cleanly for retry checks.",
            },
            "shots": [
                {
                    "shot_id": "shot_0010",
                    "t": 0,
                    "visual": "wide stage, tracking motion",
                    "action": "start groove",
                    "caption": "Intro buildup",
                },
                {
                    "shot_id": "shot_0020",
                    "t": int(length_seconds * 0.2),
                    "visual": "mid shot, energetic vibe",
                    "action": "side step",
                    "caption": "On beat",
                },
                {
                    "shot_id": "shot_0030",
                    "t": int(length_seconds * 0.4),
                    "visual": "mid shot",
                    "action": "spin",
                    "caption": "Spin",
                },
                {
                    "shot_id": "shot_0040",
                    "t": int(length_seconds * 0.6),
                    "visual": "wide stage, build up",
                    "action": "pose hit",
                    "caption": "Intensity build",
                },
                {
                    "shot_id": "shot_0050",
                    "t": int(length_seconds * 0.8),
                    "visual": "mid shot, drop depth",
                    "action": "bounce",
                    "caption": "The drop",
                },
                {
                    "shot_id": "shot_0060",
                    "t": length_seconds - 1,
                    "visual": "wide stage",
                    "action": "reset",
                    "caption": "Loop",
                },
            ],
            "captions": ["Mochi", "On beat", "ComfyUI lane", "Loop"],
            "hashtags": ["#cat", "#shorts", "#dance"],
            "render": {
                "background_asset": background_asset,
                "subtitle_style": "big_bottom",
                "output_basename": f"{basename}-{workflow_tag}-comfy",
            },
            "continuity_pack": {
                "relpath": "repo/examples/episode_continuity_pack.identity_only.v1.example.json"
            },
            "comfyui": {
                "provider": "comfyui_video",
                "base_url": self.base_url,
                "workflow_id": self.workflow_id,
                "workflow_relpath": f"repo/workflows/comfy/{self.workflow_id}.json",
                "client_id": str(uuid.uuid4()),
                "bindings": {
                    "positive_prompt": comfy_positive,
                    "negative_prompt": comfy_negative,
                    "seed": comfy_seed,
                    "positive_nodes": ["input_prompt", "identity_prompt"],
                    "negative_nodes": ["input_negative_prompt"],
                    "seed_nodes": ["sampler"],
                    "identity_image_path": identity_asset,
                    "pose_video_path": pose_video_asset,
                },
                "poll": {
                    "timeout_seconds": 900,
                    "interval_seconds": 2,
                },
            },
            "generation_policy": {
                "registry_relpath": "repo/shared/engine_adapter_registry.v1.json",
                "baseline_video_provider": "comfyui_video",
                "baseline_frame_provider": "vertex_imagen",
                "route_mode": os.environ.get("CAF_ENGINE_ROUTE_MODE", "production")
                .strip()
                .lower()
                or "production",
                "selected_video_provider": "comfyui_video",
                "selected_frame_provider": "vertex_imagen",
                "video_provider_order": ["comfyui_video"],
                "frame_provider_order": ["vertex_imagen"],
                "lab_challenger_order": [],
                "motion_constraints": [],
                "post_process_order": [],
            },
        }

        return job
