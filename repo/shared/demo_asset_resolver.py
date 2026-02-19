from __future__ import annotations

import pathlib
from typing import Iterable, Optional

# Canonical candidate orders for deterministic demo asset resolution.
DANCE_LOOP_CANDIDATES: tuple[str, ...] = (
    "assets/demo/processed/dance_loop.mp4",
    "assets/demo/dance_loop.mp4",
)

FIGHT_COMPOSITE_ALIASES: tuple[str, ...] = (
    "assets/demo/fight_composite.mp4",
    "assets/demo/processed/fight_composite.mp4",
    "assets/demo/flight_composite.mp4",
    "assets/demo/processed/flight_composite.mp4",
)

GENERAL_BACKGROUND_CANDIDATES: tuple[str, ...] = (
    *DANCE_LOOP_CANDIDATES,
    *FIGHT_COMPOSITE_ALIASES,
)


def _normalize_relpath(relpath: str) -> str:
    p = relpath.strip().replace("\\", "/")
    if p.startswith("sandbox/"):
        p = p[len("sandbox/") :]
    return p


def _exists_under_sandbox(sandbox_root: pathlib.Path, relpath: str) -> bool:
    p = sandbox_root / _normalize_relpath(relpath)
    return p.exists() and p.is_file()


def resolve_first_existing(
    *,
    sandbox_root: pathlib.Path,
    candidates: Iterable[str],
) -> Optional[str]:
    for rel in candidates:
        norm = _normalize_relpath(rel)
        if _exists_under_sandbox(sandbox_root, norm):
            return norm
    return None


def resolve_alias_for_existing(
    *,
    sandbox_root: pathlib.Path,
    relpath: str,
) -> Optional[str]:
    norm = _normalize_relpath(relpath)
    if _exists_under_sandbox(sandbox_root, norm):
        return norm
    if norm in FIGHT_COMPOSITE_ALIASES:
        return resolve_first_existing(
            sandbox_root=sandbox_root,
            candidates=FIGHT_COMPOSITE_ALIASES,
        )
    return None
