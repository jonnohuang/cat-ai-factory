"""
hero_registry_validate.py

Shared validation logic for the Hero Registry.
Used by:
- repo/tools/validate_hero_registry.py (CLI)
- repo/services/planner/planner_cli.py (Planner Service)
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Tuple


def load_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def validate_with_jsonschema(
    data: Dict[str, Any], schema: Dict[str, Any]
) -> Tuple[bool, List[str]]:
    """
    Full validation using jsonschema if available.
    Returns (True, []) or (False, [error_messages]).
    """
    try:
        import jsonschema  # type: ignore
        from jsonschema.exceptions import ValidationError
    except ImportError:
        # Proceed with semantic checks only if jsonschema is missing
        return True, []

    try:
        jsonschema.validate(instance=data, schema=schema)
        return True, []
    except ValidationError as e:
        # Format a friendly error message
        path = " -> ".join(str(p) for p in e.path) if e.path else "root"
        msg = f"Schema validation failed at '{path}': {e.message}"
        return False, [msg]
    except Exception as ex:
        return False, [f"Unexpected validation error: {str(ex)}"]


def semantic_checks(registry: Dict[str, Any]) -> List[str]:
    """Perform extra semantic checks (uniqueness, etc)."""
    errors: List[str] = []

    heroes = registry.get("heroes")
    if not isinstance(heroes, list):
        return errors

    seen_ids: Dict[str, int] = {}
    for i, hero in enumerate(heroes):
        if not isinstance(hero, dict):
            continue

        hid = hero.get("hero_id")
        if not isinstance(hid, str):
            continue

        if hid in seen_ids:
            first_idx = seen_ids[hid]
            errors.append(
                f"Duplicate hero_id '{hid}' at heroes[{i}] (already seen at heroes[{first_idx}])"
            )
        else:
            seen_ids[hid] = i

    return errors


def validate_registry_data(
    registry: Dict[str, Any], schema: Dict[str, Any]
) -> Tuple[bool, List[str]]:
    """
    Validates registry data against schema data.
    Returns (True, []) on success, or (False, [errors]) on failure.
    """
    errors = []

    # Schema Validation
    ok, schema_errors = validate_with_jsonschema(registry, schema)
    if not ok:
        errors.extend(schema_errors)

    # Semantic Checks
    sem_errors = semantic_checks(registry)
    errors.extend(sem_errors)

    return (len(errors) == 0), errors


def validate_registry_file(
    registry_path: str, schema_path: str
) -> Tuple[bool, List[str]]:
    """
    Validates a registry file against a schema file.
    Returns (True, []) on success, or (False, [errors]) on failure.
    """
    if not os.path.exists(registry_path):
        return False, [f"Registry file not found: {registry_path}"]
    if not os.path.exists(schema_path):
        return False, [f"Schema file not found: {schema_path}"]

    try:
        registry = load_json(registry_path)
    except Exception as ex:
        return False, [f"Failed to parse registry JSON: {ex}"]

    try:
        schema = load_json(schema_path)
    except Exception as ex:
        return False, [f"Failed to parse schema JSON: {ex}"]

    return validate_registry_data(registry, schema)
