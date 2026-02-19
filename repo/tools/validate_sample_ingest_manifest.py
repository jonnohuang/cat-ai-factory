#!/usr/bin/env python3
from __future__ import annotations

import json
import pathlib
import sys
from typing import Any

try:
    from jsonschema import ValidationError, validate
except Exception:
    ValidationError = Exception
    validate = None


def _repo_root() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parents[2]


def _load(path: pathlib.Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def eprint(*args: Any) -> None:
    print(*args, file=sys.stderr)


def _validate_required_artifact_classes(data: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["SEMANTIC_ERROR: payload must be object"]
    classes = data.get("artifact_classes")
    if not isinstance(classes, dict):
        return ["SEMANTIC_ERROR: artifact_classes must be object"]
    for name, row in classes.items():
        if not isinstance(row, dict):
            errors.append(f"SEMANTIC_ERROR: artifact_classes.{name} must be object")
            continue
        required = bool(row.get("required"))
        present = bool(row.get("present"))
        evidence = row.get("evidence", [])
        if required and not present:
            errors.append(f"SEMANTIC_ERROR: required artifact class missing: {name}")
        if present and (not isinstance(evidence, list) or len(evidence) == 0):
            errors.append(f"SEMANTIC_ERROR: present artifact class must include evidence: {name}")
    return errors


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        eprint("Usage: python -m repo.tools.validate_sample_ingest_manifest path/to/sample_ingest_manifest.v1.json")
        return 1
    target = pathlib.Path(argv[1]).resolve()
    if not target.exists():
        eprint(f"ERROR: file not found: {target}")
        return 1

    root = _repo_root()
    schema = _load(root / "repo" / "shared" / "sample_ingest_manifest.v1.schema.json")
    data = _load(target)
    if validate is not None:
        try:
            validate(instance=data, schema=schema)
        except ValidationError as ex:
            eprint(f"SCHEMA_ERROR: {ex.message}")
            return 1
    elif not isinstance(data, dict):
        eprint("SEMANTIC_ERROR: payload must be object")
        return 1
    semantic_errors = _validate_required_artifact_classes(data)
    if semantic_errors:
        for err in semantic_errors:
            eprint(err)
        return 1
    print(f"OK: {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
