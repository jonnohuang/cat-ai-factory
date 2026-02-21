#!/usr/bin/env python3
"""
Validates a Cat AI Factory episode_ledger.v1.json against its schema.
Performs semantic checks:
- Schema validation
- Cross-reference check with hero_registry.v1.json (heroes_involved)
- Cross-reference check with series_bible.v1.json (continuity_links)
- Uniqueness checks (episode_id)

Usage:
  python3 repo/tools/validate_episode_ledger.py path/to/ledger.v1.json [path/to/hero_registry.v1.json] [path/to/series_bible.v1.json]

Exit codes:
  0 = valid
  1 = invalid / error
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any, Dict, List, Optional, Set

# Robustly find the repo root
_TOOL_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.normpath(os.path.join(_TOOL_DIR, "..", ".."))

# Add _REPO_ROOT to sys.path
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)


def eprint(*args: Any) -> None:
    print(*args, file=sys.stderr)


# Fail-loud import for jsonschema
try:
    from jsonschema import ValidationError, validate
except ImportError:
    eprint("ERROR: jsonschema not installed.")
    eprint("Please run: pip install jsonschema")
    sys.exit(1)


def load_json(path: str) -> Any:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        eprint(f"ERROR: File not found: {path}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        eprint(f"ERROR: Invalid JSON in {path}: {e}")
        sys.exit(1)
    except Exception as e:
        eprint(f"ERROR: Could not read {path}: {e}")
        sys.exit(1)


def validate_references(
    ledger_data: Dict[str, Any], registry_path: str, bible_path: Optional[str]
) -> bool:
    ok = True

    # 1. Load Registry
    registry_data = load_json(registry_path)

    # Identity check
    if (
        registry_data.get("project") != "Cat AI Factory"
        or registry_data.get("schema") != "hero_registry.v1"
    ):
        eprint(
            f"SEMANTIC_ERROR: Registry at {registry_path} appears to be invalid (wrong project or schema)."
        )
        ok = False

    heroes = registry_data.get("heroes")
    if not isinstance(heroes, list):
        eprint(
            f"ERROR: Invalid registry format in {registry_path}: 'heroes' must be a list"
        )
        return False

    hero_ids: Set[str] = {h.get("hero_id", "") for h in heroes if isinstance(h, dict)}
    hero_ids.discard("")

    # 2. Load Bible if provided
    bible_data = None
    valid_settings = set()
    valid_gags = set()

    if bible_path and os.path.exists(bible_path):
        bible_data = load_json(bible_path)

        # Identity check
        if (
            bible_data.get("project") != "Cat AI Factory"
            or bible_data.get("schema") != "series_bible.v1"
        ):
            eprint(
                f"SEMANTIC_ERROR: Series Bible at {bible_path} appears to be invalid (wrong project or schema)."
            )
            ok = False

        # Pre-compute valid settings w/ shape check
        settings = bible_data.get("settings")
        if not isinstance(settings, list):
            eprint(
                f"ERROR: Invalid bible format in {bible_path}: 'settings' must be a list"
            )
            return False

        valid_settings = {
            s.get("setting_id")
            for s in settings
            if isinstance(s, dict) and s.get("setting_id")
        }

        # Pre-compute valid gags w/ shape check
        gags = bible_data.get("running_gags")
        if not isinstance(gags, list):
            eprint(
                f"ERROR: Invalid bible format in {bible_path}: 'running_gags' must be a list"
            )
            return False

        valid_gags = {
            g.get("gag_id") for g in gags if isinstance(g, dict) and g.get("gag_id")
        }

    elif bible_path:
        eprint(
            f"Warning: Series Bible not found at {bible_path}. Skipping continuity checks."
        )

    # 3. Check Episodes
    episode_ids = set()
    episodes = ledger_data.get("episodes", [])
    if not isinstance(episodes, list):
        eprint("ERROR: Invalid ledger format: 'episodes' must be a list")
        return False

    for i, episode in enumerate(episodes):
        if not isinstance(episode, dict):
            eprint(
                f"SEMANTIC_ERROR: Invalid episode format at index {i}: must be an object"
            )
            ok = False
            continue

        # Unique episode_id
        eid = episode.get("episode_id")
        if eid in episode_ids:
            eprint(f"SEMANTIC_ERROR: duplicate episode_id '{eid}' at episodes[{i}]")
            ok = False
        if eid:
            episode_ids.add(eid)

        # Check heroes_involved
        heroes_involved = episode.get("heroes_involved", [])
        if isinstance(heroes_involved, list):
            for j, hero_ref in enumerate(heroes_involved):
                if not isinstance(hero_ref, str):
                    eprint(
                        f"SEMANTIC_ERROR: episodes[{i}].heroes_involved[{j}] must be a string"
                    )
                    ok = False
                elif hero_ref not in hero_ids:
                    eprint(
                        f"SEMANTIC_ERROR: episodes[{i}].heroes_involved[{j}] '{hero_ref}' not found in registry {registry_path}"
                    )
                    ok = False

        # Check continuity links if bible loaded
        if bible_data and "continuity_links" in episode:
            links = episode["continuity_links"]
            if isinstance(links, dict):
                # Check setting_id
                if "setting_id" in links:
                    setting_ref = links["setting_id"]
                    if setting_ref not in valid_settings:
                        eprint(
                            f"SEMANTIC_ERROR: episodes[{i}].continuity_links.setting_id '{setting_ref}' not found in bible {bible_path}"
                        )
                        ok = False

                # Check gags_used
                if "gags_used" in links:
                    gags = links["gags_used"]
                    if isinstance(gags, list):
                        for k, gag_ref in enumerate(gags):
                            if not isinstance(gag_ref, str):
                                eprint(
                                    f"SEMANTIC_ERROR: episodes[{i}].continuity_links.gags_used[{k}] must be a string"
                                )
                                ok = False
                            elif gag_ref not in valid_gags:
                                eprint(
                                    f"SEMANTIC_ERROR: episodes[{i}].continuity_links.gags_used[{k}] '{gag_ref}' not found in bible {bible_path}"
                                )
                                ok = False

    return ok


def main(argv: List[str]) -> int:
    if len(argv) < 2 or len(argv) > 4:
        eprint(
            "Usage: python3 repo/tools/validate_episode_ledger.py path/to/ledger.v1.json [path/to/hero_registry.v1.json] [path/to/series_bible.v1.json]"
        )
        return 1

    ledger_path = argv[1]

    # Defaults
    if len(argv) >= 3:
        registry_path = argv[2]
    else:
        registry_path = os.path.join(
            _REPO_ROOT, "repo", "shared", "hero_registry.v1.json"
        )

    if len(argv) >= 4:
        bible_path = argv[3]
    else:
        bible_path = os.path.join(_REPO_ROOT, "repo", "shared", "series_bible.v1.json")

    # 1. Load schema
    schema_path = os.path.join(
        _REPO_ROOT, "repo", "shared", "episode_ledger.v1.schema.json"
    )
    schema = load_json(schema_path)

    # 2. Load ledger
    ledger_data = load_json(ledger_path)

    # 3. Validate schema
    try:
        validate(instance=ledger_data, schema=schema)
    except ValidationError as e:
        eprint(f"Schema Validation Error in {ledger_path}:")
        eprint(f"Message: {e.message}")
        if e.path:
            eprint(f"Path: {' -> '.join(str(p) for p in e.path)}")
        else:
            eprint("Path: (root)")
        return 1

    # 4. Validate references
    if not validate_references(ledger_data, registry_path, bible_path):
        eprint(f"Semantic Validation Failed for {ledger_path}")
        return 1

    print(f"OK: {ledger_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
