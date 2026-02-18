from __future__ import annotations

import datetime as dt
import os
import re
from typing import Any, Dict, List, Optional

from .base import BaseProvider


def _today_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).date().isoformat()


def _slug(text: str) -> str:
    clean = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return clean[:48] or "grok-image-job"


def _prompt_text(prd: Dict[str, Any]) -> str:
    for key in ("prompt", "concept", "title"):
        v = prd.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return "Mochi storyboard seed test"


def _seed_assets_from_context(quality_context: Optional[Dict[str, Any]]) -> List[str]:
    if not isinstance(quality_context, dict):
        return []
    sb = quality_context.get("storyboard_i2v")
    if not isinstance(sb, dict):
        return []
    seeds = sb.get("seed_frame_assets")
    if not isinstance(seeds, list):
        return []
    out: List[str] = []
    for s in seeds:
        if isinstance(s, str) and s.strip():
            out.append(s.strip())
    dedup: List[str] = []
    seen = set()
    for s in out:
        if s in seen:
            continue
        seen.add(s)
        dedup.append(s)
    return dedup[:3]


class GrokImageProvider(BaseProvider):
    @property
    def name(self) -> str:
        return "grok_image"

    @property
    def default_model(self) -> str:
        return "grok-image-stub"

    def __init__(self) -> None:
        self.model = self.default_model
        # Prefer dedicated Grok key; keep OPENAI_API_KEY fallback for backward compatibility.
        self.api_key = os.environ.get("GROK_API_KEY", "").strip() or os.environ.get("OPENAI_API_KEY", "").strip()

    def generate_job(
        self,
        prd: Dict[str, Any],
        inbox: Optional[List[Dict[str, Any]]] = None,
        hero_registry: Optional[Dict[str, Any]] = None,
        quality_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        _ = inbox, hero_registry
        prompt = _prompt_text(prd)
        if not self.api_key:
            print("WARNING planner provider=grok_image missing GROK_API_KEY (and OPENAI_API_KEY fallback)")
        basename = _slug(prompt)
        date = prd.get("date") if isinstance(prd.get("date"), str) else _today_utc()
        niche = prd.get("niche") if isinstance(prd.get("niche"), str) else "cats"
        seeds = _seed_assets_from_context(quality_context)
        if not seeds:
            seeds = ["assets/demo/fight_composite.mp4"]
        background_asset = seeds[0]
        if not (background_asset.startswith("assets/") or background_asset.startswith("sandbox/assets/")):
            background_asset = "assets/demo/fight_composite.mp4"
        job: Dict[str, Any] = {
            "job_id": f"{basename[:33]}-grokimg",
            "date": date,
            "lane": "image_motion",
            "niche": niche,
            "video": {
                "length_seconds": 12,
                "aspect_ratio": "9:16",
                "fps": 30,
                "resolution": "1080x1920",
            },
            "script": {
                "hook": "Mochi storyboard seed test",
                "voiceover": f"Grok image adapter scaffold run for: {prompt}. Prioritize stable hero framing and continuity.",
                "ending": "Use frame-guided loop continuity.",
            },
            "shots": [
                {"t": 0, "visual": "seed frame one", "action": "establish", "caption": "Seed 1"},
                {"t": 2, "visual": "seed frame two", "action": "move", "caption": "Seed 2"},
                {"t": 4, "visual": "seed frame three", "action": "accent", "caption": "Seed 3"},
                {"t": 6, "visual": "hero close", "action": "hold", "caption": "Hero"},
                {"t": 8, "visual": "hero mid", "action": "turn", "caption": "Continuity"},
                {"t": 10, "visual": "loop seam", "action": "reset", "caption": "Loop"},
            ],
            "captions": ["Seeded", "Framed", "Stable", "Loop"],
            "hashtags": ["#cat", "#shorts", "#storyboard"],
            "render": {
                "background_asset": background_asset,
                "subtitle_style": "big_bottom",
                "output_basename": f"{basename}-grokimg",
            },
            "image_motion": {
                "seed_frames": seeds,
                "motion_preset": "pan_lr",
            },
        }
        return job
