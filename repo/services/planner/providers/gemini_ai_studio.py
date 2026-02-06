from __future__ import annotations

import json
import os
import subprocess
import tempfile
import urllib.parse
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

from .base import PlannerProvider
from ..util.json_extract import extract_json_object
from ..util.redact import redact_text


class GeminiAIStudioProvider(PlannerProvider):
    def __init__(self, api_key: Optional[str] = None, model: str = "gemini-2.5-flash") -> None:
        env_name = "GEMINI_" + "API" + "_" + "KEY"
        self.api_key = api_key or os.environ.get(env_name)
        self.model = os.environ.get("GEMINI_MODEL", model)
        self._last_raw_text: Optional[str] = None

    def plan(self, prd: Dict[str, Any], inbox: Optional[List[Dict[str, Any]]]) -> Dict[str, Any]:
        if not self.api_key:
            env_name = "GEMINI_" + "API" + "_" + "KEY"
            raise ValueError(f"{env_name} is required")
        prompt = _build_prompt(prd, inbox or [])
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
        if ok:
            return job

        fix_prompt = _build_schema_fix_prompt(prompt, raw, err)
        fixed = self._generate_content(fix_prompt)
        self._last_raw_text = fixed
        fixed_job = extract_json_object(fixed)
        ok2, err2 = _validate_job(fixed_job)
        if not ok2:
            raise RuntimeError(f"Job failed validation after schema fix: {err2}")
        return fixed_job

    def _generate_content(self, prompt: str) -> str:
        base = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:generateContent"
        )
        url = base + "?" + urllib.parse.urlencode({"key": self.api_key})
        payload = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.0, "maxOutputTokens": 4096},
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
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

        return _extract_text_from_response(data)

    def debug_snapshot(self) -> Dict[str, Any]:
        return {
            "provider": "gemini_ai_studio",
            "model": self.model,
            "raw_text": self._last_raw_text or "",
        }


def _repo_root() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.normpath(os.path.join(here, "..", "..", ".."))


def _validate_job(job: Dict[str, Any]) -> Tuple[bool, str]:
    validate_script = os.path.join(_repo_root(), "tools", "validate_job.py")
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


def _build_prompt(prd: Dict[str, Any], inbox: List[Dict[str, Any]]) -> str:
    prd_json = json.dumps(prd, indent=2, ensure_ascii=True)
    inbox_json = json.dumps(inbox, indent=2, ensure_ascii=True)
    template = (
        '{"job_id":"optional-id","date":"YYYY-MM-DD","niche":"...",'
        '"video":{"length_seconds":15,"aspect_ratio":"9:16","fps":30,"resolution":"1080x1920"},'
        '"script":{"hook":"...","voiceover":"...","ending":"..."},'
        '"shots":[{"t":0,"visual":"...","action":"...","caption":"..."}],'
        '"captions":["..."],"hashtags":["#cat","#shorts","#pets"],'
        '"render":{"background_asset":"assets/demo/flight_composite.mp4",'
        '"subtitle_style":"big_bottom","output_basename":"..."}}'
    )
    rules = (
        "Return ONLY a single JSON object. No markdown, no code fences, no commentary.\n"
        "Top-level keys required: job_id, date, niche, video, script, shots, captions, hashtags, render.\n"
        "date must be YYYY-MM-DD.\n"
        "video must be an object: length_seconds (10-60 int), aspect_ratio 9:16, fps 24-60 int, resolution 1080x1920.\n"
        "shots must be 6-14 objects with keys: t (int), visual (string), action (string), caption (string).\n"
        "captions must be 4-24 strings (1-80 chars).\n"
        "hashtags must be 3-20 strings matching ^#\\w[\\w_]*$ (no hyphens or spaces).\n"
        "render.subtitle_style must be big_bottom or karaoke_bottom.\n"
        "Use a background_asset under assets/demo/ if no other asset is specified.\n"
    )
    return (
        "You are the Planner for Cat AI Factory.\n"
        f"{rules}\n"
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
        "- Escape any embedded double quotes inside strings (\\\")\n"
        "- Do NOT change the intended content; only fix JSON validity/escaping\n\n"
        "Previous response to repair:\n"
        f"{prior_response}\n"
    )


def _looks_truncated(raw: str) -> bool:
    s = raw.strip()
    return ("{" in s) and ("}" not in s)


def _build_schema_fix_prompt(original_prompt: str, prior_response: str, error_text: str) -> str:
    return (
        "Your previous response did not pass schema validation.\n"
        "Return ONLY a single JSON object. No markdown, no code fences, no commentary.\n"
        "Fix only to satisfy the schema: types, required fields, min/max items, and patterns.\n"
        "Keep top-level keys exactly as required: job_id, date, niche, video, script, shots, captions, hashtags, render.\n\n"
        "Validation error:\n"
        f"{error_text}\n\n"
        "Original prompt (for reference):\n"
        f"{original_prompt}\n\n"
        "Previous response (to fix):\n"
        f"{prior_response}\n"
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
