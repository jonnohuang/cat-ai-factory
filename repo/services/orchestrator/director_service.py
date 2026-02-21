#!/usr/bin/env python3
"""Director Service: Shot-by-shot orchestration and assembly (PR-39)."""

import json
import os
import pathlib
import subprocess
import sys
from typing import Any, Dict, List, Optional, Tuple


class DirectorService:
    def __init__(self, job_id: str, sandbox_root: pathlib.Path, repo_root: pathlib.Path):
        self.job_id = job_id
        self.sandbox_root = sandbox_root
        self.repo_root = repo_root
        self.director_dir = sandbox_root / "logs" / job_id / "director"
        self.state_path = self.director_dir / "state.v1.json"
        self.shots_dir = sandbox_root / "output" / job_id / "shots"
        
        self.director_dir.mkdir(parents=True, exist_ok=True)
        self.shots_dir.mkdir(parents=True, exist_ok=True)

    def load_state(self) -> Dict[str, Any]:
        if self.state_path.exists():
            try:
                return json.loads(self.state_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {
            "version": "director_state.v1",
            "job_id": self.job_id,
            "shots": {},  # shot_id -> {status: "pending"|"render"|"failed"|"ready", attempt_id: "...", path: "..."}
            "assembly": {"status": "pending", "path": None}
        }

    def save_state(self, state: Dict[str, Any]) -> None:
        self.state_path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")

    def sync_shots(self, job_payload: Dict[str, Any]) -> List[str]:
        """
        Synchronize shot list from job and return shot_ids that need work.
        """
        state = self.load_state()
        job_shots = job_payload.get("shots", [])
        
        pending_ids = []
        for shot in job_shots:
            shot_id = shot.get("shot_id")
            if not shot_id:
                continue
            
            # Check if already ready on disk
            shot_out_dir = self.shots_dir / shot_id
            result_json = shot_out_dir / "result.json"
            final_mp4 = shot_out_dir / "final.mp4"
            
            if result_json.exists() and final_mp4.exists():
                state["shots"][shot_id] = {
                    "status": "ready",
                    "path": str(final_mp4.relative_to(self.sandbox_root))
                }
            else:
                current = state["shots"].get(shot_id, {})
                if current.get("status") != "ready":
                    state["shots"][shot_id] = {"status": "pending"}
                    pending_ids.append(shot_id)
        
        self.save_state(state)
        return pending_ids

    def get_shot_output_dir(self, shot_id: str) -> pathlib.Path:
        return self.shots_dir / shot_id

    def assemble(self, job_payload: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """
        Concatenate all 'ready' shots into the final final.mp4.
        """
        state = self.load_state()
        job_shots = job_payload.get("shots", [])
        shot_paths = []
        
        for shot in job_shots:
            shot_id = shot.get("shot_id")
            s_state = state["shots"].get(shot_id)
            if not s_state or s_state.get("status") != "ready":
                return False, f"Shot {shot_id} is not ready for assembly."
            
            full_path = self.sandbox_root / s_state["path"]
            if not full_path.exists():
                return False, f"Shot {shot_id} path {full_path} missing on disk."
            shot_paths.append(full_path)

        if not shot_paths:
            return False, "No shots to assemble."

        # Create ffmpeg concat list
        concat_list_path = self.director_dir / "concat_list.txt"
        with concat_list_path.open("w", encoding="utf-8") as f:
            for p in shot_paths:
                f.write(f"file '{p.absolute()}'\n")

        final_out = self.sandbox_root / "output" / self.job_id / "final.mp4"
        final_out.parent.mkdir(parents=True, exist_ok=True)
        
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", str(concat_list_path),
            "-c", "copy",
            str(final_out)
        ]
        
        try:
            subprocess.run(cmd, check=True, capture_output=True)
            state["assembly"] = {
                "status": "completed",
                "path": str(final_out.relative_to(self.sandbox_root))
            }
            self.save_state(state)
            return True, None
        except subprocess.CalledProcessError as e:
            err_msg = e.stderr.decode()
            return False, f"Assembly failed: {err_msg}"
