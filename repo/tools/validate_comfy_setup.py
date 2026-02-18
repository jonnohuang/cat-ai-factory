#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import pathlib
import shutil
import sys
import urllib.error
import urllib.request
from typing import Any, Dict


def _repo_root() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parents[2]


def _http_json(url: str, *, method: str = "GET", payload: Dict[str, Any] | None = None) -> Dict[str, Any]:
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url=url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as ex:
        body = ""
        try:
            body = ex.read().decode("utf-8", errors="replace")
        except Exception:
            body = ""
        detail = f"HTTP {ex.code}"
        if body:
            detail = f"{detail} body={body}"
        raise RuntimeError(detail) from ex
    obj = json.loads(raw)
    if not isinstance(obj, dict):
        raise RuntimeError("non-object JSON response")
    return obj


def _load_workflow(path: pathlib.Path) -> Dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise RuntimeError("workflow JSON must be an object")
    if isinstance(raw.get("prompt_api"), dict):
        return raw["prompt_api"]
    if isinstance(raw.get("nodes"), dict):
        return raw["nodes"]
    # Accept direct Comfy prompt JSON too.
    return raw


def _inject_seed_image(graph: Dict[str, Any]) -> None:
    comfy_home_s = os.environ.get("COMFYUI_HOME", "").strip()
    comfy_home = pathlib.Path(comfy_home_s) if comfy_home_s else (_repo_root() / "sandbox" / "third_party" / "ComfyUI")
    input_dir = comfy_home / "input"
    input_dir.mkdir(parents=True, exist_ok=True)
    seed_name = "caf_seed_input.png"
    seed_path = input_dir / seed_name
    if not seed_path.exists():
        fallback = _repo_root() / "repo" / "assets" / "watermarks" / "caf-watermark.png"
        if fallback.exists():
            shutil.copy2(fallback, seed_path)

    for node in graph.values():
        if not isinstance(node, dict):
            continue
        cls = str(node.get("class_type", "")).strip()
        if cls == "CheckpointLoaderSimple":
            inputs = node.get("inputs")
            if isinstance(inputs, dict) and str(inputs.get("ckpt_name", "")).strip() == "__CAF_CHECKPOINT__":
                # Derive first available checkpoint from object_info when possible.
                ckpt = os.environ.get("COMFYUI_CHECKPOINT_NAME", "").strip()
                if not ckpt:
                    try:
                        info = _http_json(f"{os.environ.get('COMFYUI_BASE_URL','').rstrip('/')}/object_info")
                        req = (((info.get("CheckpointLoaderSimple") or {}).get("input") or {}).get("required") or {}).get("ckpt_name")
                        if isinstance(req, list) and req and isinstance(req[0], list) and req[0]:
                            ckpt = str(req[0][0])
                    except Exception:
                        ckpt = ""
                if ckpt:
                    inputs["ckpt_name"] = ckpt
            continue
        if cls != "LoadImage":
            continue
        inputs = node.get("inputs")
        if not isinstance(inputs, dict):
            continue
        image_tag = str(inputs.get("image", "")).strip()
        if image_tag in {"__CAF_SEED_IMAGE__", "__CAF_FRAME_IMAGE__"}:
            inputs["image"] = seed_name
            inputs["upload"] = "image"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Validate ComfyUI API reachability and CAF workflow wiring.")
    parser.add_argument("--base-url", default=os.environ.get("COMFYUI_BASE_URL", "").strip())
    parser.add_argument("--workflow-id", default=os.environ.get("COMFYUI_WORKFLOW_ID", "").strip())
    parser.add_argument("--workflow-path", default="", help="Optional explicit workflow file path")
    parser.add_argument(
        "--require-nodes",
        default="input_prompt,input_negative_prompt,sampler",
        help="Comma-separated node ids required by CAF bindings",
    )
    parser.add_argument("--check-submit", action="store_true", help="Submit workflow to /prompt for runtime validation")
    args = parser.parse_args(argv)

    ok = True

    base_url = args.base_url.rstrip("/")
    if not base_url:
        print("ERROR: missing COMFYUI_BASE_URL (or --base-url)", file=sys.stderr)
        return 1
    os.environ["COMFYUI_BASE_URL"] = base_url

    workflow_path: pathlib.Path
    if args.workflow_path.strip():
        workflow_path = pathlib.Path(args.workflow_path.strip())
    else:
        workflow_id = args.workflow_id.strip() or "caf_dance_loop_v1"
        workflow_path = _repo_root() / "repo" / "workflows" / "comfy" / f"{workflow_id}.json"

    print(f"base_url: {base_url}")
    print(f"workflow_path: {workflow_path}")

    if not workflow_path.exists():
        print(f"ERROR: workflow file not found: {workflow_path}", file=sys.stderr)
        return 1

    try:
        graph = _load_workflow(workflow_path)
    except Exception as ex:
        print(f"ERROR: invalid workflow JSON: {ex}", file=sys.stderr)
        return 1

    if not isinstance(graph, dict) or not graph:
        print("ERROR: workflow graph is empty", file=sys.stderr)
        return 1

    required = [x.strip() for x in args.require_nodes.split(",") if x.strip()]
    missing = [node_id for node_id in required if node_id not in graph]
    if missing:
        print(f"ERROR: workflow missing required node ids: {missing}", file=sys.stderr)
        ok = False
    else:
        print(f"OK: required nodes present: {required}")

    try:
        stats = _http_json(f"{base_url}/system_stats")
        print("OK: ComfyUI API reachable (/system_stats)")
        # Keep output brief and deterministic.
        if isinstance(stats.get("system"), dict):
            vram_state = stats["system"].get("vram_state")
            if vram_state is not None:
                print(f"info: vram_state={vram_state}")
    except urllib.error.URLError as ex:
        print(f"ERROR: ComfyUI API unreachable: {ex}", file=sys.stderr)
        ok = False
    except Exception as ex:
        print(f"ERROR: /system_stats check failed: {ex}", file=sys.stderr)
        ok = False

    if args.check_submit:
        try:
            submit_graph = json.loads(json.dumps(graph))
            if isinstance(submit_graph, dict):
                _inject_seed_image(submit_graph)
                # Explicit preflight: fail early with clear message when no checkpoints are installed.
                info = _http_json(f"{base_url}/object_info")
                req = (((info.get("CheckpointLoaderSimple") or {}).get("input") or {}).get("required") or {}).get("ckpt_name")
                ckpts = req[0] if isinstance(req, list) and req and isinstance(req[0], list) else []
                if "__CAF_CHECKPOINT__" in json.dumps(submit_graph) and not ckpts:
                    print(
                        "ERROR: motion workflow requires checkpoint model(s) in "
                        "ComfyUI/models/checkpoints (none found).",
                        file=sys.stderr,
                    )
                    return 2
            resp = _http_json(
                f"{base_url}/prompt",
                method="POST",
                payload={"client_id": "caf-validate", "prompt": submit_graph},
            )
            prompt_id = resp.get("prompt_id")
            if isinstance(prompt_id, str) and prompt_id.strip():
                print(f"OK: /prompt accepted workflow prompt_id={prompt_id}")
            else:
                print("ERROR: /prompt response missing prompt_id", file=sys.stderr)
                ok = False
        except Exception as ex:
            print(f"ERROR: /prompt submit failed: {ex}", file=sys.stderr)
            ok = False

    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
