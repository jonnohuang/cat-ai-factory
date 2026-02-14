from __future__ import annotations

import os
import subprocess
import tempfile
from typing import Any, Dict, List, Optional, TypedDict

from .base import BaseProvider
from .gemini_ai_studio import GeminiAIStudioProvider


class PlannerState(TypedDict, total=False):
    prd: Dict[str, Any]
    inbox: List[Dict[str, Any]]
    hero_registry: Optional[Dict[str, Any]]
    job: Dict[str, Any]


class LangGraphDemoProvider(BaseProvider):
    @property
    def name(self) -> str:
        return "langgraph_demo"

    @property
    def default_model(self) -> str:
        return "gemini-1.5-flash"

    def generate_job(
        self,
        prd: Dict[str, Any],
        inbox: Optional[List[Dict[str, Any]]] = None,
        hero_registry: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        try:
            from langgraph.graph import StateGraph, END
        except ImportError as ex:
            raise RuntimeError(
                "LangGraph is not installed. Install with: pip install langgraph"
            ) from ex

        def draft_job(state: PlannerState) -> PlannerState:
            provider = GeminiAIStudioProvider()
            job = provider.generate_job(
                state["prd"],
                state.get("inbox", []),
                hero_registry=state.get("hero_registry"),
            )
            return {"job": job}

        def validate_job(state: PlannerState) -> PlannerState:
            _validate_job(state["job"])
            return {"job": state["job"]}

        graph = StateGraph(PlannerState)
        graph.add_node("draft_job", draft_job)
        graph.add_node("validate_job", validate_job)
        graph.set_entry_point("draft_job")
        graph.add_edge("draft_job", "validate_job")
        graph.add_edge("validate_job", END)
        workflow = graph.compile()

        result = workflow.invoke(
            {
                "prd": prd,
                "inbox": inbox or [],
                "hero_registry": hero_registry,
            }
        )
        return result["job"]


def _repo_root() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.normpath(os.path.join(here, "..", "..", "..", ".."))


def _validate_job(job: Dict[str, Any]) -> None:
    validate_script = os.path.join(_repo_root(), "repo", "tools", "validate_job.py")
    fd, temp_path = tempfile.mkstemp(prefix="planner-validate-", suffix=".job.json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            import json

            json.dump(job, f, indent=2)
            f.write("\n")
        result = subprocess.run(
            ["python3", validate_script, temp_path],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            msg = result.stderr.strip() or result.stdout.strip() or "Job validation failed"
            raise RuntimeError(msg)
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)
