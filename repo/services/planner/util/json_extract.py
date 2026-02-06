from __future__ import annotations

import json
from typing import Any, Dict


def _strip_code_fences(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()
    return stripped


def extract_json_object(text: str) -> Dict[str, Any]:
    cleaned = _strip_code_fences(text)
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end == -1:
        raise ValueError("Truncated JSON: missing closing brace")
    snippet = cleaned[start : end + 1]
    snippet = "".join(ch for ch in snippet if ch >= " " or ch in "\n\r\t")

    # Defensive cleanup: remove NULs that can break json.loads
    snippet = snippet.replace("\u0000", "")

    try:
        obj = json.loads(snippet)
    except json.JSONDecodeError as ex:
        raise ValueError(f"Invalid JSON object: {ex}") from ex
    if not isinstance(obj, dict):
        raise ValueError("Top-level JSON value must be an object")
    return obj
