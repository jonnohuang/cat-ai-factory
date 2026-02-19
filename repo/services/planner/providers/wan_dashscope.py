from __future__ import annotations

import json
import os
import pathlib
import re
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

from .base import BaseProvider, today_utc


def _repo_root_path() -> pathlib.Path:
    # repo/services/planner/providers/wan_dashscope.py -> <repo_root>
    return pathlib.Path(__file__).resolve().parents[4]


def _safe_slug(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:48] or "wan-dashscope-job"


def _job_context_text(job: Dict[str, Any], prd: Dict[str, Any]) -> str:
    parts: List[str] = []
    for key in ("prompt", "title", "concept", "objective"):
        val = prd.get(key)
        if isinstance(val, str) and val.strip():
            parts.append(val.strip())
    script = job.get("script")
    if isinstance(script, dict):
        for key in ("hook", "voiceover", "ending"):
            val = script.get(key)
            if isinstance(val, str) and val.strip():
                parts.append(val.strip())
    return " | ".join(parts)[:1200]


def _prompt_text(prd: Dict[str, Any]) -> str:
    for key in ("prompt", "concept", "title"):
        val = prd.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return "Mochi dance continuity smoke"


def _extract_task_id(payload: Any) -> Optional[str]:
    if not isinstance(payload, dict):
        return None
    for path in (
        ("output", "task_id"),
        ("output", "taskId"),
        ("task_id",),
        ("taskId",),
    ):
        cur: Any = payload
        ok = True
        for key in path:
            if not isinstance(cur, dict) or key not in cur:
                ok = False
                break
            cur = cur[key]
        if ok and isinstance(cur, str) and cur.strip():
            return cur.strip()
    return None


def _find_first_url(payload: Any) -> Optional[str]:
    if isinstance(payload, str):
        lower = payload.lower()
        if lower.startswith("http://") or lower.startswith("https://"):
            return payload
        return None
    if isinstance(payload, list):
        for item in payload:
            hit = _find_first_url(item)
            if hit:
                return hit
        return None
    if isinstance(payload, dict):
        for key in ("video_url", "url", "resource_url", "file_url"):
            v = payload.get(key)
            hit = _find_first_url(v)
            if hit:
                return hit
        for v in payload.values():
            hit = _find_first_url(v)
            if hit:
                return hit
    return None


def _http_json(
    *,
    url: str,
    method: str,
    headers: Dict[str, str],
    payload: Optional[Dict[str, Any]] = None,
    timeout_s: int = 60,
) -> Dict[str, Any]:
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url=url, data=data, method=method)
    for k, v in headers.items():
        req.add_header(k, v)
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        raw = resp.read().decode("utf-8")
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise RuntimeError("non-object JSON response")
    return parsed


def _download_file(*, url: str, dst_path: pathlib.Path, timeout_s: int = 300) -> None:
    req = urllib.request.Request(url=url, method="GET")
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        data = resp.read()
    dst_path.parent.mkdir(parents=True, exist_ok=True)
    dst_path.write_bytes(data)


class WanDashScopeProvider(BaseProvider):
    @property
    def name(self) -> str:
        return "wan_dashscope"

    @property
    def default_model(self) -> str:
        return "wan2.2-t2v"

    def __init__(self) -> None:
        self.model = os.environ.get("WAN_DASHSCOPE_MODEL", self.default_model).strip() or self.default_model
        self.base_url = (
            os.environ.get("WAN_DASHSCOPE_BASE_URL", "https://dashscope-intl.aliyuncs.com").strip().rstrip("/")
        )
        self.api_key = os.environ.get("DASHSCOPE_API_KEY", "").strip()
        self.poll_seconds = max(30, min(900, int(os.environ.get("WAN_DASHSCOPE_POLL_SECONDS", "240"))))
        self.poll_interval = max(2, min(30, int(os.environ.get("WAN_DASHSCOPE_POLL_INTERVAL", "5"))))

    def generate_job(
        self,
        prd: Dict[str, Any],
        inbox: Optional[List[Dict[str, Any]]] = None,
        hero_registry: Optional[Dict[str, Any]] = None,
        quality_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        _ = inbox, hero_registry, quality_context
        prompt = _prompt_text(prd)
        basename = _safe_slug(prompt)
        date = prd.get("date") if isinstance(prd.get("date"), str) else today_utc()
        niche = prd.get("niche") if isinstance(prd.get("niche"), str) else "cats"
        job: Dict[str, Any] = {
            "job_id": f"{basename[:36]}-wands",
            "date": date,
            "lane": "ai_video",
            "niche": niche,
            "video": {
                "length_seconds": 12,
                "aspect_ratio": "9:16",
                "fps": 30,
                "resolution": "1080x1920",
            },
            "script": {
                "hook": "Mochi dance loop test",
                "voiceover": f"Wan DashScope adapter scaffold run for: {prompt}. Keep timing stable and motion readable.",
                "ending": "Loop cleanly for retry checks.",
            },
            "shots": [
                {"t": 0, "visual": "wide stage", "action": "start groove", "caption": "Mochi starts"},
                {"t": 2, "visual": "mid shot", "action": "side step", "caption": "On beat"},
                {"t": 4, "visual": "mid shot", "action": "spin", "caption": "Spin"},
                {"t": 6, "visual": "wide stage", "action": "pose hit", "caption": "Pose"},
                {"t": 8, "visual": "mid shot", "action": "bounce", "caption": "Bounce"},
                {"t": 10, "visual": "wide stage", "action": "reset", "caption": "Loop"},
            ],
            "captions": ["Mochi", "On beat", "Clean motion", "Loop"],
            "hashtags": ["#cat", "#shorts", "#dance"],
            "render": {
                "background_asset": "assets/demo/fight_composite.mp4",
                "subtitle_style": "big_bottom",
                "output_basename": f"{basename}-wands",
            },
        }

        context = _job_context_text(job, prd)
        rel_video = self._try_generate_video_asset(context=context, job_id=str(job["job_id"]))
        if rel_video:
            render = job.setdefault("render", {})
            render["background_asset"] = rel_video
            job.pop("image_motion", None)
            print(
                f"INFO planner provider={self.name} generated_video_asset={rel_video} lane=ai_video model={self.model}"
            )
        else:
            print(
                "WARNING planner provider="
                f"{self.name} no_generated_video_asset model={self.model} path=fallback_background"
            )
        return job

    def _try_generate_video_asset(self, *, context: str, job_id: str) -> Optional[str]:
        if not self.api_key:
            print(f"WARNING planner provider={self.name} missing DASHSCOPE_API_KEY")
            return None
        submit_url = f"{self.base_url}/api/v1/services/aigc/video-generation/video-synthesis"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "X-DashScope-Async": "enable",
        }
        payload = {
            "model": self.model,
            "input": {
                "prompt": context[:1500] or "Cute cat dance loop, stable camera, clean background.",
            },
            "parameters": {
                "size": "720*1280",
            },
        }
        try:
            submit_resp = _http_json(url=submit_url, method="POST", headers=headers, payload=payload, timeout_s=90)
        except urllib.error.HTTPError as ex:
            print(f"WARNING planner provider={self.name} submit_failed=http_{ex.code}")
            return None
        except Exception as ex:  # pragma: no cover
            print(f"WARNING planner provider={self.name} submit_failed={type(ex).__name__}")
            return None

        task_id = _extract_task_id(submit_resp)
        if not task_id:
            print(f"WARNING planner provider={self.name} missing_task_id")
            return None

        task_url = f"{self.base_url}/api/v1/tasks/{task_id}"
        deadline = time.time() + self.poll_seconds
        while time.time() < deadline:
            try:
                status_resp = _http_json(url=task_url, method="GET", headers=headers, payload=None, timeout_s=60)
            except Exception:
                time.sleep(self.poll_interval)
                continue
            task_status = str(status_resp.get("output", {}).get("task_status", "")).upper()
            if task_status in {"SUCCEEDED", "SUCCESS"}:
                video_url = _find_first_url(status_resp)
                if not video_url:
                    print(f"WARNING planner provider={self.name} missing_video_url task={task_id}")
                    return None
                return self._download_to_asset(video_url=video_url, job_id=job_id)
            if task_status in {"FAILED", "CANCELED"}:
                print(f"WARNING planner provider={self.name} task_failed task={task_id}")
                return None
            time.sleep(self.poll_interval)

        print(f"WARNING planner provider={self.name} task_timeout task={task_id}")
        return None

    def _download_to_asset(self, *, video_url: str, job_id: str) -> Optional[str]:
        safe_job_id = _safe_slug(job_id)
        rel_dir = f"assets/generated/{safe_job_id}"
        out_dir = _repo_root_path() / "sandbox" / rel_dir
        out_path = out_dir / "wan-dashscope-0001.mp4"
        try:
            _download_file(url=video_url, dst_path=out_path, timeout_s=300)
        except Exception as ex:
            print(f"WARNING planner provider={self.name} download_failed={type(ex).__name__}")
            return None
        return f"{rel_dir}/wan-dashscope-0001.mp4"
