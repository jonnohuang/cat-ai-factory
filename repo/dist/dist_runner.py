import json
import logging
import os
import pathlib
import sys
import time
import traceback
from typing import Any, Dict, Set

# Configuration and Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s"
)
logger = logging.getLogger("dist_runner")

# Add repo root to sys.path
repo_root = pathlib.Path(__file__).resolve().parents[2]
sys.path.append(str(repo_root))

from repo.tools.publisher_adapters.instagram import InstagramAdapter
from repo.tools.publisher_adapters.tiktok import TikTokAdapter
from repo.tools.publisher_adapters.x import XAdapter
from repo.tools.publisher_adapters.youtube import YouTubeAdapter

# Constants
SANDBOX_PATH = (repo_root / os.getenv("CAF_SANDBOX_PATH", "sandbox")).resolve()
if not SANDBOX_PATH.exists():
    SANDBOX_PATH.mkdir(parents=True, exist_ok=True)

INBOX_PATH = SANDBOX_PATH / "inbox"
DIST_ARTIFACTS_PATH = SANDBOX_PATH / "dist_artifacts"
POLL_INTERVAL_SEC = 2

# Adapter Registry
PLATFORM_ADAPTERS = {
    "youtube": YouTubeAdapter,
    "tiktok": TikTokAdapter,
    "instagram": InstagramAdapter,
    "x": XAdapter,
}

def load_json(path: pathlib.Path) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def write_state(job_id: str, platform: str, nonce: str, status: str, error: str = None):
    """Update the platform.state.json to track progress and idempotency."""
    state_path = DIST_ARTIFACTS_PATH / job_id / f"{platform}.state.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    
    state = {
        "job_id": job_id,
        "platform": platform,
        "nonce": str(nonce),
        "status": status,
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    if error:
        state["error"] = error
        
    with open(state_path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)

def process_approval(approval_path: pathlib.Path):
    """Processes a single approval artifact."""
    try:
        data = load_json(approval_path)
    except Exception as e:
        logger.error(f"Failed to load approval {approval_path.name}: {e}")
        return

    job_id = data.get("job_id")
    platform = data.get("platform")
    nonce = data.get("nonce")
    approved = data.get("approved", False)

    if not all([job_id, platform, nonce]):
        logger.warning(f"Invalid approval artifact format in {approval_path.name}")
        return

    if not approved:
        logger.info(f"Skipping rejection for {job_id} on {platform}")
        return

    # 1. Idempotency Check: Read existing state
    state_path = DIST_ARTIFACTS_PATH / job_id / f"{platform}.state.json"
    if state_path.exists():
        try:
            state = load_json(state_path)
            if str(state.get("nonce")) == str(nonce) and state.get("status") in ["BUNDLE_GENERATED", "POSTED"]:
                # Already processed this specific approval
                return
        except Exception:
            pass

    logger.info(f"🚀 Processing approval: job={job_id}, platform={platform}, nonce={nonce}")
    
    plan_path = DIST_ARTIFACTS_PATH / job_id / "publish_plan.json"
    if not plan_path.exists():
        logger.error(f"Missing publish_plan.json for {job_id} at {plan_path}")
        write_state(job_id, platform, nonce, "FAILED", error="Missing publish_plan.json")
        return

    # 2. Trigger Adapter
    adapter_cls = PLATFORM_ADAPTERS.get(platform)
    if not adapter_cls:
        logger.error(f"No adapter found for platform: {platform}")
        write_state(job_id, platform, nonce, "FAILED", error=f"Unsupported platform: {platform}")
        return

    try:
        adapter = adapter_cls()
        logger.info(f"Generating bundle for {platform}...")
        bundle_path = adapter.generate_bundle(
            job_id=job_id,
            publish_plan_path=str(plan_path),
            dist_root=str(DIST_ARTIFACTS_PATH)
        )
        
        if bundle_path:
            logger.info(f"✅ Bundle generated: {bundle_path}")
            write_state(job_id, platform, nonce, "BUNDLE_GENERATED")
        else:
            logger.warning(f"No plan content for {platform} in {job_id}")
            write_state(job_id, platform, nonce, "SKIPPED", error="Platform not in plan")
            
    except Exception as e:
        logger.error(f"Bundle generation failed for {job_id} on {platform}: {e}")
        logger.error(traceback.format_exc())
        write_state(job_id, platform, nonce, "FAILED", error=str(e))

def run_loop():
    """Main polling loop."""
    logger.info("🐾 CAF Distribution Runner started.")
    logger.info(f"- Watching: {INBOX_PATH}")
    logger.info(f"- Poll interval: {POLL_INTERVAL_SEC}s")

    if not INBOX_PATH.exists():
        INBOX_PATH.mkdir(parents=True)

    processed_files: Set[str] = set()

    try:
        while True:
            # 1. Look for approve-*.json
            approval_files = sorted(INBOX_PATH.glob("approve-*.json"))
            
            for ap in approval_files:
                # We use the filename as a coarse unique key for in-memory tracking
                # but process_approval handles persistent idempotency via state files.
                process_approval(ap)
            
            time.sleep(POLL_INTERVAL_SEC)
    except KeyboardInterrupt:
        logger.info("Runner stopped by user.")
    except Exception as e:
        logger.critical(f"FATAL ERROR: {e}")
        logger.critical(traceback.format_exc())
        sys.exit(1)

if __name__ == "__main__":
    run_loop()
