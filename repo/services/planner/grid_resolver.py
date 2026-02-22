from __future__ import annotations

import json
import pathlib
from typing import Any, Dict, List, Optional


class GridResolver:
    def __init__(self, repo_root: pathlib.Path):
        self.repo_root = repo_root

    def resolve_beat_grid(self, audio_strategy: Dict[str, Any], duration_s: float) -> Dict[str, Any]:
        """
        Resolves or generates a beat grid for the given audio strategy.
        """
        mode = audio_strategy.get("mode")

        # 1. Check for explicit grid in the audio pack (if mode is pack)
        # For now, we'll implement a generative fallback based on BPM

        bpm = audio_strategy.get("bpm", 128) # Default 128
        beats_per_bar = 4

        # Generative Grid construction
        events = []
        beat_interval = 60.0 / bpm

        current_time = 0.0
        beat_count = 1

        while current_time < duration_s:
            # Add a 'cut' eventEvery 4 beats (start of bar)
            if (beat_count - 1) % beats_per_bar == 0:
                events.append({
                    "type": "cut",
                    "time_s": round(current_time, 3),
                    "beat": beat_count,
                    "label": f"bar_{ (beat_count-1)//beats_per_bar + 1 }"
                })

            # Add 'move' or 'effect' on other beats if needed

            current_time += beat_interval
            beat_count += 1

        return {
            "version": "beat_grid.v1",
            "bpm": bpm,
            "beats_per_bar": beats_per_bar,
            "events": events
        }

    def snap_shots_to_grid(self, shots: List[Dict[str, Any]], grid: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Mutates shot timestamps to align with 'cut' events in the grid.
        """
        cuts = [e for e in grid.get("events", []) if e.get("type") == "cut"]
        if not cuts:
            return shots

        new_shots = []
        for i, shot in enumerate(shots):
            # Find the closest cut for this shot
            # For simplicity, we'll map shot_index to cut_index if within range
            if i < len(cuts):
                shot["t"] = cuts[i]["time_s"]
            new_shots.append(shot)

        return new_shots
