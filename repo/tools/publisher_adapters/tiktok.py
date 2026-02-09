"""
TikTok Publisher Adapter (ADR-0021)
Generated 'v1' bundle for TikTok.
"""
from typing import Any, Dict
from .adapter import PublisherAdapter

class TikTokAdapter(PublisherAdapter):
    def __init__(self):
        super().__init__("tiktok")

    def generate_checklist_content(self, publish_plan: Dict[str, Any]) -> str:
        """
        Generates the posting checklist for TikTok.
        """
        job_id = publish_plan.get("job_id", "UNKNOWN_JOB")
        
        # Build the checklist text
        lines = []
        lines.append(f"POSTING CHECKLIST -- TIKTOK -- Job: {job_id}")
        lines.append("---------------------------------------------------")
        lines.append("[ ] 1. Open TikTok App or Web Upload.")
        lines.append("[ ] 2. Upload Video.")
        
        clips = publish_plan.get("platform_plans", {}).get("tiktok", {}).get("clips", [])
        for i, clip in enumerate(clips):
            clip_idx = i + 1
            clip_name = f"clip-{str(clip_idx).zfill(3)}"
            lines.append(f"\n--- CLIP {clip_idx} ({clip_name}) ---")
            lines.append(f"[ ] 3.{clip_idx}.1 Select 'clips/{clip_name}/video/final.mp4'.")
            lines.append(f"[ ] 3.{clip_idx}.2 Add Sound: See 'clips/{clip_name}/audio/audio_notes.txt'.")
            lines.append(f"[ ] 3.{clip_idx}.3 Copy Description from 'clips/{clip_name}/copy/copy.en.txt'.")
            lines.append(f"[ ] 3.{clip_idx}.4 Add Link (if applicable).")
        
        lines.append("\n---------------------------------------------------")
        
        return "\n".join(lines)
