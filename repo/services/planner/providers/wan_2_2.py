from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from .base import BaseProvider, today_utc


def _slug(text: str) -> str:
    clean = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return clean[:48] or "wanlocal-job"


def _prompt_text(prd: Dict[str, Any]) -> str:
    for key in ("prompt", "concept", "title"):
        v = prd.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return "Mochi dance continuity test"


class WanLocalProvider(BaseProvider):
    @property
    def name(self) -> str:
        return "wan_local"

    @property
    def default_model(self) -> str:
        return "wan-2.2-14b"

    def __init__(self) -> None:
        self.model = self.default_model

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

        # Determine length based on prompt keywords
        length_seconds = 12
        if "24s" in prompt.lower() or "24 seconds" in prompt.lower():
            length_seconds = 24

        job: Dict[str, Any] = {
            "job_id": f"{basename[:36]}-wanlocal",
            "date": date,
            "lane": "ai_video",
            "niche": niche,
            "video": {
                "model_family": "wan",
                "model_version": "2.2",
                "length_seconds": length_seconds,
                "aspect_ratio": "9:16",
                "fps": 30,
                "resolution": "1080x1920",
            },
            "script": {
                "hook": "Wan 2.2 Motion Synthesis",
                "voiceover": f"Processing high-fidelity motion for: {prompt}.",
                "ending": "Grand finale loop.",
            },
            "shots": [
                {
                    "shot_id": "shot_0010",
                    "t": 0,
                    "visual": "opening sequence",
                    "action": "intro",
                    "caption": "Opening",
                },
                {
                    "shot_id": "shot_0020",
                    "t": length_seconds // 3,
                    "visual": "mid sequence",
                    "action": "main movement",
                    "caption": "Action",
                },
                {
                    "shot_id": "shot_0030",
                    "t": (length_seconds * 2) // 3,
                    "visual": "closing sequence",
                    "action": "pose lock",
                    "caption": "Final Pose",
                },
            ],
            "captions": ["Wan2.2", "Pose Locked", "GCP GPU"],
            "hashtags": ["#wan22", "#aiart", "#cats"],
            "render": {
                "background_asset": prd.get("background_asset", "assets/demo/processed/dance_loop.mp4"),
                "subtitle_style": "minimal_glow",
                "output_basename": f"{basename}-wanlocal",
            },
        }
        return job


# Backward compatibility alias for older references.
Wan22Provider = WanLocalProvider
