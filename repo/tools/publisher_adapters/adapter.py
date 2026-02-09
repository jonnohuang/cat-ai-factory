"""
Publisher Adapter Interface & Shared Bundle Builder (ADR-0021)

This module defines the abstract base class for valid publisher adapters
and implements the shared, deterministic logic for generating export bundles.

Strict adherence to ADR-0021:
- Atomic writes: Build to tmp, validate, verify-swap, cleanup.
- Deterministic clip naming: clip-001, clip-002...
- Hard constraints: Missing required assets fail the build.
- Secrets: Scanned and rejected.
- Path safety: Enforces writes within restrictions relative to repo root.
"""

import abc
import json
import os
import re
import shutil
import uuid
from pathlib import Path
from typing import Any, Dict, Optional
from .copy_format import clip_id_dirname, format_copy

# --- Secret Scanning (Reused from validate_publish_plan) ---
SECRET_PATTERNS = [
    r"api_key", r"token", r"cookie", r"authorization", 
    r"secret", r"password", r"bearer"
]
SECRET_REGEX = re.compile("|".join(SECRET_PATTERNS), re.IGNORECASE)

def scan_for_secrets(data: Any, path: str = "") -> None:
    """Recursively scan keys for secret patterns. Raises ValueError if found."""
    if isinstance(data, dict):
        for key, value in data.items():
            current_path = f"{path}.{key}" if path else key
            if SECRET_REGEX.search(key):
                raise ValueError(f"SECURITY ERROR: Potential secret found in key: {current_path}")
            scan_for_secrets(value, current_path)
    elif isinstance(data, list):
        for i, item in enumerate(data):
            current_path = f"{path}[{i}]"
            scan_for_secrets(item, current_path)

# --- Shared Builder Logic ---

class SharedBundleBuilder:
    """
    Deterministic, ADR-0021 compliant bundle generator.
    Called by platform adapters to build the 'dist_artifacts/.../bundles/<platform>/v1/' tree.
    """
    
    @staticmethod
    def _get_repo_root() -> Path:
        """
        Derives the repository root based on the file location.
        Assumes file is at: repo/tools/publisher_adapters/adapter.py
        Root is 4 levels up: publisher_adapters -> tools -> repo -> (ROOT)
        """
        return Path(__file__).resolve().parent.parent.parent.parent

    @staticmethod
    def _validate_job_id(job_id: str) -> None:
        """
        Validates job_id is filesystem-safe and contains no traversal patterns.
        """
        if not job_id or not isinstance(job_id, str):
            raise ValueError("job_id must be a non-empty string.")
            
        # Check for traversal, separators, or prohibited characters
        # Allow alphanumeric, dashes, underscores, dots (but not ..)
        if ".." in job_id or "/" in job_id or "\\" in job_id:
            raise ValueError(f"Security Error: Invalid job_id '{job_id}'. Must not contain path separators or traversal.")
            
        if not re.match(r"^[a-zA-Z0-9_\-\.]+$", job_id):
             raise ValueError(f"Security Error: Invalid characters in job_id '{job_id}'.")

    @staticmethod
    def _is_relative_to(path: Path, other: Path) -> bool:
        """
        Safe implementation of is_relative_to (Python 3.9+).
        Fallbacks to try/except ValueError for older Pythons if needed.
        """
        try:
            # Attempt native method (Py3.9+)
            if hasattr(path, "is_relative_to"):
                return path.is_relative_to(other)
            else:
                # Fallback for Py3.8
                path.relative_to(other)
                return True
        except ValueError:
            return False

    @staticmethod
    def build_bundle(
        job_id: str,
        platform: str,
        publish_plan: Dict[str, Any],
        checklist_content: str,
        dist_root: Path
    ) -> Optional[Path]:
        """
        Generates the v1 bundle for a specific platform.
        """
        
        # 0. Safety Guard: Enforce dist_root and job_id
        SharedBundleBuilder._validate_job_id(job_id)
        
        repo_root = SharedBundleBuilder._get_repo_root()
        expected_dist_root = (repo_root / "sandbox" / "dist_artifacts").resolve()
        
        # Resolve dist_root relative to repo_root if it's relative (e.g., "sandbox/dist_artifacts")
        # This makes it robust to CWD.
        if not dist_root.is_absolute():
            resolved_dist = (repo_root / dist_root).resolve()
        else:
            resolved_dist = dist_root.resolve()
        
        if resolved_dist != expected_dist_root:
             raise ValueError(f"Security Error: dist_root must resolve to '{expected_dist_root}', got: {resolved_dist}")

        # 1. Validate Plan Scope
        if "platform_plans" not in publish_plan:
            raise ValueError("Invalid publish_plan: missing 'platform_plans'")
        
        platform_plan = publish_plan["platform_plans"].get(platform)
        if not platform_plan:
            return None

        # 2. Prepare Paths
        bundle_root_final = resolved_dist / job_id / "bundles" / platform / "v1"
        
        # Path Traversal Check (Redundant if job_id safe, but good measure)
        if not SharedBundleBuilder._is_relative_to(bundle_root_final, resolved_dist):
             raise ValueError(f"Security Error: computed path {bundle_root_final} escapes dist_root")

        # Atomic Write Setup
        bundle_parent = bundle_root_final.parent
        bundle_parent.mkdir(parents=True, exist_ok=True)
        
        nonce = str(uuid.uuid4())[:8]
        bundle_root_tmp = bundle_parent / f"v1.__tmp__{nonce}"
        
        if bundle_root_tmp.exists():
            shutil.rmtree(bundle_root_tmp)
        bundle_root_tmp.mkdir(parents=True)

        try:
            # 3. Create Structure
            clips_dir = bundle_root_tmp / "clips"
            clips_dir.mkdir()
            
            checklists_dir = bundle_root_tmp / "checklists"
            checklists_dir.mkdir()
            
            # 4. Generate Checklist
            checklist_filename = f"posting_checklist_{platform}.txt"
            with open(checklists_dir / checklist_filename, "w", encoding="utf-8") as f:
                f.write(checklist_content)
                
            # 5. Process Clips
            clips_meta = platform_plan.get("clips", [])
            
            # Guard against empty clips if strictly required?
            # User suggested "if clips empty, return None or fail hard".
            # For now, let's allow empty clips if the plan implies it (unlikely), 
            # but usually a plan with no clips is invalid.
            if not clips_meta:
                 # Reverting to "no plan for platform" behavior or explicit empty? 
                 # Let's check user intent: "either return None... or fail hard".
                 # If platform key exists but clips is empty, likely valid but useless.
                 # Let's fail hard for safety per ADR strictness.
                 raise ValueError(f"Invalid plan: No clips defined for {platform}")

            for idx, clip_meta in enumerate(clips_meta):
                clip_dirname = clip_id_dirname(clip_meta, idx)
                clip_dir = clips_dir / clip_dirname
                clip_dir.mkdir()
                
                # Subdirs
                (clip_dir / "video").mkdir()
                (clip_dir / "copy").mkdir()
                (clip_dir / "audio" / "assets").mkdir(parents=True)
                
                # A. Video (Physical Copy)
                src_video_str = clip_meta.get("video_path")
                if not src_video_str:
                     raise ValueError(f"Missing video_path for clip {idx}")
                
                # Strict Video Path Logic
                expected_output_root = (repo_root / "sandbox" / "output" / job_id).resolve()
                
                # Handle /sandbox/... or sandbox/... inputs mapping to repo_root
                if src_video_str.startswith("/sandbox/") or src_video_str.startswith("sandbox/"):
                    # Clean leading slash for join
                    clean_path = src_video_str.lstrip("/")
                    abs_src_video = (repo_root / clean_path).resolve()
                else:
                    # Treat as absolute or relative path, but must resolve strictly
                    abs_src_video = Path(src_video_str).resolve()

                # Validate strictness
                if not SharedBundleBuilder._is_relative_to(abs_src_video, expected_output_root):
                     raise ValueError(f"Security Error: source video '{src_video_str}' must be a valid sandbox path (e.g. 'sandbox/output/{job_id}/final.mp4'). Absolute host paths are discouraged.")
                
                if not abs_src_video.exists():
                    raise FileNotFoundError(f"Required video artifact not found: {abs_src_video}")
                
                dst_video = clip_dir / "video" / "final.mp4"
                shutil.copy2(abs_src_video, dst_video)
                
                # B. Captions (Optional)
                potential_srt = abs_src_video.parent / "final.srt"
                if potential_srt.exists():
                    (clip_dir / "captions").mkdir()
                    shutil.copy2(potential_srt, clip_dir / "captions" / "final.srt")
                
                # C. Copy
                for lang in ["en", "zh-Hans"]:
                    content = format_copy(platform, platform_plan, clip_meta, lang)
                    with open(clip_dir / "copy" / f"copy.{lang}.txt", "w", encoding="utf-8") as f:
                        f.write(content)
                        
                # D. Audio
                audio_plan = clip_meta.get("audio_plan")
                if not audio_plan:
                    raise ValueError(f"Missing audio_plan for clip {idx}")
                    
                with open(clip_dir / "audio" / "audio_plan.json", "w", encoding="utf-8") as f:
                    json.dump(audio_plan, f, indent=2)
                    
                audio_notes = clip_meta.get("audio_notes")
                if not audio_notes:
                    raise ValueError(f"Missing audio_notes for clip {idx}")
                
                with open(clip_dir / "audio" / "audio_notes.txt", "w", encoding="utf-8") as f:
                    f.write(audio_notes)
                    
                # Audio Access
                audio_assets = clip_meta.get("audio_assets", [])
                for asset_path in audio_assets:
                    # Resolve logic similar to video but for generic sandbox assets
                    if asset_path.startswith("/sandbox/") or asset_path.startswith("sandbox/"):
                         clean_asset = asset_path.lstrip("/")
                         abs_asset = (repo_root / clean_asset).resolve()
                    else:
                         abs_asset = Path(asset_path).resolve()
                         
                    sandbox_root = (repo_root / "sandbox").resolve()
                    if not SharedBundleBuilder._is_relative_to(abs_asset, sandbox_root):
                         raise ValueError(f"Security Error: asset {asset_path} must be in sandbox/")
                    
                    if abs_asset.exists():
                        asset_name = abs_asset.name
                        shutil.copy2(abs_asset, clip_dir / "audio" / "assets" / asset_name)
                    else:
                         raise FileNotFoundError(f"Required audio asset not found: {asset_path}")

            # 6. Atomic Rename
            bundle_root_old = None
            if bundle_root_final.exists():
                old_nonce = str(uuid.uuid4())[:8]
                bundle_root_old = bundle_parent / f"v1.__old__{old_nonce}"
                os.rename(bundle_root_final, bundle_root_old)
            
            try:
                os.rename(bundle_root_tmp, bundle_root_final)
            except OSError:
                # Rollback
                if bundle_root_old and bundle_root_old.exists() and not bundle_root_final.exists():
                    try:
                        os.rename(bundle_root_old, bundle_root_final)
                    except OSError:
                        pass # Double fault
                # Ensure we re-raise to trigger finally cleanup
                raise 
            
            # Cleanup Old
            if bundle_root_old and bundle_root_old.exists():
                shutil.rmtree(bundle_root_old)
                
            return bundle_root_final

        except Exception as e:
            raise e
            
        finally:
             # Always cleanup tmp if it still exists (success or fail)
             # If rename succeeded, tmp is gone. If failed, tmp is there.
             # If exception happens before rename, tmp is there.
             if bundle_root_tmp.exists():
                 shutil.rmtree(bundle_root_tmp)

# --- Adapter Base Class ---

class PublisherAdapter(abc.ABC):
    """
    Abstract Base Class for Platform Adapters.
    """
    
    def __init__(self, platform_name: str):
        self.platform_name = platform_name
        
    def generate_bundle(self, job_id: str, publish_plan_path: str, dist_root: str = "sandbox/dist_artifacts") -> Optional[Path]:
        """
        Main entry point.
        """
        with open(publish_plan_path, "r") as f:
            plan = json.load(f)
            
        scan_for_secrets(plan)
        
        if plan.get("job_id") != job_id:
            raise ValueError(f"Plan job_id '{plan.get('job_id')}' does not match requested '{job_id}'")
            
        checklist_content = self.generate_checklist_content(plan)
        
        # Pass path object
        dist_path = Path(dist_root)
        result_path = SharedBundleBuilder.build_bundle(
            job_id=job_id,
            platform=self.platform_name,
            publish_plan=plan,
            checklist_content=checklist_content,
            dist_root=dist_path
        )
        
        return result_path
    
    @abc.abstractmethod
    def generate_checklist_content(self, publish_plan: Dict[str, Any]) -> str:
        """
        Subclasses must implement this.
        """
        pass
