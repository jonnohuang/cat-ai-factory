from __future__ import annotations

import json
import pathlib
from typing import Any, Dict, List, Optional


class AudioResolver:
    def __init__(self, repo_root: pathlib.Path):
        self.repo_root = repo_root
        self.pack_manifest_path = self.repo_root / "repo/shared/audio_packs/v1.json"

        # Fallback to example for dev/bootstrapping
        if not self.pack_manifest_path.exists():
            self.pack_manifest_path = self.repo_root / "repo/examples/audio_pack.v1.example.json"

        self._packs: List[Dict[str, Any]] = []
        self._load_packs()

    def _load_packs(self):
        if not self.pack_manifest_path.exists():
            return
        try:
            with open(self.pack_manifest_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                # Ensure it's a list or wrap it if it's a single pack registry
                if isinstance(data, dict):
                    self._packs = [data]
                elif isinstance(data, list):
                    self._packs = data
        except Exception:
            self._packs = []

    def resolve_audio_strategy(self, intent_text: str) -> Dict[str, Any]:
        """
        Determines the best audio strategy based on intent.
        Returns a dict compatible with the 'audio' block in job.json.
        """
        text = intent_text.lower()

        # 1. Platform Trending heuristic
        if "trending" in text or "viral" in text or "tiktok" in text or "reels" in text:
            return {
                "mode": "platform_trending",
                "notes": "Silent master requested for platform-native audio sync."
            }

        # 2. Pack Resolution heuristic
        # Default to licensed_pack if not trending
        best_track = self._find_best_track(text)
        if best_track:
            return {
                "mode": "licensed_pack",
                "audio_pack_id": best_track["pack_id"],
                "track_id": best_track["track_id"],
                "audio_asset": best_track["path"] # Compatibility for older worker versions if needed
            }

        # 3. Fallback to legacy or silence
        return {
            "mode": "original_pack",
            "audio_pack_id": "caf_signature_v1",
            "track_id": "mochi_meow_trap",
            "notes": "Fallback to signature audio."
        }

    def _find_best_track(self, text: str) -> Optional[Dict[str, Any]]:
        """
        Finds the most relevant track from available packs.
        """
        candidates = []
        for pack in self._packs:
            pack_id = pack.get("pack_id")
            for track in pack.get("tracks", []):
                # Basic tag matching
                track_tags = [t.lower() for t in track.get("tags", [])]
                score = 0
                if any(tag in text for tag in track_tags):
                    score += 10

                # Priority boost
                score += track.get("priority", 0)

                if score > 0:
                    candidates.append({
                        "pack_id": pack_id,
                        "track_id": track.get("track_id"),
                        "path": track.get("path"),
                        "score": score
                    })

        if not candidates:
            return None

        # Tie-break by score desc, then track_id
        candidates.sort(key=lambda x: (-x["score"], x["track_id"]))
        return candidates[0]
