from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import traceback
from typing import Any, Dict, List, Optional, TypedDict

from ..util.json_extract import extract_json_object
from .base import BaseProvider
from .gemini_ai_studio import GeminiAIStudioProvider


class PlannerState(TypedDict, total=False):
    prd: Dict[str, Any]
    inbox: List[Dict[str, Any]]
    hero_registry: Optional[Dict[str, Any]]
    quality_context: Optional[Dict[str, Any]]
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
        quality_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        # NOTE: LangGraph is currently incompatible with Python 3.14 in this environment.
        # Fallback to procedural "Lightweight Graphite" execution to maintain narrative logic.
        using_langgraph = False
        try:
            from langgraph.graph import END, StateGraph
            using_langgraph = True
        except Exception:
             # SILENT FALLBACK: Log to stderr or similar if diagnostic mode enabled
             pass

        def select_vpl(state: PlannerState) -> PlannerState:
            vpl_index_path = os.path.join(_repo_root(), "repo", "canon", "viral_patterns", "vpl_index.v1.json")
            if not os.path.exists(vpl_index_path):
                return {"viral_pattern_id": "none"}

            with open(vpl_index_path, "r", encoding="utf-8") as f:
                index = json.load(f)

            prd_tags = state["prd"].get("tags", [])
            selected_id = "dance_loop_v1" # Default for demo
            for pattern in index.get("patterns", []):
                if any(tag in pattern.get("tags", []) for tag in prd_tags):
                    selected_id = pattern["pattern_id"]
                    break

            return {"viral_pattern_id": selected_id}

        def story_agent(state: PlannerState) -> PlannerState:
            vpl_id = state.get("viral_pattern_id", "none")
            storyline = {
                "version": "storyline.v1",
                "vpl_id": vpl_id,
                "arc": "Hook -> Build -> Loop -> Outro",
                "emotional_pacing": "Exciting -> High Energy"
            }
            storyboard = {
                "version": "storyboard.v1",
                "job_id": state["prd"].get("job_id", "demo_job"),
                "frames": [
                    {
                        "shot_id": "shot_001",
                        "anchor_id": "mochi-stabilized",
                        "image_asset": "assets/mochi_hero.png",
                        "prompt": f"Mochi dancing according to {vpl_id} pattern.",
                        "duration_sec": 8.0
                    }
                ]
            }
            return {"storyline": storyline, "storyboard": storyboard}

        def viral_optimizer(state: PlannerState) -> PlannerState:
            vpl_id = state.get("viral_pattern_id", "none")
            hook_plan = {
                "version": "hook_plan.v1",
                "vpl_id": vpl_id,
                "hook_type": "zoom_punch",
                "alignment_sec": 0.5
            }
            loop_plan = {
                "version": "loop_plan.v1",
                "vpl_id": vpl_id,
                "seam_strategy": "pose_match"
            }
            return {"hook_plan": hook_plan, "loop_plan": loop_plan}

        def draft_job(state: PlannerState) -> PlannerState:
            enriched_prd = state["prd"].copy()
            enriched_prd["story_context"] = {
                "vpl_id": state.get("viral_pattern_id"),
                "storyline": state.get("storyline"),
                "hook_plan": state.get("hook_plan")
            }

            provider = GeminiAIStudioProvider()
            job = provider.generate_job(
                enriched_prd,
                state.get("inbox", []),
                hero_registry=state.get("hero_registry"),
                quality_context=state.get("quality_context"),
            )
            job.setdefault("metadata", {})
            job["metadata"]["viral_pattern_id"] = state.get("viral_pattern_id")
            job["metadata"]["hook_plan_v1"] = state.get("hook_plan")
            return {"job": job}


        def crewai_refine(state: PlannerState) -> PlannerState:
            if os.environ.get("CREWAI_ENABLED", "0") != "1":
                return {"job": state["job"]}

            try:
                from crewai import Agent, Crew, Process, Task
                from langchain_google_genai import ChatGoogleGenerativeAI
            except ImportError as ex:
                raise RuntimeError(
                    "CrewAI or langchain_google_genai is not installed. Install with: pip install crewai langchain-google-genai"
                ) from ex

            api_key = os.environ.get("GEMINI_API_KEY")
            if not api_key:
                raise ValueError(
                    "GEMINI_API_KEY is required for CrewAI refinement step"
                )

            # Configure Gemini LLM
            model_name = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
            llm = ChatGoogleGenerativeAI(
                model=model_name, google_api_key=api_key, temperature=0.0
            )

            prompt = _build_crewai_prompt(
                state["prd"],
                state.get("inbox", []),
                state.get("hero_registry"),
                state["job"],
            )

            agent = Agent(
                role="Planner Refiner",
                goal="Refine the draft into a strict JSON job object that passes schema validation.",
                backstory="You are a planner-only refinement step. Return JSON only.",
                allow_delegation=False,
                verbose=False,
                llm=llm,
            )
            task = Task(
                description=prompt,
                agent=agent,
                expected_output="A single JSON object that conforms to the job schema.",
            )
            crew = Crew(
                agents=[agent], tasks=[task], process=Process.sequential, verbose=False
            )
            result = crew.kickoff()
            text = result.raw if hasattr(result, "raw") else str(result)
            job = extract_json_object(text)
            return {"job": job}

        def validate_job(state: PlannerState) -> PlannerState:
            job = _normalize_job(state["job"])
            _validate_job(job)
            return {"job": job}

        initial_state: PlannerState = {
            "prd": prd,
            "inbox": inbox or [],
            "hero_registry": hero_registry,
            "quality_context": quality_context,
        }

        if using_langgraph:
            graph = StateGraph(PlannerState)
            graph.add_node("select_vpl", select_vpl)
            graph.add_node("story_agent", story_agent)
            graph.add_node("viral_optimizer", viral_optimizer)
            graph.add_node("draft_job", draft_job)
            graph.add_node("crewai_refine", crewai_refine)
            graph.add_node("validate_job", validate_job)

            graph.set_entry_point("select_vpl")
            graph.add_edge("select_vpl", "story_agent")
            graph.add_edge("story_agent", "viral_optimizer")
            graph.add_edge("viral_optimizer", "draft_job")
            graph.add_edge("draft_job", "crewai_refine")
            graph.add_edge("crewai_refine", "validate_job")
            graph.add_edge("validate_job", END)
            workflow = graph.compile()
            result = workflow.invoke(initial_state)
        else:
            # Procedural Fallback Sequence
            state = initial_state.copy()
            state.update(select_vpl(state))
            state.update(story_agent(state))
            state.update(viral_optimizer(state))
            state.update(draft_job(state))
            state.update(crewai_refine(state))
            state.update(validate_job(state))
            result = state

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
            msg = (
                result.stderr.strip()
                or result.stdout.strip()
                or "Job validation failed"
            )
            raise RuntimeError(msg)
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)


def _build_crewai_prompt(
    prd: Dict[str, Any],
    inbox: List[Dict[str, Any]],
    hero_registry: Optional[Dict[str, Any]],
    draft_job: Dict[str, Any],
) -> str:
    prd_json = json.dumps(prd, indent=None, separators=(",", ":"), ensure_ascii=True)
    inbox_json = json.dumps(
        inbox, indent=None, separators=(",", ":"), ensure_ascii=True
    )
    draft_json = json.dumps(
        draft_job, indent=None, separators=(",", ":"), ensure_ascii=True
    )
    registry_context = ""
    if hero_registry:
        registry_json = json.dumps(
            hero_registry, indent=None, separators=(",", ":"), ensure_ascii=True
        )
        registry_context = (
            "Hero Registry (Reference):\n"
            f"{registry_json}\n"
            "Use only existing hero ids. Do not invent new heroes.\n\n"
        )
    rules = (
        "Return ONLY a single JSON object. No markdown, no code fences, no commentary.\n"
        "Keep top-level keys required by job schema: job_id, date, niche, video, script, shots, captions, hashtags, render.\n"
        "Ensure the JSON validates against the job schema. If unsure, minimally adjust values.\n"
        "Shots[].t must be an integer between 0 and 60. If you would output a decimal, round to the nearest int.\n"
    )
    return (
        "You are a planner-only refinement step for Cat AI Factory.\n"
        f"{rules}\n"
        f"{registry_context}"
        f"PRD JSON:\n{prd_json}\n\n"
        f"Inbox JSON list:\n{inbox_json}\n\n"
        f"Draft job JSON (to refine):\n{draft_json}\n"
    )


def _normalize_job(job: Dict[str, Any]) -> Dict[str, Any]:
    shots = job.get("shots")
    if not isinstance(shots, list):
        return job
    for shot in shots:
        if not isinstance(shot, dict):
            continue
        t = shot.get("t")
        if isinstance(t, float):
            t_int = int(round(t))
            if t_int < 0:
                t_int = 0
            if t_int > 60:
                t_int = 60
            shot["t"] = t_int
    return job
