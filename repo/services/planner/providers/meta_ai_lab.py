from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional

from .base import BaseProvider, today_utc


def _slug(text: str) -> str:
    clean = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return clean[:48] or "meta-ai-lab-job"


def _prompt_text(prd: Dict[str, Any]) -> str:
    for key in ("prompt", "concept", "title"):
        v = prd.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return "Mochi meta ai lab continuity test"


class MetaAiLabProvider(BaseProvider):
    @property
    def name(self) -> str:
        return "meta_ai_lab"

    @property
    def default_model(self) -> str:
        return "meta-movie-gen-lab-stub"

    def __init__(self) -> None:
        self.model = os.environ.get("META_AI_LAB_MODEL", self.default_model).strip() or self.default_model
        self.base_url = os.environ.get("META_AI_LAB_BASE_URL", "").strip()

    def generate_job(
        self,
        prd: Dict[str, Any],
        inbox: Optional[List[Dict[str, Any]]] = None,
        hero_registry: Optional[Dict[str, Any]] = None,
        quality_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        _ = inbox, hero_registry, quality_context
        prompt = _prompt_text(prd)
        basename = _slug(prompt)
        date = prd.get("date") if isinstance(prd.get("date"), str) else today_utc()
        niche = prd.get("niche") if isinstance(prd.get("niche"), str) else "cats"
        if not os.environ.get("META_AI_LAB_API_KEY", "").strip():
            print("WARNING planner provider=meta_ai_lab missing META_AI_LAB_API_KEY; using scaffold background")
        if not self.base_url:
            print("WARNING planner provider=meta_ai_lab missing META_AI_LAB_BASE_URL; using local scaffold defaults")
        return {
            "job_id": f"{basename[:36]}-metalab",
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
                "voiceover": f"Meta AI lab adapter scaffold run for: {prompt}. Keep cast continuity stable for QC gates.",
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
            "captions": ["Mochi", "On beat", "Meta AI lab lane", "Loop"],
            "hashtags": ["#cat", "#shorts", "#dance"],
            "render": {
                "background_asset": "assets/demo/fight_composite.mp4",
                "subtitle_style": "big_bottom",
                "output_basename": f"{basename}-metalab",
            },
        }
