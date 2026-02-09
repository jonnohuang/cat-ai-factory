"""
Instagram Publisher Adapter (ADR-0021)
Generated 'v1' bundle for Instagram.
"""
from typing import Any, Dict
from .adapter import PublisherAdapter

class InstagramAdapter(PublisherAdapter):
    def __init__(self):
        super().__init__("instagram")

    def generate_checklist_content(self, publish_plan: Dict[str, Any]) -> str:
        """
        Generates the posting checklist for Instagram.
        """
        job_id = publish_plan.get("job_id", "UNKNOWN_JOB")
        
        # Build the checklist text
        lines = []
        lines.append(f"POSTING CHECKLIST -- INSTAGRAM -- Job: {job_id}")
        lines.append("---------------------------------------------------")
        lines.append("[ ] 1. Open Instagram App (mobile preferred) or Creator Studio.")
        lines.append("[ ] 2. Create New Reel.")
        
        clips = publish_plan.get("platform_plans", {}).get("instagram", {}).get("clips", [])
        for i, clip in enumerate(clips):
            clip_idx = i + 1
            clip_name = f"clip-{str(clip_idx).zfill(3)}"
            lines.append(f"\n--- CLIP {clip_idx} ({clip_name}) ---")
            lines.append(f"[ ] 3.{clip_idx}.1 Select 'clips/{clip_name}/video/final.mp4'.")
            lines.append(f"[ ] 3.{clip_idx}.2 Add Cover (if planned).")
            lines.append(f"[ ] 3.{clip_idx}.3 Copy Caption from 'clips/{clip_name}/copy/copy.en.txt'.")
            lines.append(f"[ ] 3.{clip_idx}.4 Add Music/Audio: See 'clips/{clip_name}/audio/audio_notes.txt'.")
            lines.append(f"[ ] 3.{clip_idx}.5 Tag accounts/location/products if planned.")
            lines.append(f"[ ] 3.{clip_idx}.6 Share to Feed (Recommended).")
        
        lines.append("\n---------------------------------------------------")
        
        return "\n".join(lines)
