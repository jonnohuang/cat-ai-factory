from __future__ import annotations

import json
import os
import subprocess
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

from ..util.json_extract import extract_json_object
from ..util.redact import redact_text
from .base import BaseProvider


class GeminiAIStudioProvider(BaseProvider):
    @property
    def name(self) -> str:
        return "ai_studio"

    @property
    def default_model(self) -> str:
        return "gemini-2.5-flash"

    def __init__(
        self, api_key: Optional[str] = None, model: str = "gemini-2.5-flash"
    ) -> None:
        env_name = "GEMINI_" + "API" + "_" + "KEY"
        self.api_key = api_key or os.environ.get(env_name)
        self.model = os.environ.get("GEMINI_MODEL", model)
        self._last_raw_text: Optional[str] = None

    def generate_job(
        self,
        prd: Dict[str, Any],
        inbox: Optional[List[Dict[str, Any]]] = None,
        hero_registry: Optional[Dict[str, Any]] = None,
        quality_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if not self.api_key:
            env_name = "GEMINI_" + "API" + "_" + "KEY"
            raise ValueError(f"{env_name} is required")
        prompt = _build_prompt(prd, inbox or [], hero_registry, quality_context)
        raw = self._generate_content(prompt)
        if _looks_truncated(raw):
            repair_prompt = _build_repair_prompt(prompt, raw)
            repaired = self._generate_content(repair_prompt)
            self._last_raw_text = repaired
            job = extract_json_object(repaired)
            ok, err = _validate_job(job)
            if not ok:
                raise RuntimeError(f"Job failed validation after repair: {err}")
            return job
        self._last_raw_text = raw

        try:
            job = extract_json_object(raw)
        except Exception:
            repair_prompt = _build_repair_prompt(prompt, raw)
            repaired = self._generate_content(repair_prompt)
            self._last_raw_text = repaired
            job = extract_json_object(repaired)
            ok, err = _validate_job(job)
            if not ok:
                raise RuntimeError(f"Job failed validation after repair: {err}")
            return job

        ok, err = _validate_job(job)
        if not ok:
            fix_prompt = _build_schema_fix_prompt(prompt, raw, err)
            fixed = self._generate_content(fix_prompt)
            self._last_raw_text = fixed
            job = extract_json_object(fixed)
            ok2, err2 = _validate_job(job)
            if not ok2:
                 raise RuntimeError(f"Job failed validation after schema fix: {err2}")

        # --- PHASE 2: Narrative Critic (PR-39 Enhancement) ---
        critic_prompt = _build_critic_prompt(prd, job)
        critic_raw = self._generate_content(critic_prompt)
        critic_eval = extract_json_object(critic_raw)

        if critic_eval.get("status") == "FAIL":
            print(f"CRITIC FAIL: {critic_eval.get('reason')}")
            # Re-generate once with critic feedback
            regen_prompt = _build_regen_prompt(prompt, job, critic_eval)
            regen_raw = self._generate_content(regen_prompt)
            job = extract_json_object(regen_raw)
            # final safety check
            ok3, err3 = _validate_job(job)
            if not ok3:
                # Apply schema fix to regen output
                fix_prompt = _build_schema_fix_prompt(regen_prompt, regen_raw, err3)
                fixed = self._generate_content(fix_prompt)
                job = extract_json_object(fixed)
                ok4, err4 = _validate_job(job)
                if not ok4:
                    raise RuntimeError(f"Job failed validation after narrative regen + schema fix: {err4}")

        return job

    def _generate_content(self, prompt: str) -> str:
        base = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:generateContent"
        )
        url = base + "?" + urllib.parse.urlencode({"key": self.api_key})
        payload = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.0, "maxOutputTokens": 8192},
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url, data=data, headers={"Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                raw = resp.read().decode("utf-8")
        except urllib.error.HTTPError as ex:
            msg = ex.read().decode("utf-8", errors="ignore")
            safe = redact_text(f"HTTPError: {ex.code} {msg}", [self.api_key])
            raise RuntimeError(safe) from ex
        except Exception as ex:
            safe = redact_text(f"Request failed: {ex}", [self.api_key])
            raise RuntimeError(safe) from ex

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as ex:
            safe = redact_text(f"Invalid JSON response: {ex}", [self.api_key])
            raise RuntimeError(safe) from ex

        text = _extract_text_from_response(data)
        print(f"DEBUG: gemini raw text length: {len(text)}")
        return text

    def debug_snapshot(self) -> Dict[str, Any]:
        return {
            "provider": "gemini_ai_studio",
            "model": self.model,
            "raw_text": self._last_raw_text or "",
        }


def _repo_root() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.normpath(os.path.join(here, "..", "..", "..", ".."))


def _validate_job(job: Dict[str, Any]) -> Tuple[bool, str]:
    validate_script = os.path.join(_repo_root(), "repo", "tools", "validate_job.py")
    fd, temp_path = tempfile.mkstemp(prefix="planner-validate-", suffix=".job.json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(job, f, indent=2)
            f.write("\n")
        result = subprocess.run(
            ["python3", validate_script, temp_path],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            return True, ""
        msg = result.stderr.strip() or result.stdout.strip() or "Job validation failed"
        return False, msg
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)


def _build_prompt(
    prd: Dict[str, Any],
    inbox: List[Dict[str, Any]],
    hero_registry: Optional[Dict[str, Any]] = None,
    quality_context: Optional[Dict[str, Any]] = None,
) -> str:
    prd_json = json.dumps(prd, indent=None, separators=(",", ":"), ensure_ascii=True)
    inbox_json = json.dumps(
        inbox, indent=None, separators=(",", ":"), ensure_ascii=True
    )

    registry_context = ""
    if hero_registry:
        # PR21: Compact JSON to save tokens
        # Reduced view (ids + names + tags) to save tokens.
        reduced_heroes = []
        for hero in hero_registry.get("heroes", []):
            if not isinstance(hero, dict):
                continue
            reduced_heroes.append(
                {
                    "id": hero.get("hero_id"),
                    "name": hero.get("name"),
                    "tags": hero.get("series_tags"),
                }
            )
        registry_json = json.dumps(
            {"heroes": reduced_heroes},
            indent=None,
            separators=(",", ":"),
            ensure_ascii=True,
        )
        registry_context = (
            f"Hero Registry (Reference Material):\n"
            f"{registry_json}\n"
            "Read-only reference; do not invent new hero characters; pick from the registry list.\n"
            "Do not output the registry content. Do not paste registry JSON into captions.\n\n"
        )

    quality_context_block = ""
    if quality_context:
        quality_json = json.dumps(
            quality_context, indent=None, separators=(",", ":"), ensure_ascii=True
        )
        quality_context_block = (
            "Quality Context (Planner-Only Reference):\n"
            f"{quality_json}\n"
            "Use this only as planning guidance. Keep output strictly within job schema.\n"
            "Do not emit non-schema fields.\n\n"
        )

    template = (
        '{"job_id":"optional-id","date":"YYYY-MM-DD","niche":"...",'
        '"video":{"length_seconds":15,"aspect_ratio":"9:16","fps":30,"resolution":"1080x1920"},'
        '"script":{"hook":"...","voiceover":"...","ending":"..."},'
        '"shots":[{"t":0,"visual":"...","action":"...","caption":"..."}],'
        '"captions":["..."],"hashtags":["#cat","#shorts","#pets"],'
        '"render":{"background_asset":"assets/demo/fight_composite.mp4",'
        '"subtitle_style":"big_bottom","output_basename":"..."}}'
    )
    rules = (
        "Return ONLY a single JSON object. No markdown, no code fences, no commentary.\n"
        "Top-level keys required: job_id, date, niche, video, script, shots, captions, hashtags, render.\n"
        "date must be YYYY-MM-DD.\n"
        "video must be an object: length_seconds (10-60 int), aspect_ratio 9:16, fps 30, resolution 1080x1920.\n"
        "shots must be 6-14 objects with keys: shot_id (string shot_NNNN), t (int), visual (string), action (string), caption (string), hero_id (string, e.g. 'mochi-grey-tabby').\n"
        "captions must be 4-24 strings (1-80 chars).\n"
        "hashtags must be 3-20 strings matching ^#\\w[\\w_]*$ (no hyphens or spaces).\n"
        "render.subtitle_style must be big_bottom or karaoke_bottom.\n"
        "--- NARRATIVE & SPECIES REINFORCEMENT (CRITICAL) ---\n"
        "1. In EVERY shot's 'visual' description, the FIRST WORD must be the hero's name (e.g. 'Mochi') and the word 'cat' MUST appear within the first 5 words.\n"
        "2. FORBIDDEN SUBJECTS: Absolutely NO dogs, NO humans, NO human hands, and NO other animals. Every character in every shot MUST be a cat. This is non-negotiable.\n"
        "3. STORY CONTINUITY: Ensure the background setting (e.g. 'Construction Site') is consistent across all shots. Describe structural beams, cranes, and high-vis vests in every 'visual' field.\n"
        "4. DETAILED PROMPTS: visual descriptions must be highly detailed, cinematic, and specify lighting, texture (fur), and camera angle.\n"
        "--- FELINE STABILIZATION & SPECIES LOCK (PR-PROD-03) ---\n"
        "If generating for a cat/feline subject, you MUST inject dynamic parameter overrides in comfyui.bindings.parameters:\n"
        "- Add 'human', 'human face', 'human hand', 'person', 'woman', 'man', 'dog', 'canine', 'bipedal' to the negative prompt.\n"
        "--- STYLE & CONTINUITY ANCHORS (PR-PROD-02) ---\n"
        "1. Every single 'visual' field MUST end with this exact suffix: \", photorealistic, 8k, cinematic lighting, highly detailed fur, no cartoon, no 2D, no drawing.\"\n"
        "2. VISUAL THEME: The setting 'Construction Site' must be prominent in every shot (cranes, structural beams, dust).\n"
        "3. MOTION PRECISION: Only assign 'background_asset' (assets/demo/fight_composite.mp4) to shots that require intense feline wrestling/fighting. For all other shots, omit background_asset to maintain identity stability.\n"
        "--- STORYBOARD & CONTINUITY (PR-PROD-04) ---\n"
        "1. VISUAL FLOW: Every shot after shot_0001 MUST reference the previous shot's outcome in its 'visual' description (e.g. 'Mochi glares at Ronnie, who is still tangled in the pipes').\n"
        "2. STORYBOARD ALIGNMENT: Strictly follow the 'storyboard_rules' provided in the PRD JSON. Each shot MUST map to a storyboard beat.\n"
    )
    return (
        "You are the Planner for Cat AI Factory.\n"
        f"{rules}\n"
        f"{registry_context}"
        f"{quality_context_block}"
        f"Template (structure only): {template}\n\n"
        f"PRD JSON:\n{prd_json}\n\n"
        f"Inbox JSON list:\n{inbox_json}\n"
    )


def _build_repair_prompt(original_prompt: str, prior_response: str) -> str:
    return (
        "You are a JSON repair tool.\n"
        "Return ONE valid JSON object ONLY.\n"
        "- No markdown\n"
        "- No code fences\n"
        "- No commentary\n"
        "- No trailing commas\n"
        "- Use double quotes for all strings\n"
        '- Escape any embedded double quotes inside strings (\\")\n'
        "- Do NOT change the intended content; only fix JSON validity/escaping\n"
        "- If you mention a hero character in script/captions/shots, pick from the registry list and do not invent new names.\n\n"
        "Previous response to repair:\n"
        f"{prior_response}\n"
    )


def _looks_truncated(raw: str) -> bool:
    s = raw.strip()
    return ("{" in s) and ("}" not in s)


def _build_schema_fix_prompt(
    original_prompt: str, prior_response: str, error_text: str
) -> str:
    return (
        "Your previous response did not pass schema validation.\n"
        "Return ONLY a single JSON object. No markdown, no code fences, no commentary.\n"
        "Fix only to satisfy the schema: types, required fields, min/max items, and patterns.\n"
        "Keep top-level keys exactly as required: job_id, date, niche, video, script, shots, captions, hashtags, render.\n"
        "If you mention a hero character in script/captions/shots, pick from the registry list and do not invent new names.\n\n"
        "Validation error:\n"
        f"{error_text}\n\n"
        "Original prompt (for reference):\n"
        f"{original_prompt}\n\n"
        "Previous response (to fix):\n"
        f"{prior_response}\n"
    )


def _build_critic_prompt(prd: Dict[str, Any], job: Dict[str, Any]) -> str:
    return (
        "You are the NARRATIVE CRITIC for Cat AI Factory.\n"
        "Your role is to audit the DRAFT JOB for viral potential, identity consistency, and species safety.\n\n"
        "### AUDIT CRITERIA:\n"
        "1. SPECIES SAFETY: Are there ANY mentions of humans, human parts, dogs, or other animals? If you see 'man', 'woman', 'hand', or 'person', it is a CRITICAL FAIL.\n"
        "2. IDENTITY CONTINUITY: Does every shot specify the correct hero_id? Are the visual descriptions consistent with the character traits?\n"
        "3. NARRATIVE PINNING: Does the job strictly follow the provided brief (e.g., Construction Site)? Is the setting consistent every shot? Are the visual style descriptions uniform (no mix of 'cinematic' and 'cartoon')?\n"
        "4. MOTION OVER-CONTAMINATION: Are setup shots (standing, surveying) incorrectly assigned a fight-motion background_asset? If so, FAIL.\n"
        "5. VIRAL IMPACT: Is the sequence funny? Does it have a clear 'Hook' and 'Viral Punchline'?\n\n"
        "### DRAFT JOB:\n"
        f"{json.dumps(job, indent=2)}\n\n"
        "### ORIGINAL BRIEF:\n"
        f"{prd.get('brief')}\n\n"
        "Return ONLY a JSON object:\n"
        '{"status": "PASS" | "FAIL", "reason": "...", "suggestions": "..."}'
    )


def _build_regen_prompt(original_prompt: str, job: Dict[str, Any], evaluation: Dict[str, Any]) -> str:
    return (
        f"{original_prompt}\n\n"
        "### CRITIC FEEDBACK (MANDATORY FIX):\n"
        f"Status: {evaluation.get('status')}\n"
        f"Reason: {evaluation.get('reason')}\n"
        f"Suggestions: {evaluation.get('suggestions')}\n\n"
        "Return a NEW and CORRECTED Job JSON that addresses all feedback.\n"
        "### SCHEMA REQUIREMENTS (MANDATORY):\n"
        "- 'render' MUST be an object with background_asset, subtitle_style, and output_basename.\n"
        "- 'captions' MUST be an array of 4-24 strings.\n"
        "- 'shots' MUST be an array of 6-14 objects.\n"
        "Return ONLY the JSON object. No markdown, no commentary."
    )


def _extract_text_from_response(data: Dict[str, Any]) -> str:
    candidates = data.get("candidates")
    if not candidates:
        raise RuntimeError("No candidates in Gemini response")
    content = candidates[0].get("content") if isinstance(candidates[0], dict) else None
    if not content:
        raise RuntimeError("No content in Gemini response")
    parts = content.get("parts")
    if not parts:
        raise RuntimeError("No parts in Gemini response")
    text = parts[0].get("text") if isinstance(parts[0], dict) else None
    if not text:
        raise RuntimeError("No text in Gemini response")
    return text
