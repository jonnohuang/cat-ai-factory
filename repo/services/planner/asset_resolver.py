from __future__ import annotations

import json
import pathlib
from typing import Any, Dict, List, Optional


class AssetResolver:
    def __init__(self, repo_root: pathlib.Path):
        self.repo_root = repo_root
        self.manifest_path = self.repo_root / "repo/shared/asset_manifest.v1.json"
        self._assets: List[Dict[str, Any]] = []
        self._load_manifest()

    def _load_manifest(self):
        if not self.manifest_path.exists():
            return
        try:
            with open(self.manifest_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                self._assets = data.get("assets", [])
        except Exception:
            self._assets = []

    def find_assets(self, tags: List[str], asset_type: Optional[str] = None) -> List[str]:
        """
        Finds assets matching ALL provided tags.
        Returns a list of relative paths sorted by priority (desc) then asset_id.
        """
        matches = []
        search_tags = [t.lower() for t in tags]
        
        for asset in self._assets:
            if asset_type and asset.get("type") != asset_type:
                continue
                
            asset_tags = [t.lower() for t in asset.get("tags", [])]
            if all(t in asset_tags for t in search_tags):
                matches.append(asset)
        
        # Sort by priority (desc), then asset_id (asc)
        matches.sort(key=lambda x: (-x.get("priority", 50), x.get("asset_id", "")))
        
        return [a.get("relpath") for a in matches]

    def resolve_reference_images(self, intent_text: str) -> List[str]:
        """
        Heuristic-based resolution of reference images for a given intent.
        """
        text = intent_text.lower()
        tags = []
        
        if "mochi" in text:
            tags.append("mochi")
        if "dance" in text or "loop" in text:
            tags.append("dance")
            
        if not tags:
            return []
            
        # Find all assets that match at least one of the tags (Union for references)
        # But we sort them together.
        matches = []
        for asset in self._assets:
            if asset.get("type") != "image":
                continue
            asset_tags = [t.lower() for t in asset.get("tags", [])]
            if any(t in asset_tags for t in tags):
                matches.append(asset)
                
        matches.sort(key=lambda x: (-x.get("priority", 50), x.get("asset_id", "")))
        return [a.get("relpath") for a in matches]

    def resolve_background_video(self, intent_text: str) -> Optional[str]:
        """
        Heuristic-based resolution of background video assets.
        """
        text = intent_text.lower()
        if "dance" in text or "loop" in text:
            paths = self.find_assets(["background", "dance"], asset_type="video")
            if paths:
                return paths[0]
        return None
