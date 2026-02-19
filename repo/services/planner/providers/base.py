from __future__ import annotations

import datetime as dt
from abc import ABC, abstractmethod
from typing import Any, Dict, List


def today_utc() -> str:
    """Returns the current UTC date in YYYY-MM-DD format."""
    return dt.datetime.now(dt.timezone.utc).date().isoformat()


def redact_debug(text: str) -> str:
    """Returns a redacted, safe-to-log representation of a string."""
    return f"<redacted len={len(text)}>"


class BaseProvider(ABC):
    """Base class for all planner providers."""

    @property
    @abstractmethod
    def name(self) -> str:
        """The unique name of the provider."""
        raise NotImplementedError

    @property
    @abstractmethod
    def default_model(self) -> str:
        """The default model used by the provider."""
        raise NotImplementedError

    @abstractmethod
    def generate_job(
        self,
        prd: Dict[str, Any],
        inbox: List[Dict[str, Any]] | None = None,
        hero_registry: Dict[str, Any] | None = None,
        quality_context: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        """
        Generates a job dictionary from the given PRD and inbox.

        Args:
            prd: The product definition dictionary.
            inbox: An optional list of inbox message dictionaries.
            hero_registry: Optional reference-only hero registry data (hero_registry.v1).
            quality_context: Optional planner-side quality signals (analyzer/benchmark/manifests).

        Returns:
            A dictionary representing the generated job, ready for validation and writing.
        """
        raise NotImplementedError
