#!/usr/bin/env python3
"""
validate_voice_registry.py

Validates a voice_registry.v1.json against schema and semantic checks.

Usage:
  python -m repo.tools.validate_voice_registry path/to/voice_registry.v1.json
"""

from __future__ import annotations

import json
import pathlib
import re
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


def _semantic_check(data: dict[str, Any], hero_ids: set[str]) -> list[str]:
    errors: list[str] = []
    seen_heroes: set[str] = set()
    seen_voice_keys: set[tuple[str, str]] = set()

    secret_like = re.compile(
        r"(?:^|[_-])(sk|api|token|secret)(?:[_-]|$)", re.IGNORECASE
    )

    for i, row in enumerate(data.get("voices", [])):
        hero_id = row.get("hero_id", "")
        provider = row.get("provider", "")
        voice_id = row.get("voice_id", "")

        if hero_id in seen_heroes:
            errors.append(f"voices[{i}]: duplicate hero_id '{hero_id}'")
        seen_heroes.add(hero_id)

        if hero_id not in hero_ids:
            errors.append(
                f"voices[{i}]: hero_id '{hero_id}' not found in hero_registry.v1.json"
            )

        key = (provider, voice_id)
        if key in seen_voice_keys:
            errors.append(
                f"voices[{i}]: duplicate provider+voice_id combination '{provider}:{voice_id}'"
            )
        seen_voice_keys.add(key)

        if secret_like.search(str(voice_id)):
            errors.append(
                f"voices[{i}]: voice_id appears secret-like; use placeholder-safe identifiers only"
            )

    return errors


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        eprint(
            "Usage: python -m repo.tools.validate_voice_registry path/to/voice_registry.v1.json"
        )
        return 1

    target = pathlib.Path(argv[1]).resolve()
    if not target.exists():
        eprint(f"ERROR: file not found: {target}")
        return 1

    root = _repo_root()
    schema_path = root / "repo" / "shared" / "voice_registry.v1.schema.json"
    heroes_path = root / "repo" / "shared" / "hero_registry.v1.json"

    try:
        schema = _load(schema_path)
        data = _load(target)
        heroes = _load(heroes_path)
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

    hero_ids = {
        h.get("hero_id") for h in heroes.get("heroes", []) if isinstance(h, dict)
    }
    errors = _semantic_check(data, {x for x in hero_ids if isinstance(x, str)})
    if errors:
        eprint(f"SEMANTIC_ERROR: {target}")
        for err in errors:
            eprint(f"- {err}")
        return 1

    print(f"OK: {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
