#!/usr/bin/env python3
"""
validate_style_registry.py

Validates a style_registry.v1.json against schema and semantic checks.

Usage:
  python -m repo.tools.validate_style_registry path/to/style_registry.v1.json
"""
from __future__ import annotations

import json
import pathlib
import sys
from typing import Any

try:
    from jsonschema import ValidationError, validate
except Exception:
    print("ERROR: jsonschema not installed in active environment.", file=sys.stderr)
    raise SystemExit(1)


def eprint(*args: Any) -> None:
    print(*args, file=sys.stderr)


def _repo_root() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parents[2]


def _load(path: pathlib.Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _semantic_check(data: dict[str, Any], costume_ids: set[str]) -> list[str]:
    errors: list[str] = []
    seen_style_ids: set[str] = set()
    seen_refs: set[tuple[str, str]] = set()

    for i, row in enumerate(data.get("styles", [])):
        style_id = row.get("style_id", "")
        provider = row.get("provider", "")
        workflow_ref = row.get("workflow_ref", "")

        if style_id in seen_style_ids:
            errors.append(f"styles[{i}]: duplicate style_id '{style_id}'")
        seen_style_ids.add(style_id)

        key = (provider, workflow_ref)
        if key in seen_refs:
            errors.append(f"styles[{i}]: duplicate provider+workflow_ref '{provider}:{workflow_ref}'")
        seen_refs.add(key)

        for cid in row.get("costume_profile_ids", []):
            if cid not in costume_ids:
                errors.append(f"styles[{i}]: costume_profile_id '{cid}' not found in costume_profiles.v1.json")

    return errors


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        eprint("Usage: python -m repo.tools.validate_style_registry path/to/style_registry.v1.json")
        return 1

    target = pathlib.Path(argv[1]).resolve()
    if not target.exists():
        eprint(f"ERROR: file not found: {target}")
        return 1

    root = _repo_root()
    schema_path = root / "repo" / "shared" / "style_registry.v1.schema.json"
    costume_path = root / "repo" / "shared" / "costume_profiles.v1.json"

    try:
        schema = _load(schema_path)
        data = _load(target)
        costumes = _load(costume_path)
    except Exception as ex:
        eprint(f"ERROR: failed to load JSON input/schema: {ex}")
        return 1

    try:
        validate(instance=data, schema=schema)
    except ValidationError as ex:
        eprint(f"SCHEMA_ERROR: {target}")
        eprint(ex.message)
        if ex.path:
            eprint("Path:", " -> ".join(str(p) for p in ex.path))
        return 1

    costume_ids = {p.get("id") for p in costumes.get("profiles", []) if isinstance(p, dict)}
    errors = _semantic_check(data, {x for x in costume_ids if isinstance(x, str)})
    if errors:
        eprint(f"SEMANTIC_ERROR: {target}")
        for err in errors:
            eprint(f"- {err}")
        return 1

    print(f"OK: {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
