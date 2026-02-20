from __future__ import annotations

import base64
import json
import os
import pathlib
import re
import shutil
import statistics
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

from ..util.json_extract import extract_json_object
from ..util.redact import redact_text
from ...budget.pricing import (
    COST_GEMINI_PRO_INPUT_1M,
    COST_GEMINI_PRO_OUTPUT_1M,
    COST_VERTEX_IMAGEN_IMAGE,
    COST_VERTEX_VEO_VIDEO_SEC,
)
from ...budget.tracker import BudgetTracker
from .base import BaseProvider
from .gemini_ai_studio import (
    GeminiAIStudioProvider,
    _build_prompt,
    _build_repair_prompt,
    _build_schema_fix_prompt,
    _looks_truncated,
    _validate_job,
)


class _VertexBaseProvider(BaseProvider):
    """Planner-side Vertex adapter with safe fallback to AI Studio."""

    lane_hint: Optional[str] = None
    vertex_model_env: str = ""
    vertex_model_default: str = ""
    provider_name: str = ""

    @property
    def name(self) -> str:
        return self.provider_name

    @property
    def default_model(self) -> str:
        return self.vertex_model_default

    def __init__(self) -> None:
        self.project_id = os.environ.get("VERTEX_PROJECT_ID", "").strip()
        self.location = os.environ.get("VERTEX_LOCATION", "").strip() or "us-central1"
        self.access_token = os.environ.get("VERTEX_ACCESS_TOKEN", "").strip()
        self.model = os.environ.get(self.vertex_model_env, self.vertex_model_default)
        self._last_raw_text: Optional[str] = None
        self._last_path: str = "vertex"
        self._auth_source: str = "none"
        self._fallback_reason: str = ""
        self._generated_asset_path: str = ""
        self._selected_hero: Optional[Dict[str, Any]] = None
        self._lane_a_error: str = ""
        self._quality_context: Optional[Dict[str, Any]] = None
        self._last_reference_image_rels: List[str] = []
        self._budget = BudgetTracker()

    def _preprocess_job_schema_defaults(self, job: Dict[str, Any]) -> Dict[str, Any]:
        """Ensures required schema fields are present and typed correctly before validation."""
        if not isinstance(job, dict):
            return job
        
        # 0. Type Fixes (Floats to Ints where required by schema)
        video = job.get("video", {})
        if isinstance(video, dict):
            if "length_seconds" in video:
                try:
                    video["length_seconds"] = int(round(float(video["length_seconds"])))
                except (ValueError, TypeError):
                    video["length_seconds"] = 15
            if "fps" in video:
                try:
                    video["fps"] = int(round(float(video["fps"])))
                except (ValueError, TypeError):
                    video["fps"] = 30
        
        shots = job.get("shots", [])
        if isinstance(shots, list):
            for shot in shots:
                if isinstance(shot, dict) and "t" in shot:
                    try:
                        shot["t"] = int(round(float(shot["t"])))
                    except (ValueError, TypeError):
                        pass

        # 1. Captions (required, min 4)
        if not job.get("captions") or len(job.get("captions", [])) < 4:
            shots = job.get("shots", [])
            caps = [s.get("caption", "...") for s in shots if isinstance(s, dict) and s.get("caption")]
            if len(caps) < 4:
                caps.extend(["Mochi is rhythm!", "Meow moves!", "Dino cat style!", "Dance loop magic!"])
            job["captions"] = caps[:24]
            
        # 2. Hashtags (required, min 3)
        if not job.get("hashtags") or len(job.get("hashtags", [])) < 3:
            job["hashtags"] = ["#Mochi", "#CatDance", "#DinoCostume", "#CutePets"]
            
        # 3. Render (required: background_asset, subtitle_style, output_basename)
        render = job.setdefault("render", {})
        if not render.get("background_asset"):
            render["background_asset"] = "assets/demo/mochi_front.png"
        if not render.get("subtitle_style"):
            render["subtitle_style"] = "big_bottom"
        if not render.get("output_basename"):
            job_id = job.get("job_id", "mochi-generated")
            render["output_basename"] = job_id
            
        return job

    def generate_job(
        self,
        prd: Dict[str, Any],
        inbox: Optional[List[Dict[str, Any]]] = None,
        hero_registry: Optional[Dict[str, Any]] = None,
        quality_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        self._quality_context = quality_context if isinstance(quality_context, dict) else None
        self._selected_hero = _select_target_hero(hero_registry, prd, inbox or [])
        if self._selected_hero:
            _persist_hero_bundle(self._selected_hero)

        if not self._vertex_ready():
            return self._fallback_generate(prd, inbox, hero_registry, quality_context)

        prompt = _build_prompt(prd, inbox or [], hero_registry, quality_context)
        raw = self._generate_content(prompt)
        self._last_raw_text = raw

        if _looks_truncated(raw):
            repaired = self._generate_content(_build_repair_prompt(prompt, raw))
            self._last_raw_text = repaired
            job = extract_json_object(repaired)
            job = self._preprocess_job_schema_defaults(job)
            ok, err = _validate_job(job)
            if not ok:
                raise RuntimeError(f"Job failed validation after repair: {err}")
            job = self._apply_lane_hint(job)
            return self._finalize_media_handoff(job, prd)

        try:
            job = extract_json_object(raw)
            job = self._preprocess_job_schema_defaults(job)
        except Exception:
            repaired = self._generate_content(_build_repair_prompt(prompt, raw))
            self._last_raw_text = repaired
            job = extract_json_object(repaired)
            job = self._preprocess_job_schema_defaults(job)
            ok, err = _validate_job(job)
            if not ok:
                raise RuntimeError(f"Job failed validation after repair: {err}")
            job = self._apply_lane_hint(job)
            return self._finalize_media_handoff(job, prd)

        ok, err = _validate_job(job)
        if ok:
            job = self._apply_lane_hint(job)
            return self._finalize_media_handoff(job, prd)

        fixed = self._generate_content(_build_schema_fix_prompt(prompt, raw, err))
        self._last_raw_text = fixed
        fixed_job = extract_json_object(fixed)
        fixed_job = self._preprocess_job_schema_defaults(fixed_job)
        ok2, err2 = _validate_job(fixed_job)
        if not ok2:
            raise RuntimeError(f"Job failed validation after schema fix: {err2}")
        fixed_job = self._apply_lane_hint(fixed_job)
        return self._finalize_media_handoff(fixed_job, prd)

    def _vertex_ready(self) -> bool:
        if not self.project_id:
            self._fallback_reason = "VERTEX_PROJECT_ID missing"
            return False
        token, source = self._resolve_access_token()
        if not token:
            self._fallback_reason = "VERTEX_ACCESS_TOKEN missing"
            return False
        self.access_token = token
        self._auth_source = source
        return True

    def _resolve_access_token(self) -> Tuple[str, str]:
        if self.access_token:
            return self.access_token, "env"

        # Prefer ADC when available (Cloud Run service account or local ADC).
        try:
            import google.auth  # type: ignore
            from google.auth.transport.requests import Request  # type: ignore

            creds, _project = google.auth.default(
                scopes=["https://www.googleapis.com/auth/cloud-platform"]
            )
            if creds and not creds.valid:
                creds.refresh(Request())
            token = getattr(creds, "token", None)
            if token:
                return str(token), "adc"
        except Exception:
            pass

        return "", "none"

    def _fallback_generate(
        self,
        prd: Dict[str, Any],
        inbox: Optional[List[Dict[str, Any]]],
        hero_registry: Optional[Dict[str, Any]],
        quality_context: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        self._last_path = "ai_studio_fallback"
        print(
            f"INFO planner provider={self.name} fallback=ai_studio reason={self._fallback_reason}"
        )
        fallback = GeminiAIStudioProvider()
        job = fallback.generate_job(prd, inbox, hero_registry, quality_context)
        job = self._apply_lane_hint(job)
        if self.provider_name == "vertex_veo":
            context_text = _job_context_text(job, prd)
            if _job_uses_demo_background(job) and not _allow_demo_background_fallback():
                raise RuntimeError(
                    "Planner fail-loud: vertex_veo resolved to demo background_asset via fallback. "
                    "Set CAF_ALLOW_DEMO_BACKGROUND_FALLBACK=1 only for explicit dev-only runs."
                )
            if self._must_require_generated_video(context_text) and _job_uses_demo_background(job):
                raise RuntimeError(
                    "Planner fail-loud: dance context requires generated video; demo background fallback is disallowed."
                )
        return job

    def _apply_lane_hint(self, job: Dict[str, Any]) -> Dict[str, Any]:
        if self.lane_hint and not job.get("lane"):
            job["lane"] = self.lane_hint
            print(
                f"INFO planner provider={self.name} lane_hint_applied={self.lane_hint} path={self._last_path}"
            )
        return job

    def _finalize_media_handoff(self, job: Dict[str, Any], prd: Dict[str, Any]) -> Dict[str, Any]:
        """Attach planner-generated assets for end-to-end original media output.

        PR-25 wiring: try generating an Imagen seed frame and route through deterministic
        image_motion rendering.
        """
        self._attach_default_audio(job, prd)
        
        # Ensure the rich prompt (with motion/style tokens) is preserved for the worker
        hero_desc = _hero_prompt_descriptor(self._selected_hero)
        rich_prompt = _seed_prompt_from_job(job, prd, hero_desc, self._quality_context)
        job["prompt"] = rich_prompt
        
        context_text = _job_context_text(job, prd)

        # Prefer true lane-A generated video when available.
        lane_a_video = self._try_generate_lane_a_video(job, prd)
        if lane_a_video:
            self._generated_asset_path = lane_a_video
            render = job.setdefault("render", {})
            render["background_asset"] = lane_a_video
            job["lane"] = "ai_video"
            job.pop("image_motion", None)
            print(
                f"INFO planner provider={self.name} generated_video_asset={lane_a_video} lane=ai_video"
            )
            return job
        if self._must_require_generated_video(context_text):
            reason = self._lane_a_error or "vertex video generation returned no asset"
            raise RuntimeError(
                f"Planner fail-loud: {self.name} requires generated video for dance context, but none was produced ({reason})"
            )

        if self._selected_hero and _is_dance_context(context_text):
            gen_seed_rels = self._try_generate_seed_frames(job, prd)
            hero_seed_rels = _hero_seed_frames(self._selected_hero)
            # Keep hero reference seeds as fallback only; do not override generated dance seeds.
            seed_rels = _merge_unique_seeds(gen_seed_rels, hero_seed_rels, max_items=3)
            if seed_rels:
                self._generated_asset_path = ",".join(seed_rels)
                render = job.setdefault("render", {})
                render["background_asset"] = seed_rels[0]
                job["lane"] = "image_motion"
                motion_preset = _choose_motion_preset(job, prd, len(seed_rels))
                job["image_motion"] = {
                    "seed_frames": seed_rels,
                    "motion_preset": motion_preset,
                }
                print(
                    "INFO planner provider="
                    f"{self.name} hero_consistency_mode=on hero_id={self._selected_hero.get('hero_id')} "
                    f"generated_seeds={len(gen_seed_rels)} reference_seeds={len(hero_seed_rels)} "
                    f"selected_seeds={len(seed_rels)} motion_preset={motion_preset} lane=image_motion"
                )
                return job

        seed_rels = self._try_generate_seed_frames(job, prd)
        if not seed_rels:
            return job

        self._generated_asset_path = ",".join(seed_rels)
        render = job.setdefault("render", {})
        render["background_asset"] = seed_rels[0]
        job["lane"] = "image_motion"
        motion_preset = _choose_motion_preset(job, prd, len(seed_rels))
        job["image_motion"] = {
            "seed_frames": seed_rels,
            "motion_preset": motion_preset,
        }
        print(
            f"INFO planner provider={self.name} generated_seed_frames={len(seed_rels)} motion_preset={motion_preset} lane=image_motion"
        )
        return job

    def _try_generate_lane_a_video(self, job: Dict[str, Any], prd: Dict[str, Any]) -> str:
        # Base provider does not generate video assets.
        return ""

    def _must_require_generated_video(self, context_text: str) -> bool:
        return self.provider_name == "vertex_veo" and _is_dance_context(context_text)

    def _attach_default_audio(self, job: Dict[str, Any], prd: Dict[str, Any]) -> None:
        existing = job.get("audio")
        if isinstance(existing, dict) and existing.get("audio_asset"):
            return

        context_text = _job_context_text(job, prd)
        audio_asset = _pick_default_audio_asset(context_text)
        if not audio_asset:
            return

        job["audio"] = {"audio_asset": audio_asset}
        print(
            f"INFO planner provider={self.name} audio_asset_selected={audio_asset}"
        )

    def _try_generate_seed_frames(self, job: Dict[str, Any], prd: Dict[str, Any]) -> List[str]:
        if not self.project_id or not self.access_token:
            return []

        hero_desc = _hero_prompt_descriptor(self._selected_hero)
        prompt = _seed_prompt_from_job(job, prd, hero_desc, self._quality_context)
        desired = 3 if _is_dance_context(_job_context_text(job, prd)) else 1
        context = _job_context_text(job, prd)
        kitten_mode = _is_kitten_context(context)
        candidate_pool = desired
        if desired > 1 or kitten_mode:
            candidate_pool = _clamp_int(os.environ.get("VERTEX_IMAGEN_CANDIDATES", "3"), 1, 6, 3)
            candidate_pool = max(candidate_pool, desired)
        image_batch = self._generate_image_batch(prompt, candidate_pool)
        if not image_batch:
            return []

        ranked = sorted(
            image_batch,
            key=lambda b: _score_image_candidate_bytes(b, kitten_mode),
            reverse=True,
        )
        selected = ranked[:desired]
        print(
            f"INFO planner provider={self.name} imagen_candidates={len(image_batch)} "
            f"selected={len(selected)} kitten_mode={str(kitten_mode).lower()}"
        )

        job_id = str(job.get("job_id", "job-generated")).strip() or "job-generated"
        safe_job_id = _safe_slug(job_id)
        rel_dir = f"assets/generated/{safe_job_id}"
        out_dir = _repo_root_path() / "sandbox" / rel_dir
        out_dir.mkdir(parents=True, exist_ok=True)
        rel_paths: List[str] = []
        for idx, image_bytes in enumerate(selected, start=1):
            out_path = out_dir / f"seed-{idx:04d}.png"
            out_path.write_bytes(image_bytes)
            rel_paths.append(f"{rel_dir}/seed-{idx:04d}.png")
        return rel_paths

    def _generate_image_batch(self, prompt: str, sample_count: int) -> List[bytes]:
        model = os.environ.get("VERTEX_IMAGEN_GEN_MODEL", "imagen-3.0-generate-001")
        count = max(1, min(6, sample_count))

        est_cost = count * COST_VERTEX_IMAGEN_IMAGE
        if not self._budget.check_budget(est_cost):
            print(
                f"WARNING planner provider={self.name} budget_exceeded for imagen batch (cost={est_cost:.4f})"
            )
            return []

        endpoint = (
            f"https://{self.location}-aiplatform.googleapis.com/v1/"
            f"projects/{self.project_id}/locations/{self.location}/"
            f"publishers/google/models/{model}:predict"
        )
        payload = {
            "instances": [{"prompt": prompt}],
            "parameters": {"sampleCount": count, "aspectRatio": "9:16"},
        }
        req = urllib.request.Request(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                raw = resp.read().decode("utf-8")
            data = json.loads(raw)
        except Exception as ex:
            print(
                f"WARNING planner provider={self.name} imagen_seed_failed={type(ex).__name__}"
            )
            return []

        predictions = data.get("predictions")
        if not isinstance(predictions, list) or not predictions:
            return []
        out: List[bytes] = []
        for pred in predictions[:count]:
            if not isinstance(pred, dict):
                continue
            b64 = pred.get("bytesBase64Encoded")
            if not isinstance(b64, str) or not b64:
                continue
            try:
                out.append(base64.b64decode(b64))
            except Exception:
                continue

        if out:
            import uuid

            self._budget.record_spending(est_cost, f"vertex-imagen-{uuid.uuid4()}")
        return out

    def _generate_content(self, prompt: str) -> str:
        if os.environ.get("CAF_VEO_MOCK", "").strip().lower() in ("1", "true", "yes"):
            print(f"INFO planner provider={self.name} CAF_VEO_MOCK=1; bypassing Gemini planning call.")
            # Return a mock job contract that matches the "dance loop" demo
            mock_job = {
                "job_id": "mock-veo-dance-loop",
                "date": "2024-07-30",
                "niche": "Cat Dance",
                "video": {
                    "length_seconds": 12,
                    "aspect_ratio": "9:16",
                    "fps": 30,
                    "resolution": "1080x1920"
                },
                "script": {
                    "hook": "Mochi's Dino Dance!",
                    "voiceover": "Watch Mochi groovy in a dinosaur suit! This 12 second loop captures the magic of the studio.",
                    "ending": "Follow for more!"
                },
                "shots": [
                    {
                        "t": 0,
                        "visual": "Mochi dancing in a dino suit in a studio.",
                        "action": "dance | facts:camera=locked,brightness=mid,palette=#5F6A7A",
                        "caption": "Mochi's Dino Dance!"
                    },
                    {
                        "t": 2,
                        "visual": "Mochi spinning in the dino suit.",
                        "action": "spin | facts:camera=locked,brightness=mid,palette=#5F6A7A",
                        "caption": "Spinning Mochi!"
                    },
                    {
                        "t": 4,
                        "visual": "Mochi jumping with paws up.",
                        "action": "jump | facts:camera=locked,brightness=mid,palette=#5F6A7A",
                        "caption": "Paws up!"
                    },
                    {
                        "t": 6,
                        "visual": "Mochi doing a tail wiggle.",
                        "action": "wiggle | facts:camera=locked,brightness=mid,palette=#5F6A7A",
                        "caption": "Tail wiggle!"
                    },
                    {
                        "t": 8,
                        "visual": "Mochi stomping rhythmicallly.",
                        "action": "stomp | facts:camera=locked,brightness=mid,palette=#5F6A7A",
                        "caption": "Dino stomps!"
                    },
                    {
                        "t": 10,
                        "visual": "Mochi striking a final pose.",
                        "action": "pose | facts:camera=locked,brightness=mid,palette=#5F6A7A",
                        "caption": "Grand finale!"
                    }
                ],
                "render": {
                    "background_asset": "assets/generated/mock-veo-dance-loop/veo-0001.mp4",
                    "output_basename": "mock-veo-dance-loop"
                }
            }
            return json.dumps(mock_job)

        # Budget check
        est_input_tokens = len(prompt) // 4
        est_output_tokens = 4096
        est_cost = (
            (est_input_tokens / 1_000_000) * COST_GEMINI_PRO_INPUT_1M
            + (est_output_tokens / 1_000_000) * COST_GEMINI_PRO_OUTPUT_1M
        )
        if not self._budget.check_budget(est_cost):
            raise RuntimeError(f"Budget exceeded (estimated cost: ${est_cost:.4f})")

        self._last_path = "vertex"
        endpoint = (
            f"https://{self.location}-aiplatform.googleapis.com/v1/"
            f"projects/{self.project_id}/locations/{self.location}/"
            f"publishers/google/models/{self.model}:generateContent"
        )
        payload = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.0, "maxOutputTokens": 4096},
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            endpoint,
            data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                raw = resp.read().decode("utf-8")
        except urllib.error.HTTPError as ex:
            msg = ex.read().decode("utf-8", errors="ignore")
            safe = redact_text(
                f"Vertex HTTPError: {ex.code} {msg}",
                [self.access_token, self.project_id],
            )
            raise RuntimeError(safe) from ex
        except Exception as ex:
            safe = redact_text(
                f"Vertex request failed: {ex}",
                [self.access_token, self.project_id],
            )
            raise RuntimeError(safe) from ex

        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as ex:
            raise RuntimeError(f"Invalid Vertex JSON response: {ex}") from ex

        import uuid

        self._budget.record_spending(est_cost, f"vertex-text-{uuid.uuid4()}")
        return _extract_text_from_response(payload)

    def debug_snapshot(self) -> Dict[str, Any]:
        return {
            "provider": self.name,
            "model": self.model,
            "path": self._last_path,
            "auth_source": self._auth_source,
            "fallback_reason": self._fallback_reason,
            "generated_asset_path": self._generated_asset_path,
            "raw_text": self._last_raw_text or "",
        }


class VertexVeoProvider(_VertexBaseProvider):
    lane_hint = "ai_video"
    vertex_model_env = "VERTEX_VEO_MODEL"
    vertex_model_default = "gemini-2.5-flash"
    provider_name = "vertex_veo"

    def _try_generate_lane_a_video(self, job: Dict[str, Any], prd: Dict[str, Any]) -> str:
        self._lane_a_error = ""
        if not self.project_id or not self.access_token:
            self._lane_a_error = "vertex auth not configured"
            return ""

        hero_desc = _hero_prompt_descriptor(self._selected_hero)
        base_prompt = _seed_prompt_from_job(job, prd, hero_desc, self._quality_context)
        reference_images = self._build_veo_reference_images(job, prd)
        if reference_images:
            preview = self._last_reference_image_rels[:3]
            print(
                f"INFO planner provider={self.name} veo_reference_images={len(reference_images)} "
                f"reference_preview={preview}"
            )
        requested_duration = int(job.get("video", {}).get("length_seconds", 15))
        target_duration = _normalize_veo_duration(requested_duration)
        if target_duration != requested_duration:
            print(
                "INFO planner provider="
                f"{self.name} lane_a_duration_normalized={requested_duration}->{target_duration}"
            )
        candidate_count = _clamp_int(os.environ.get("VERTEX_VEO_CANDIDATES", "3"), 1, 3, 3)
        min_score = _clamp_float(os.environ.get("VERTEX_VEO_MIN_MOTION_SCORE", "-9999"), -1e9, 1e9, -9999.0)
        allow_low_if_any = os.environ.get("VERTEX_VEO_ALLOW_LOW_SCORE_IF_ANY", "1").strip().lower() in (
            "1",
            "true",
            "yes",
        )

        job_id = str(job.get("job_id", "job-generated")).strip() or "job-generated"
        safe_job_id = _safe_slug(job_id)
        rel_dir = f"assets/generated/{safe_job_id}"
        out_dir = _repo_root_path() / "sandbox" / rel_dir
        out_dir.mkdir(parents=True, exist_ok=True)

        candidates: List[Tuple[float, int, str, bytes]] = []
        last_error = ""
        for idx in range(1, candidate_count + 1):
            prompt_i = _veo_candidate_prompt(base_prompt, idx, candidate_count)
            video_bytes = self._generate_video_bytes(prompt_i, target_duration, reference_images)
            if (not video_bytes) and _looks_like_safety_block(self._lane_a_error):
                safe_prompt_i = _sanitize_prompt_for_safety(prompt_i)
                if safe_prompt_i != prompt_i:
                    print(
                        f"INFO planner provider={self.name} veo_prompt_safety_retry candidate={idx}"
                    )
                    video_bytes = self._generate_video_bytes(
                        safe_prompt_i, target_duration, reference_images
                    )
            if (not video_bytes) and _looks_like_safety_block(self._lane_a_error):
                fallback_prompt = _safe_fallback_motion_prompt()
                print(
                    f"INFO planner provider={self.name} veo_prompt_fallback_retry candidate={idx}"
                )
                video_bytes = self._generate_video_bytes(
                    fallback_prompt, target_duration, reference_images
                )
            if not video_bytes:
                last_error = self._lane_a_error
                continue
            rel_name = f"veo-candidate-{idx:04d}.mp4"
            rel_path = f"{rel_dir}/{rel_name}"
            abs_path = out_dir / rel_name
            abs_path.write_bytes(video_bytes)
            motion_score = _score_video_motion_against_demo(abs_path)
            candidates.append((motion_score, idx, rel_path, video_bytes))

        if not candidates:
            if not self._lane_a_error:
                self._lane_a_error = last_error or "Vertex predict response did not contain decodable video bytes"
            return ""

        # Deterministic selection: prefer clip with closest cadence to demo dance_loop.
        candidates.sort(key=lambda x: (-x[0], x[1]))
        best_score, best_idx, best_rel, best_bytes = candidates[0]
        score_list = ", ".join([f"{i}:{s:.3f}" for (s, i, _r, _b) in candidates])
        print(
            f"INFO planner provider={self.name} veo_candidates={len(candidates)}/{candidate_count} "
            f"selected={best_idx} motion_score={best_score:.3f} all_scores=[{score_list}]"
        )
        if best_score < min_score:
            if allow_low_if_any:
                print(
                    f"WARNING planner provider={self.name} low_motion_score={best_score:.3f} "
                    f"threshold={min_score:.3f} allow_low_score_if_any=true using_best_available"
                )
            else:
                self._lane_a_error = (
                    f"best candidate motion_score {best_score:.3f} below threshold {min_score:.3f}"
                )
                return ""

        out_path = out_dir / "veo-0001.mp4"
        out_path.write_bytes(best_bytes)
        return f"{rel_dir}/veo-0001.mp4"

    def _generate_video_bytes(
        self,
        prompt: str,
        duration_seconds: int,
        reference_images: Optional[List[Dict[str, Any]]] = None,
    ) -> bytes:
        model = os.environ.get("VERTEX_VEO_GEN_MODEL", "veo-3.1-generate-preview")
        normalized_duration = _normalize_veo_duration(duration_seconds)
        if normalized_duration != duration_seconds:
            print(
                "INFO planner provider="
                f"{self.name} veo_duration_normalized={duration_seconds}->{normalized_duration}"
            )

        est_cost = normalized_duration * COST_VERTEX_VEO_VIDEO_SEC
        if os.environ.get("CAF_VEO_MOCK", "").strip().lower() in ("1", "true", "yes"):
            print(f"INFO planner provider={self.name} CAF_VEO_MOCK=1; bypassing priced generation and budget tracking.")
            # Return real video bytes to satisfy analysis logic
            source_demo = _repo_root_path() / "sandbox/assets/demo/dance_loop.mp4"
            if source_demo.exists():
                return source_demo.read_bytes()
            return b"VEO_MOCK_VIDEO_BYTES"

        if not self._budget.check_budget(est_cost):
            self._lane_a_error = f"budget exceeded for veo video (cost={est_cost:.4f})"
            return b""

        endpoint = (
            f"https://{self.location}-aiplatform.googleapis.com/v1/"
            f"projects/{self.project_id}/locations/{self.location}/"
            f"publishers/google/models/{model}:predictLongRunning"
        )
        instance: Dict[str, Any] = {"prompt": prompt}
        if reference_images:
            instance["referenceImages"] = reference_images
        payload = {
            "instances": [instance],
            "parameters": {
                "sampleCount": 1,
                "aspectRatio": "9:16",
                "durationSeconds": normalized_duration,
            },
        }
        req = urllib.request.Request(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                raw = resp.read().decode("utf-8")
            operation = json.loads(raw)
        except urllib.error.HTTPError as ex:
            msg = ex.read().decode("utf-8", errors="ignore")
            self._lane_a_error = f"HTTP {ex.code}: {msg[:240]}"
            print(
                f"WARNING planner provider={self.name} veo_video_failed=http_{ex.code}"
            )
            return b""
        except Exception as ex:
            self._lane_a_error = f"{type(ex).__name__}: {ex}"
            print(
                f"WARNING planner provider={self.name} veo_video_failed={type(ex).__name__}"
            )
            return b""

        op_name = operation.get("name") if isinstance(operation, dict) else None
        if not isinstance(op_name, str) or not op_name:
            self._lane_a_error = "predictLongRunning response missing operation name"
            return b""

        endpoint_name = (
            f"projects/{self.project_id}/locations/{self.location}/"
            f"publishers/google/models/{model}"
        )
        data = self._poll_operation(op_name, endpoint_name)
        if not isinstance(data, dict):
            if not self._lane_a_error:
                self._lane_a_error = "operation polling returned no payload"
            return b""
        if not data:
            if not self._lane_a_error:
                self._lane_a_error = "operation polling returned empty payload"
            return b""

        import uuid

        b64 = _extract_first_base64_blob(data)
        if b64:
            try:
                res = base64.b64decode(b64)
                self._budget.record_spending(est_cost, f"vertex-veo-{uuid.uuid4()}")
                return res
            except Exception as ex:
                self._lane_a_error = f"base64 decode failed: {type(ex).__name__}"
                return b""

        media_uri = _extract_first_media_uri(data)
        if media_uri:
            content = self._download_media_uri(media_uri)
            if content:
                self._budget.record_spending(est_cost, f"vertex-veo-{uuid.uuid4()}")
                return content
            if not self._lane_a_error:
                self._lane_a_error = f"media uri download failed: {media_uri[:160]}"
            return b""

        if not self._lane_a_error:
            top_keys = ",".join(sorted(data.keys())[:12]) if isinstance(data, dict) else "non-dict"
            self._lane_a_error = (
                "predict response missing bytes and media uri "
                f"(top-level keys: {top_keys})"
            )
        return b""

    def _poll_operation(self, op_name: str, endpoint_name: str) -> Dict[str, Any]:
        timeout_s = int(os.environ.get("VERTEX_VEO_LRO_TIMEOUT_SECONDS", "420"))
        interval_s = int(os.environ.get("VERTEX_VEO_LRO_POLL_SECONDS", "5"))
        deadline = time.time() + max(30, timeout_s)
        op_urls = _build_operation_urls(op_name, self.location)
        fetch_url = (
            f"https://aiplatform.googleapis.com/v1/"
            f"{endpoint_name}:fetchPredictOperation"
        )

        while time.time() < deadline:
            # Preferred path for predictLongRunning operations.
            try:
                fetch_req = urllib.request.Request(
                    fetch_url,
                    data=json.dumps({"operationName": op_name}).encode("utf-8"),
                    headers={
                        "Authorization": f"Bearer {self.access_token}",
                        "Content-Type": "application/json",
                    },
                )
                with urllib.request.urlopen(fetch_req, timeout=60) as resp:
                    fetch_raw = resp.read().decode("utf-8")
                op = json.loads(fetch_raw)
            except urllib.error.HTTPError:
                # Fall back to generic operations.get URL forms below.
                op = None
            except Exception as ex:
                self._lane_a_error = f"LRO fetchPredictOperation failed: {type(ex).__name__}: {ex}"
                return {}

            if op is None:
                # Fallback path: try operations.get URL variants.
                last_http_err = ""
                for op_url in op_urls:
                    req = urllib.request.Request(
                        op_url,
                        headers={
                            "Authorization": f"Bearer {self.access_token}",
                        },
                    )
                    try:
                        with urllib.request.urlopen(req, timeout=60) as resp:
                            raw = resp.read().decode("utf-8")
                        op = json.loads(raw)
                        break
                    except urllib.error.HTTPError as ex:
                        msg = ex.read().decode("utf-8", errors="ignore")
                        last_http_err = f"{op_url} -> HTTP {ex.code}: {msg[:180]}"
                        continue
                    except Exception as ex:
                        self._lane_a_error = f"LRO poll failed: {type(ex).__name__}: {ex}"
                        return {}

                if op is None:
                    if last_http_err:
                        self._lane_a_error = f"LRO polling failed across URLs: {last_http_err}"
                    else:
                        self._lane_a_error = "LRO polling failed: no operation response"
                    return {}

            if not isinstance(op, dict):
                self._lane_a_error = "LRO response was not a JSON object"
                return {}

            if op.get("done") is True:
                op_error = op.get("error")
                if isinstance(op_error, dict):
                    code = op_error.get("code", "unknown")
                    msg = op_error.get("message", "operation failed")
                    self._lane_a_error = f"LRO error {code}: {msg}"
                    return {}
                response = op.get("response")
                # Veo may return media references in operation metadata while
                # response can be an empty object.
                if isinstance(response, dict) and response:
                    return response
                # Some APIs return predictions directly at top-level on done.
                return op

            time.sleep(max(1, interval_s))

        self._lane_a_error = f"LRO timeout after {timeout_s}s"
        return {}

    def _build_veo_reference_images(self, job: Dict[str, Any], prd: Dict[str, Any]) -> List[Dict[str, Any]]:
        if os.environ.get("VERTEX_VEO_DISABLE_REFERENCES", "").strip().lower() in ("1", "true", "yes"):
            return []

        refs: List[pathlib.Path] = []
        self._last_reference_image_rels = []

        # PR-34.8a: storyboard-first I2V defaults.
        storyboard_ctx = self._quality_context.get("storyboard_i2v", {}) if isinstance(self._quality_context, dict) else {}
        if isinstance(storyboard_ctx, dict):
            seed_assets = storyboard_ctx.get("seed_frame_assets", [])
            if isinstance(seed_assets, list):
                for rel in seed_assets:
                    if not isinstance(rel, str) or not rel.strip():
                        continue
                    p = _repo_root_path() / "sandbox" / rel.strip()
                    if p.exists():
                        refs.append(p)

        # Honor explicit planner seed-frame contracts if present.
        image_motion = job.get("image_motion", {})
        if isinstance(image_motion, dict):
            for rel in image_motion.get("seed_frames", []):
                if not isinstance(rel, str) or not rel.strip():
                    continue
                p = _repo_root_path() / "sandbox" / rel.strip()
                if p.exists():
                    refs.append(p)

        if self._selected_hero:
            for rel in _hero_seed_frames(self._selected_hero):
                p = _repo_root_path() / "sandbox" / rel
                if p.exists():
                    refs.append(p)

        context = _job_context_text(job, prd)
        if "mochi" in context:
            for rel in (
                "assets/demo/mochi_front.png",
                "assets/demo/mochi_profile.png",
                "assets/demo/mochi_jump.png",
            ):
                p = _repo_root_path() / "sandbox" / rel
                if p.exists():
                    refs.append(p)
        if _is_dance_context(context):
            for rel in (
                "assets/demo/dance_loop_snapshot.png",
                "assets/demo/dance_loop_ref_01.png",
                "assets/demo/dance_loop_ref_02.png",
                "assets/demo/dance_loop_ref_03.png",
            ):
                p = _repo_root_path() / "sandbox" / rel
                if p.exists():
                    refs.append(p)

        # Deduplicate and cap.
        uniq: List[pathlib.Path] = []
        seen = set()
        for p in refs:
            k = str(p.resolve())
            if k in seen:
                continue
            seen.add(k)
            uniq.append(p)
        max_refs = _clamp_int(os.environ.get("VERTEX_VEO_REFERENCE_IMAGES", "3"), 0, 3, 3)
        if max_refs <= 0:
            return []
        uniq = uniq[:max_refs]

        out: List[Dict[str, Any]] = []
        for p in uniq:
            mime = _mime_type_for_image(p)
            if not mime:
                continue
            try:
                b64 = base64.b64encode(p.read_bytes()).decode("ascii")
            except Exception:
                continue
            try:
                rel = str(p.resolve().relative_to((_repo_root_path() / "sandbox").resolve())).replace("\\", "/")
                self._last_reference_image_rels.append(rel)
            except Exception:
                pass
            out.append(
                {
                    "image": {
                        "bytesBase64Encoded": b64,
                        "mimeType": mime,
                    },
                    "referenceType": "asset",
                }
            )
        return out

    def _download_media_uri(self, uri: str) -> bytes:
        if uri.startswith("gs://"):
            bucket, obj = _parse_gs_uri(uri)
            if not bucket or not obj:
                self._lane_a_error = f"invalid gs uri: {uri}"
                return b""
            object_q = urllib.parse.quote(obj, safe="")
            # Authenticated media download from GCS JSON API.
            url = f"https://storage.googleapis.com/storage/v1/b/{bucket}/o/{object_q}?alt=media"
            req = urllib.request.Request(
                url,
                headers={"Authorization": f"Bearer {self.access_token}"},
            )
        else:
            req = urllib.request.Request(
                uri,
                headers={"Authorization": f"Bearer {self.access_token}"},
            )
        try:
            with urllib.request.urlopen(req, timeout=240) as resp:
                return resp.read()
        except urllib.error.HTTPError as ex:
            msg = ex.read().decode("utf-8", errors="ignore")
            self._lane_a_error = f"media download HTTP {ex.code}: {msg[:240]}"
            return b""
        except Exception as ex:
            self._lane_a_error = f"media download failed: {type(ex).__name__}: {ex}"
            return b""


class VertexImagenProvider(_VertexBaseProvider):
    lane_hint = "image_motion"
    vertex_model_env = "VERTEX_IMAGEN_MODEL"
    vertex_model_default = "gemini-2.5-flash"
    provider_name = "vertex_imagen"


def _extract_text_from_response(data: Dict[str, Any]) -> str:
    candidates = data.get("candidates")
    if not candidates:
        raise RuntimeError("No candidates in Vertex response")
    content = candidates[0].get("content") if isinstance(candidates[0], dict) else None
    if not content:
        raise RuntimeError("No content in Vertex response")
    parts = content.get("parts")
    if not parts:
        raise RuntimeError("No parts in Vertex response")
    text = parts[0].get("text") if isinstance(parts[0], dict) else None
    if not text:
        raise RuntimeError("No text in Vertex response")
    return text


def _extract_first_base64_blob(node: Any) -> str:
    """Recursively search for a plausible base64 payload key in Vertex responses."""
    if isinstance(node, dict):
        for key in ("bytesBase64Encoded", "videoBytesBase64", "imageBytesBase64"):
            val = node.get(key)
            if isinstance(val, str) and val:
                return val
        for val in node.values():
            found = _extract_first_base64_blob(val)
            if found:
                return found
    elif isinstance(node, list):
        for item in node:
            found = _extract_first_base64_blob(item)
            if found:
                return found
    return ""


def _extract_first_media_uri(node: Any) -> str:
    if isinstance(node, dict):
        for key in ("gcsUri", "videoUri", "outputUri", "uri", "fileUri"):
            val = node.get(key)
            if isinstance(val, str) and val.strip():
                v = val.strip()
                if v.startswith("gs://") or v.startswith("https://") or v.startswith("http://"):
                    return v
        for val in node.values():
            found = _extract_first_media_uri(val)
            if found:
                return found
    elif isinstance(node, list):
        for item in node:
            found = _extract_first_media_uri(item)
            if found:
                return found
    return ""


def _parse_gs_uri(uri: str) -> Tuple[str, str]:
    # gs://bucket/path/to/object
    if not uri.startswith("gs://"):
        return "", ""
    rem = uri[len("gs://") :]
    if "/" not in rem:
        return rem, ""
    bucket, obj = rem.split("/", 1)
    return bucket, obj


def _mime_type_for_image(path: pathlib.Path) -> str:
    ext = path.suffix.lower()
    if ext == ".png":
        return "image/png"
    if ext in (".jpg", ".jpeg"):
        return "image/jpeg"
    if ext == ".webp":
        return "image/webp"
    return ""


def _build_operation_urls(op_name: str, location: str) -> List[str]:
    name = op_name.strip()
    if not name:
        return []

    # If API returns a fully-qualified operation URL, keep both URL and path forms.
    raw_path = name
    urls: List[str] = []
    if name.startswith("https://") or name.startswith("http://"):
        urls.append(name)
        try:
            parsed = urllib.parse.urlparse(name)
            raw_path = parsed.path
        except Exception:
            raw_path = name

    # Normalize to an API path with /v1 prefix.
    if raw_path.startswith("/v1/"):
        base_path = raw_path
    elif raw_path.startswith("/"):
        base_path = f"/v1{raw_path}"
    else:
        base_path = f"/v1/{raw_path}"

    candidate_paths = [base_path]

    # Veo LRO names may include the model scope:
    # /v1/projects/.../locations/.../publishers/google/models/.../operations/<id>
    # Polling often works on canonical:
    # /v1/projects/.../locations/.../operations/<id>
    p = base_path
    marker = "/operations/"
    if marker in p and "/publishers/" in p and "/locations/" in p:
        op_id = p.rsplit(marker, 1)[1]
        loc_prefix = p.split("/publishers/", 1)[0]
        canonical = f"{loc_prefix}{marker}{op_id}"
        candidate_paths.append(canonical)

    for path in candidate_paths:
        urls.append(f"https://{location}-aiplatform.googleapis.com{path}")
        urls.append(f"https://aiplatform.googleapis.com{path}")

    # Deduplicate while preserving order.
    deduped: List[str] = []
    seen = set()
    for u in urls:
        if u in seen:
            continue
        seen.add(u)
        deduped.append(u)
    return deduped


def _normalize_veo_duration(requested: int) -> int:
    # Veo text_to_video currently supports discrete durations only.
    supported = (4, 6, 8, 12)
    # Prefer the closest duration; tie-break upward so 5 -> 6.
    return min(supported, key=lambda d: (abs(d - requested), -d))


def _veo_candidate_prompt(base_prompt: str, idx: int, total: int) -> str:
    variants = [
        "single locked camera, full-body framing, continuous dancing from first frame, no idle standing, clear beat accents every half-second.",
        "exact 8-count loop choreography: 1 side-step left, 2 side-step right, 3 paw-pop, 4 hip sway, 5 side-step left, 6 side-step right, 7 quick turn, 8 return to opening pose.",
        "playful comedic dance loop style, energetic paw swings and bouncy footwork, consistent tempo and body rhythm, keep character identity and costume perfectly stable.",
    ]
    cue = variants[(idx - 1) % len(variants)]
    return f"{base_prompt} | candidate {idx}/{total} | {cue}"


def _clamp_int(raw: str, lo: int, hi: int, default: int) -> int:
    try:
        val = int(str(raw).strip())
    except Exception:
        return default
    return max(lo, min(hi, val))


def _clamp_float(raw: str, lo: float, hi: float, default: float) -> float:
    try:
        val = float(str(raw).strip())
    except Exception:
        return default
    return max(lo, min(hi, val))


def _repo_root_path() -> pathlib.Path:
    here = pathlib.Path(__file__).resolve()
    # repo/services/planner/providers/vertex_ai.py -> <repo_root>
    return here.parents[4]


def _safe_slug(text: str) -> str:
    out: List[str] = []
    for ch in text.lower():
        if ch.isalnum() or ch in "-_":
            out.append(ch)
        else:
            out.append("-")
    slug = "".join(out).strip("-")
    return slug or "job-generated"


def _select_target_hero(
    hero_registry: Optional[Dict[str, Any]],
    prd: Dict[str, Any],
    inbox: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    if not isinstance(hero_registry, dict):
        return None
    heroes = hero_registry.get("heroes")
    if not isinstance(heroes, list):
        return None

    text_parts: List[str] = []
    prompt = prd.get("prompt") if isinstance(prd, dict) else None
    if isinstance(prompt, str):
        text_parts.append(prompt.lower())
    for item in inbox:
        if isinstance(item, dict):
            text_parts.append(json.dumps(item, ensure_ascii=True).lower())
    corpus = " ".join(text_parts)

    # Explicit hero mention by id or english name.
    for hero in heroes:
        if not isinstance(hero, dict):
            continue
        hid = str(hero.get("hero_id", "")).lower()
        name_obj = hero.get("name")
        name_en = ""
        if isinstance(name_obj, dict):
            name_en = str(name_obj.get("en", "")).lower()
        if hid and hid in corpus:
            return hero
        if name_en and name_en in corpus:
            return hero

    # Default to Mochi when present.
    for hero in heroes:
        if isinstance(hero, dict) and str(hero.get("hero_id", "")).lower() == "mochi-grey-tabby":
            return hero
    return None


def _hero_prompt_descriptor(hero: Optional[Dict[str, Any]]) -> str:
    if not isinstance(hero, dict):
        return ""
    name_en = ""
    name_obj = hero.get("name")
    if isinstance(name_obj, dict):
        name_en = str(name_obj.get("en", "")).strip()
    traits = hero.get("traits")
    trait_bits: List[str] = []
    if isinstance(traits, dict):
        for key in ("coat_type", "primary_color", "secondary_color", "pattern", "eye_color", "distinguishing_marks"):
            val = traits.get(key)
            if isinstance(val, str) and val.strip():
                trait_bits.append(f"{key.replace('_', ' ')}: {val.strip()}")
    costume = hero.get("costume")
    costume_notes = ""
    if isinstance(costume, dict):
        c = costume.get("notes")
        if isinstance(c, str):
            costume_notes = c.strip()
    parts = [p for p in [name_en, "; ".join(trait_bits), costume_notes] if p]
    if not parts:
        return ""
    return "hero consistency reference: " + " | ".join(parts)


def _hero_seed_frames(hero: Dict[str, Any]) -> List[str]:
    out: List[str] = []
    hints = hero.get("asset_hints")
    if isinstance(hints, dict):
        seeds = hints.get("seed_frames")
        if isinstance(seeds, list):
            for s in seeds:
                if isinstance(s, str) and s.startswith("assets/"):
                    full = _repo_root_path() / "sandbox" / s
                    if full.exists():
                        out.append(s)
    return out


def _persist_hero_bundle(hero: Dict[str, Any]) -> None:
    hero_id = str(hero.get("hero_id", "")).strip()
    if not hero_id:
        return
    safe_hero_id = _safe_slug(hero_id)
    root = _repo_root_path()
    out_dir = root / "sandbox" / "assets" / "generated" / "heroes" / safe_hero_id
    out_dir.mkdir(parents=True, exist_ok=True)
    profile_path = out_dir / "hero_profile.json"
    profile_path.write_text(json.dumps(hero, indent=2, sort_keys=True), encoding="utf-8")

    seeds = _hero_seed_frames(hero)
    if seeds:
        src = root / "sandbox" / seeds[0]
        if src.exists():
            dst = out_dir / "reference_seed.png"
            try:
                shutil.copy2(src, dst)
            except Exception:
                pass


def _merge_unique_seeds(primary: List[str], secondary: List[str], max_items: int) -> List[str]:
    out: List[str] = []
    for s in primary + secondary:
        if not isinstance(s, str) or not s.startswith("assets/"):
            continue
        if s in out:
            continue
        full = _repo_root_path() / "sandbox" / s
        if not full.exists():
            continue
        out.append(s)
        if len(out) >= max_items:
            break
    return out


def _seed_prompt_from_job(
    job: Dict[str, Any],
    prd: Dict[str, Any],
    hero_desc: str = "",
    quality_context: Optional[Dict[str, Any]] = None,
) -> str:
    script = job.get("script")
    hook = ""
    voiceover = ""
    if isinstance(script, dict):
        hook = str(script.get("hook", "")).strip()
        voiceover = str(script.get("voiceover", "")).strip()
    niche = str(job.get("niche", "")).strip()
    user_prompt = ""
    if isinstance(prd, dict):
        user_prompt = str(prd.get("prompt", "")).strip()

    # Extract style tokens from quality_context
    style_tokens = []
    motion_tokens = []
    if isinstance(quality_context, dict):
         reverse_prompt_data = quality_context.get("reverse_prompt")
         if isinstance(reverse_prompt_data, dict):
             suggestions = reverse_prompt_data.get("suggestions", {})
             style_tokens = suggestions.get("vendor_style_tokens", [])
         
         # Motion Translation
         motion_tokens = _translate_motion_metadata(quality_context)

    parts = [p for p in [user_prompt, niche, hook, voiceover, hero_desc] if p]
    if style_tokens:
        parts.extend(style_tokens)
    if motion_tokens:
        parts.extend(motion_tokens)

    prompt = " | ".join(parts)
    context = prompt.lower()
    consistency_hints: List[str] = []
    if "mochi" in context:
        consistency_hints.append("Mochi grey tabby cat")
    if "costume" in context:
        consistency_hints.append("same costume in every frame")
    if _is_dance_context(context):
        consistency_hints.append("same character identity and outfit across all generated frames")
        consistency_hints.append("consistent camera style and lighting")
        consistency_hints.append("dance choreography synchronized to a steady upbeat beat")
        consistency_hints.append("clear full-body motion, avoid static posing")
        consistency_hints.extend(_dance_loop_directives(context))
    style_hints = _style_profile_hints(context)
    costume_hints = _costume_profile_hints(context)
    consistency_hints.extend(style_hints)
    consistency_hints.extend(costume_hints)
    if consistency_hints:
        deduped = _dedupe_preserve_order(consistency_hints)
        prompt = f"{prompt} | " + " | ".join(deduped)

    if not prompt:
        prompt = "A vertical cinematic scene for a short-form cat video."

    # Ensure baseline quality for any generated seed frame.
    prompt = f"{prompt} | 8k resolution, cinematic lighting, high fidelity, sharp focus, professional photography"

    return prompt[:1200]


def _job_context_text(job: Dict[str, Any], prd: Dict[str, Any]) -> str:
    parts: List[str] = []
    if isinstance(prd, dict):
        p = prd.get("prompt")
        if isinstance(p, str):
            parts.append(p)
    niche = job.get("niche")
    if isinstance(niche, str):
        parts.append(niche)
    script = job.get("script")
    if isinstance(script, dict):
        for key in ("hook", "voiceover", "ending"):
            val = script.get(key)
            if isinstance(val, str):
                parts.append(val)
    hashtags = job.get("hashtags")
    if isinstance(hashtags, list):
        parts.extend([h for h in hashtags if isinstance(h, str)])
    return " ".join(parts).lower()


def _job_uses_demo_background(job: Dict[str, Any]) -> bool:
    render = job.get("render")
    if not isinstance(render, dict):
        return False
    bg = render.get("background_asset")
    if not isinstance(bg, str):
        return False
    s = bg.strip().lower()
    return s.startswith("assets/demo/") or s.startswith("sandbox/assets/demo/")


def _allow_demo_background_fallback() -> bool:
    return os.environ.get("CAF_ALLOW_DEMO_BACKGROUND_FALLBACK", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )


def _dance_loop_directives(context: str) -> List[str]:
    hints: List[str] = [
        "single subject only, full body visible from head to paws for entire clip",
        "locked camera, no zooms, no cuts, no scene changes",
        "dance continuously in place with visible beat accents every 0.5 seconds",
        "target tempo around 120 bpm with readable movement on each beat",
        "use repeating 8-count choreography and close the loop exactly on count 8",
        "loop-safe choreography: ending pose, facing, and paw position should align with opening pose",
    ]
    if "bee" in context:
        hints.append("bee kigurumi onesie: yellow-black stripes, soft plush texture, small antennae")
    if "dino" in context or "dinosaur" in context:
        hints.append("full-length one-piece green dinosaur kigurumi onesie with sleeves and full leg coverage")
        hints.append("lighter green belly panel, hood spikes, cartoon dino snout details")
        hints.append("avoid two-piece clothing; keep costume as a single plush pajama suit")
    if "mochi" in context:
        hints.append("preserve Mochi grey-tabby face markings and body pattern consistently in every frame")
    if "cats" in context or "group" in context:
        hints.append("Mochi dancing together with a group of 4 other costumed cats (tiger, bear, bee, butterfly) as seen in the demo")
    if "dance loop demo style" in context or "demo dance loop style" in context:
        hints.append("cozy living-room dance-party feel with playful social-video energy, matching the demo background")
    return hints


def _is_dance_context(text: str) -> bool:
    keywords = ("dance", "dancing", "groove", "party", "loop", "choreo")
    return any(k in text for k in keywords)


def _is_kitten_context(text: str) -> bool:
    keywords = ("kitten", "kitty", "baby cat", "mochi kitten")
    return any(k in text for k in keywords)


def _choose_motion_preset(job: Dict[str, Any], prd: Dict[str, Any], seed_count: int) -> str:
    text = _job_context_text(job, prd)
    if seed_count >= 2 and _is_dance_context(text):
        return "cut_3frame"
    if _is_dance_context(text):
        return "shake_soft"
    return "kb_zoom_in"


def _pick_default_audio_asset(context_text: str) -> str:
    root = _repo_root_path()
    manifest_path = root / "sandbox" / "assets" / "audio" / "audio_manifest.v1.json"
    dance_mode = _is_dance_context(context_text)

    # 1) Manifest-first: deterministic best score, tie-broken by id.
    if manifest_path.exists():
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
            beds = data.get("beds")
            if isinstance(beds, list):
                normalized = []
                for bed in beds:
                    if not isinstance(bed, dict):
                        continue
                    bed_id = bed.get("id")
                    rel = bed.get("relpath")
                    if not isinstance(bed_id, str) or not isinstance(rel, str):
                        continue
                    if not rel.startswith("assets/audio/"):
                        continue
                    full = root / "sandbox" / rel
                    if not full.exists():
                        continue
                    score = _audio_score_from_manifest_bed(bed, dance_mode)
                    normalized.append((score, bed_id, rel))
                if normalized:
                    normalized.sort(key=lambda x: (-x[0], x[1]))
                    return normalized[0][2]
        except Exception:
            pass

    # 2) Safe local fallback: best filename score, tie-broken lexicographically.
    beds_dir = root / "sandbox" / "assets" / "audio" / "beds"
    if not beds_dir.exists():
        return ""
    candidates: List[Tuple[int, pathlib.Path]] = []
    for p in sorted(beds_dir.iterdir()):
        if not p.is_file():
            continue
        if p.suffix.lower() not in (".wav", ".mp3", ".m4a", ".aac"):
            continue
        score = _audio_score_from_filename(p.name.lower(), dance_mode)
        candidates.append((score, p))
    if not candidates:
        return ""
    candidates.sort(key=lambda x: (-x[0], str(x[1].name)))
    rel = candidates[0][1].relative_to(root / "sandbox")
    return str(rel).replace("\\", "/")


def _audio_score_from_manifest_bed(bed: Dict[str, Any], dance_mode: bool) -> int:
    score = 0
    bed_id = str(bed.get("id", "")).lower()
    rel = str(bed.get("relpath", "")).lower()
    tags = bed.get("mood_tags")
    tags_l = []
    if isinstance(tags, list):
        tags_l = [str(t).lower() for t in tags]

    if dance_mode:
        good = ("upbeat", "dance", "party", "funny", "comedy", "energetic")
        bad = ("ambient", "rumble", "sad", "dark")
        for g in good:
            if g in bed_id or g in rel or g in tags_l:
                score += 3
        for b in bad:
            if b in bed_id or b in rel or b in tags_l:
                score -= 3
    return score


def _audio_score_from_filename(name: str, dance_mode: bool) -> int:
    if not dance_mode:
        return 0
    score = 0
    if "dance_loop" in name or "dance-loop" in name:
        score += 8
    if "upbeat" in name or "party" in name:
        score += 4
    if "lofi" in name:
        score += 1
    if "ambient" in name or "rumble" in name:
        score -= 4
    return score


def _style_profile_hints(context: str) -> List[str]:
    data = _load_style_profiles()
    if not data:
        return []
    profiles = data.get("profiles")
    if not isinstance(profiles, list):
        return []

    hints: List[str] = []
    matched_costume_ids: List[str] = []
    for profile in profiles:
        if not isinstance(profile, dict):
            continue
        aliases = profile.get("aliases")
        if not isinstance(aliases, list):
            continue
        matched = False
        for a in aliases:
            if isinstance(a, str) and a.strip().lower() in context:
                matched = True
                break
        if not matched:
            continue

        positive = profile.get("positive_cues")
        if isinstance(positive, list):
            for cue in positive:
                if isinstance(cue, str) and cue.strip():
                    hints.append(cue.strip())
        negative = profile.get("negative_cues")
        if isinstance(negative, list):
            for cue in negative:
                if isinstance(cue, str) and cue.strip():
                    hints.append(cue.strip())
        ids = profile.get("costume_profile_ids")
        if isinstance(ids, list):
            for cid in ids:
                if isinstance(cid, str) and cid.strip():
                    matched_costume_ids.append(cid.strip())
    if matched_costume_ids:
        hints.extend(_costume_hints_from_ids(matched_costume_ids))
    return hints


def _load_style_profiles() -> Dict[str, Any]:
    root = _repo_root_path()
    path = root / "repo" / "shared" / "style_profiles.v1.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    return data


def _costume_profile_hints(context: str) -> List[str]:
    data = _load_costume_profiles()
    if not data:
        return []
    profiles = data.get("profiles")
    if not isinstance(profiles, list):
        return []

    hints: List[str] = []
    for profile in profiles:
        if not isinstance(profile, dict):
            continue
        aliases = profile.get("aliases")
        if not isinstance(aliases, list):
            continue
        matched = False
        for a in aliases:
            if isinstance(a, str) and a.strip().lower() in context:
                matched = True
                break
        if not matched:
            continue
        cues = profile.get("cues")
        if isinstance(cues, list):
            for cue in cues:
                if isinstance(cue, str) and cue.strip():
                    hints.append(cue.strip())
    return hints



def _translate_motion_metadata(quality_context: Optional[Dict[str, Any]]) -> List[str]:
    """Translates analysis metadata into Veo3 motion prompts."""
    if not isinstance(quality_context, dict):
        return []
    
    prompts = []
    
    # 1. Video Analysis Parsing (pattern.choreography, pattern.camera)
    # Assumes quality_context may contain a 'video_analysis' key with the v1 schema
    video_analysis = quality_context.get("video_analysis", {})
    if video_analysis:
        pattern = video_analysis.get("pattern", {})
        
        # Energy Curve
        energy = pattern.get("choreography", {}).get("energy_curve")
        if energy == "build":
            prompts.append("building energy, intensifying motion")
        elif energy == "drop":
            prompts.append("sudden drop in energy, dramatic pause")
        elif energy == "sustain":
            prompts.append("consistent high energy, sustained motion")
            
        # Camera Pattern
        shot_patterns = pattern.get("camera", {}).get("shot_pattern", [])
        if "static" in shot_patterns or "locked" in shot_patterns:
            prompts.append("static camera, fixed angle, no shake")
        if "tracking" in shot_patterns:
            prompts.append("dynamic tracking shot, following character")
        if "zoom" in shot_patterns:
            prompts.append("camera zoom")

    # 2. Reverse Prompt Parsing (truth.visual_facts)
    # Assumes quality_context may contain a 'reverse_prompt' key with the v1 schema
    reverse_prompt = quality_context.get("reverse_prompt", {})
    if reverse_prompt:
        facts = reverse_prompt.get("truth", {}).get("visual_facts", {})
        
        # Camera Mode
        cam_mode = facts.get("camera_movement_mode")
        if cam_mode == "locked":
            # Dedup with above if needed, but adding emphasis is fine
            prompts.append("tripod shot, locked camera")
        elif cam_mode == "handheld":
            prompts.append("handheld camera motion, organic shake")
            
        # Motion Intensity
        # Determine average intensity from shots if available, or top-level fact
        shots = reverse_prompt.get("truth", {}).get("shots", [])
        if shots:
            avg_intensity = sum(s.get("motion_intensity", 0) for s in shots) / len(shots)
            if avg_intensity > 0.7:
                prompts.append("high energy, fast paced, dynamic movement")
            elif avg_intensity < 0.3:
                prompts.append("subtle motion, slow movement, calm")

    return list(set(prompts)) # Simple dedup

def _costume_hints_from_ids(ids: List[str]) -> List[str]:
    data = _load_costume_profiles()
    if not data:
        return []
    profiles = data.get("profiles")
    if not isinstance(profiles, list):
        return []
    wanted = set(i.strip() for i in ids if isinstance(i, str) and i.strip())
    if not wanted:
        return []

    hints: List[str] = []
    for profile in profiles:
        if not isinstance(profile, dict):
            continue
        pid = profile.get("id")
        if not isinstance(pid, str) or pid not in wanted:
            continue
        cues = profile.get("cues")
        if isinstance(cues, list):
            for cue in cues:
                if isinstance(cue, str) and cue.strip():
                    hints.append(cue.strip())
    return hints


def _load_costume_profiles() -> Dict[str, Any]:
    root = _repo_root_path()
    path = root / "repo" / "shared" / "costume_profiles.v1.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    return data


def _dedupe_preserve_order(items: List[str]) -> List[str]:
    out: List[str] = []
    seen = set()
    for item in items:
        key = item.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(item.strip())
    return out


def _score_image_candidate_bytes(image_bytes: bytes, kitten_mode: bool) -> int:
    # Deterministic proxy score:
    # - larger encoded payloads tend to preserve more detail
    # - sampled byte diversity acts as a cheap texture/detail proxy
    size = len(image_bytes)
    if not image_bytes:
        return 0
    step = max(1, len(image_bytes) // 512)
    sample = image_bytes[::step][:512]
    diversity = len(set(sample))
    kitten_bonus = diversity * 50 if kitten_mode else diversity * 10
    return size + kitten_bonus


def _score_video_motion_against_demo(video_path: pathlib.Path) -> float:
    demo = _repo_root_path() / "sandbox" / "assets" / "demo" / "dance_loop.mp4"
    cand_seq = _extract_motion_sequence(video_path)
    if not cand_seq:
        return -1e9
    ref_seq = _extract_motion_sequence(demo)
    if not ref_seq:
        # Fallback if demo unavailable: prefer high, varied motion.
        return _sequence_energy_score(cand_seq)
    return _cadence_similarity_score(cand_seq, ref_seq)


def _extract_motion_sequence(video_path: pathlib.Path) -> List[float]:
    if not video_path.exists():
        return []
    # Deterministic low-res grayscale frame stream.
    cmd = [
        "ffmpeg",
        "-v",
        "error",
        "-i",
        str(video_path),
        "-vf",
        "fps=6,scale=64:64,format=gray",
        "-f",
        "rawvideo",
        "-",
    ]
    try:
        raw = subprocess.check_output(cmd)
    except Exception:
        return []
    frame_size = 64 * 64
    if len(raw) < frame_size * 2:
        return []

    frame_count = len(raw) // frame_size
    diffs: List[float] = []
    prev = raw[0:frame_size]
    for i in range(1, frame_count):
        start = i * frame_size
        cur = raw[start : start + frame_size]
        # Mean absolute pixel delta between consecutive frames.
        total = 0
        for a, b in zip(prev, cur):
            total += abs(a - b)
        diffs.append(total / frame_size)
        prev = cur
    return diffs


def _sequence_energy_score(seq: List[float]) -> float:
    if not seq:
        return -1e9
    mean = statistics.fmean(seq)
    stdev = statistics.pstdev(seq) if len(seq) > 1 else 0.0
    return mean + 0.5 * stdev


def _cadence_similarity_score(seq: List[float], ref: List[float]) -> float:
    # Compare summary stats and beat-like peak cadence.
    seq_mean = statistics.fmean(seq)
    ref_mean = statistics.fmean(ref)
    seq_std = statistics.pstdev(seq) if len(seq) > 1 else 0.0
    ref_std = statistics.pstdev(ref) if len(ref) > 1 else 0.0
    seq_peaks = _normalized_peak_rate(seq)
    ref_peaks = _normalized_peak_rate(ref)
    corr = _normalized_best_lag_correlation(seq, ref)

    w_mean = _env_float("VERTEX_VEO_SCORE_W_MEAN", 0.7)
    w_std = _env_float("VERTEX_VEO_SCORE_W_STD", 0.8)
    w_peaks = _env_float("VERTEX_VEO_SCORE_W_PEAKS", 130.0)
    w_corr = _env_float("VERTEX_VEO_SCORE_W_CORR", 120.0)
    w_energy = _env_float("VERTEX_VEO_SCORE_W_ENERGY", 0.03)

    dist = (
        abs(seq_mean - ref_mean) * w_mean
        + abs(seq_std - ref_std) * w_std
        + abs(seq_peaks - ref_peaks) * w_peaks
        + (1.0 - corr) * w_corr
    )
    # Higher score is better.
    return -dist + _sequence_energy_score(seq) * w_energy


def _normalized_peak_rate(seq: List[float]) -> float:
    if len(seq) < 3:
        return 0.0
    mean = statistics.fmean(seq)
    std = statistics.pstdev(seq) if len(seq) > 1 else 0.0
    thresh = mean + std * 0.35
    peaks = 0
    for i in range(1, len(seq) - 1):
        if seq[i] > thresh and seq[i] >= seq[i - 1] and seq[i] >= seq[i + 1]:
            peaks += 1
    return peaks / max(1, len(seq))


def _normalized_best_lag_correlation(a: List[float], b: List[float]) -> float:
    # Compare rhythm patterns allowing small time shift.
    n = min(len(a), len(b))
    if n < 6:
        return 0.0
    aa = a[:n]
    bb = b[:n]
    aa_n = _z_norm(aa)
    bb_n = _z_norm(bb)
    max_lag = min(8, n // 4)
    best = -1.0
    for lag in range(-max_lag, max_lag + 1):
        if lag >= 0:
            x = aa_n[lag:]
            y = bb_n[: len(x)]
        else:
            x = aa_n[: lag]
            y = bb_n[-lag:]
        if len(x) < 4:
            continue
        c = _dot_corr(x, y)
        if c > best:
            best = c
    return max(0.0, min(1.0, (best + 1.0) / 2.0))


def _z_norm(seq: List[float]) -> List[float]:
    m = statistics.fmean(seq)
    s = statistics.pstdev(seq) if len(seq) > 1 else 0.0
    if s < 1e-6:
        return [0.0 for _ in seq]
    return [(x - m) / s for x in seq]


def _dot_corr(x: List[float], y: List[float]) -> float:
    n = min(len(x), len(y))
    if n == 0:
        return 0.0
    num = 0.0
    for i in range(n):
        num += x[i] * y[i]
    return num / n


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except Exception:
        return default


def _looks_like_safety_block(msg: str) -> bool:
    text = (msg or "").lower()
    return ("sensitive words" in text) or ("responsible ai" in text) or ("support codes" in text)


def _sanitize_prompt_for_safety(prompt: str) -> str:
    # Keep intent while reducing policy-triggering terms.
    replacements = {
        "kitten": "young cat",
        "baby cat": "young cat",
        "sexy": "stylish",
        "hot": "energetic",
    }
    out = prompt
    low = out.lower()
    for k, v in replacements.items():
        if k in low:
            out = re.sub(re.escape(k), v, out, flags=re.IGNORECASE)
            low = out.lower()
    # Trim excessive punctuation that can occasionally trigger filters.
    out = re.sub(r"[!]{2,}", "!", out)
    return out


def _safe_fallback_motion_prompt() -> str:
    return (
        "A family-friendly grey tabby cat doing playful dance steps in a green dinosaur onesie. "
        "Single subject only. Full-body framing. Stable camera. Clean solid cyan studio background. "
        "Continuous rhythmic movement with simple side-steps and paw swings. No text, no extra subjects."
    )
