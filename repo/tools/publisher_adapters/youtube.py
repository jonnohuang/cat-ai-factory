"""
YouTube Publisher Adapter (ADR-0021)
Generated 'v1' bundle for YouTube.
"""
from typing import Any, Dict
from .adapter import PublisherAdapter

class YouTubeAdapter(PublisherAdapter):
    def __init__(self):
        super().__init__("youtube")

    def generate_checklist_content(self, publish_plan: Dict[str, Any]) -> str:
        """
        Generates the posting checklist for YouTube.
        """
        job_id = publish_plan.get("job_id", "UNKNOWN_JOB")
        platform_plan = publish_plan.get("platform_plans", {}).get("youtube", {})
        
        # Build the checklist text
        lines = []
        lines.append(f"POSTING CHECKLIST -- YOUTUBE -- Job: {job_id}")
        lines.append("---------------------------------------------------")
        lines.append("[ ] 1. Log in to YouTube Studio (correct channel?).")
        lines.append("[ ] 2. Click 'Create' -> 'Upload Video'.")
        
        clips = platform_plan.get("clips", [])
        for i, clip in enumerate(clips):
            clip_idx = i + 1
            clip_name = f"clip-{str(clip_idx).zfill(3)}"
            lines.append(f"\n--- CLIP {clip_idx} ({clip_name}) ---")
            lines.append(f"[ ] 3.{clip_idx}.1 Drag & Drop 'clips/{clip_name}/video/final.mp4'.")
            lines.append(f"[ ] 3.{clip_idx}.2 Copy Title from 'clips/{clip_name}/copy/copy.en.txt' (or correct language).")
            lines.append(f"[ ] 3.{clip_idx}.3 Copy Description from same file.")
            lines.append(f"[ ] 3.{clip_idx}.4 Set Visibility to 'Public' (or as planned).")
            lines.append(f"[ ] 3.{clip_idx}.5 Select 'Not made for kids'.")
            lines.append(f"[ ] 3.{clip_idx}.6 Add Tags from plan if defined.")
            lines.append(f"[ ] 3.{clip_idx}.7 Check 'clips/{clip_name}/audio/audio_notes.txt' for audio details.")
        
        lines.append("\n---------------------------------------------------")
        lines.append("Done!")
        
        return "\n".join(lines)
