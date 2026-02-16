from __future__ import annotations

from typing import Dict, List, Type

from .base import BaseProvider
from .gemini_ai_studio import GeminiAIStudioProvider
from .langgraph_demo import LangGraphDemoProvider
from .vertex_ai import VertexImagenProvider, VertexVeoProvider


PROVIDERS: Dict[str, Type[BaseProvider]] = {
    "ai_studio": GeminiAIStudioProvider,
    "langgraph_demo": LangGraphDemoProvider,
    "vertex_veo": VertexVeoProvider,
    "vertex_imagen": VertexImagenProvider,
}


def get_provider(name: str) -> BaseProvider:
    """
    Retrieves an initialized planner provider instance by name.
    """
    provider_cls = PROVIDERS.get(name)
    if provider_cls is None:
        known_providers = ", ".join(PROVIDERS.keys())
        raise ValueError(f"Unknown provider: {name}. Available: {known_providers}")
    return provider_cls()


def list_providers() -> List[str]:
    """Returns a list of available provider names."""
    return sorted(PROVIDERS.keys())
