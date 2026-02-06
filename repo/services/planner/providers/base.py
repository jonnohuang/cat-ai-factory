from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class PlannerProvider(ABC):
    @abstractmethod
    def plan(self, prd: Dict[str, Any], inbox: Optional[List[Dict[str, Any]]]) -> Dict[str, Any]:
        """Return a job dict only. Providers must not write files."""
        raise NotImplementedError
