import json
import os
import sys
from unittest.mock import MagicMock, patch

# Add repo to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

from repo.services.planner.providers.gemini_ai_studio import GeminiAIStudioProvider
from repo.services.planner.providers.langgraph_demo import LangGraphDemoProvider


def smoke_test_phase_13():
    print("--- Phase 13 Narrative Smoke Test ---")

    # 1. Setup PRD with 'dance' tag to trigger VPL
    prd = {
        "job_id": "smoke-test-v13",
        "tags": ["dance"],
        "brief": "Mochi dancing high energy"
    }

    provider = LangGraphDemoProvider()

    # 2. Mock Gemini provider to return a valid job and capture inputs
    mock_job = {
        "job_id": "smoke-test-v13",
        "date": "2026-02-24",
        "niche": "cats",
        "video": {
            "length_seconds": 15,
            "aspect_ratio": "9:16",
            "fps": 30,
            "resolution": "1080x1920"
        },
        "script": {
            "hook": "test",
            "voiceover": "test",
            "ending": "test"
        },
        "shots": [
            {"t": 0, "visual": "test", "action": "test", "caption": "test"},
            {"t": 1, "visual": "test", "action": "test", "caption": "test"},
            {"t": 2, "visual": "test", "action": "test", "caption": "test"},
            {"t": 3, "visual": "test", "action": "test", "caption": "test"},
            {"t": 4, "visual": "test", "action": "test", "caption": "test"},
            {"t": 5, "visual": "test", "action": "test", "caption": "test"}
        ],
        "captions": ["test", "test", "test", "test"],
        "hashtags": ["#cat", "#test", "#viral"],
        "render": {
            "background_asset": "assets/demo/fight_composite.mp4",
            "subtitle_style": "big_bottom",
            "output_basename": "test"
        }
    }

    with patch.object(GeminiAIStudioProvider, 'generate_job', return_value=mock_job) as mock_gen:
        print("Executing generate_job...")
        # Note: API Key check is bypassed because we mock generate_job
        job = provider.generate_job(prd)

        # 3. Verify VPL Selection
        # The mock_gen call should have received the enriched PRD
        enriched_prd = mock_gen.call_args[0][0]
        vpl_id = enriched_prd.get("story_context", {}).get("vpl_id")
        print(f"Captured VPL Selection: {vpl_id}")

        # 4. Verify Job Metadata (Story Enrichment)
        viral_id = job.get("metadata", {}).get("viral_pattern_id")
        hook_plan = job.get("metadata", {}).get("hook_plan_v1")

        print(f"Job Metadata Viral Pattern: {viral_id}")
        print(f"Job Metadata Hook Plan: {hook_plan is not None}")

        assert vpl_id == "dance_loop_v1", "VPL selection failed"
        assert viral_id == "dance_loop_v1", "Metadata enrichment failed"
        assert hook_plan is not None, "Hook plan missing from metadata"

    print("--- SMOKE TEST PASSED ---")

if __name__ == "__main__":
    try:
        smoke_test_phase_13()
    except Exception as e:
        print(f"SMOKE TEST FAILED: {e}")
        sys.exit(1)
