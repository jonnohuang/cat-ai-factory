from __future__ import annotations

from typing import Dict, Type

from .base import PlannerProvider
from .gemini_ai_studio import GeminiAIStudioProvider


PROVIDERS: Dict[str, Type[PlannerProvider]] = {
    "gemini_ai_studio": GeminiAIStudioProvider,
}


def get_provider(name: str) -> PlannerProvider:
    provider_cls = PROVIDERS.get(name)
    if provider_cls is None:
        raise ValueError(f"Unknown provider: {name}")
    return provider_cls()
