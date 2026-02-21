#!/usr/bin/env python3
import pathlib
import sys

# Add repo root to sys.path
repo_root = pathlib.Path(__file__).resolve().parents[2]
sys.path.append(str(repo_root))

from repo.services.planner.asset_resolver import AssetResolver

def test_asset_resolver():
    print("Testing AssetResolver...")
    resolver = AssetResolver(repo_root)
    
    # 1. Test Reference Images for Mochi
    mochi_refs = resolver.resolve_reference_images("Mochi dino dance")
    print(f"Mochi references: {mochi_refs}")
    assert any("mochi_front.png" in r for r in mochi_refs), "Should find mochi front"
    assert any("mochi_profile.png" in r for r in mochi_refs), "Should find mochi profile"
    
    # 2. Test Reference Images for Dance
    dance_refs = resolver.resolve_reference_images("Cat dance loop")
    print(f"Dance references: {dance_refs}")
    assert any("dance_loop_snapshot.png" in r for r in dance_refs), "Should find dance loop snapshot"
    
    # 3. Test Background resolution
    bg_video = resolver.resolve_background_video("Dance party in living room")
    print(f"Background video: {bg_video}")
    assert bg_video and "dance_loop.mp4" in bg_video, "Should find dance loop video"
    
    # 4. Test priority sorting
    # mochi-front (100) should be before mochi-profile (90)
    assert mochi_refs[0].endswith("mochi_front.png")
    
    print("AssetResolver smoke test PASSED!")

if __name__ == "__main__":
    try:
        test_asset_resolver()
    except Exception as e:
        print(f"Smoke test FAILED: {e}")
        sys.exit(1)
