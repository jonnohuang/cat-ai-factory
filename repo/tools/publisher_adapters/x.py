"""
X (Twitter) Publisher Adapter (ADR-0021)
Generated 'v1' bundle for X.
"""

from typing import Any, Dict

from .adapter import PublisherAdapter


class XAdapter(PublisherAdapter):
    def __init__(self):
        super().__init__("x")

    def generate_checklist_content(self, publish_plan: Dict[str, Any]) -> str:
        """
        Generates the posting checklist for X.
        """
        job_id = publish_plan.get("job_id", "UNKNOWN_JOB")

        # Build the checklist text
        lines = []
        lines.append(f"POSTING CHECKLIST -- X (TWITTER) -- Job: {job_id}")
        lines.append("---------------------------------------------------")
        lines.append("[ ] 1. Log in to X/Twitter.")

        clips = publish_plan.get("platform_plans", {}).get("x", {}).get("clips", [])
        for i, clip in enumerate(clips):
            clip_idx = i + 1
            clip_name = f"clip-{str(clip_idx).zfill(3)}"
            lines.append(f"\n--- CLIP {clip_idx} ({clip_name}) ---")
            lines.append(
                f"[ ] 3.{clip_idx}.1 Attach Media 'clips/{clip_name}/video/final.mp4'."
            )
            lines.append(
                f"[ ] 3.{clip_idx}.2 Copy Text from 'clips/{clip_name}/copy/copy.en.txt'."
            )
            lines.append(f"[ ] 3.{clip_idx}.3 Add Alt Text (recommended).")
            lines.append(
                f"[ ] 3.{clip_idx}.4 Review 'clips/{clip_name}/audio/audio_notes.txt' for any required audio guidance."
            )

        lines.append("\n---------------------------------------------------")

        return "\n".join(lines)
