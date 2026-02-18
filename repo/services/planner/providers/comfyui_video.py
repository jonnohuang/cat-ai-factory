from __future__ import annotations

import datetime as dt
import json
import os
import pathlib
import re
from typing import Any, Dict, List, Optional

from .base import BaseProvider


def _today_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).date().isoformat()


def _slug(text: str) -> str:
    clean = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return clean[:48] or "comfyui-job"


def _prompt_text(prd: Dict[str, Any]) -> str:
    for key in ("prompt", "concept", "title"):
        v = prd.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return "Mochi comfyui continuity test"


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
        self.workflow_id = os.environ.get("COMFYUI_WORKFLOW_ID", "").strip() or "caf_dance_loop_v1"
        self.workflow_path = self._resolve_workflow_path(self.workflow_id)

    @staticmethod
    def _repo_root() -> pathlib.Path:
        # .../repo/services/planner/providers/comfyui_video.py -> workspace root at parents[4]
        return pathlib.Path(__file__).resolve().parents[4]

    def _resolve_workflow_path(self, workflow_id: str) -> Optional[pathlib.Path]:
        if not workflow_id:
            return None
        path = self._repo_root() / "repo" / "workflows" / "comfy" / f"{workflow_id}.json"
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict) or not payload:
                return None
        except Exception:
            return None
        return path

    def generate_job(
        self,
        prd: Dict[str, Any],
        inbox: Optional[List[Dict[str, Any]]] = None,
        hero_registry: Optional[Dict[str, Any]] = None,
        quality_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        _ = inbox, hero_registry, quality_context
        if not self.base_url:
            print("WARNING planner provider=comfyui_video missing COMFYUI_BASE_URL")
        if self.workflow_path is None:
            print(
                f"WARNING planner provider=comfyui_video workflow not found/invalid for COMFYUI_WORKFLOW_ID={self.workflow_id!r}"
            )
        else:
            print(
                "INFO planner provider=comfyui_video "
                f"workflow_id={self.workflow_id} workflow_path={self.workflow_path.as_posix()}"
            )
        prompt = _prompt_text(prd)
        basename = _slug(prompt)
        date = prd.get("date") if isinstance(prd.get("date"), str) else _today_utc()
        niche = prd.get("niche") if isinstance(prd.get("niche"), str) else "cats"
        workflow_tag = self.workflow_id.replace("_", "-")
        job: Dict[str, Any] = {
            "job_id": f"{basename[:34]}-comfy",
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
                "voiceover": (
                    f"ComfyUI adapter scaffold run for: {prompt}. "
                    f"Use workflow {self.workflow_id} and keep continuity stable for QC gates."
                ),
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
            "captions": ["Mochi", "On beat", "ComfyUI lane", "Loop"],
            "hashtags": ["#cat", "#shorts", "#dance"],
            "render": {
                "background_asset": "assets/demo/flight_composite.mp4",
                "subtitle_style": "big_bottom",
                "output_basename": f"{basename}-{workflow_tag}-comfy",
            },
        }
        return job
