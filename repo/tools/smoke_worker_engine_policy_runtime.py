#!/usr/bin/env python3
from __future__ import annotations

import sys

from repo.worker.render_ffmpeg import build_engine_policy_runtime


def main(argv: list[str]) -> int:
    _ = argv
    job = {
        "generation_policy": {
            "route_mode": "production",
            "selected_video_provider": "vertex_veo",
            "selected_frame_provider": "grok_image",
            "motion_constraints": ["openpose_constraint"],
            "post_process_order": ["rife_film_post", "esrgan_selective_post"],
        }
    }
    retry_hook = {
        "provider_switch": {
            "mode": "video_provider",
            "current_provider": "vertex_veo",
            "next_provider": "wan_dashscope",
            "provider_order_index": 1,
        }
    }
    out = build_engine_policy_runtime(job=job, retry_hook=retry_hook)
    if not isinstance(out, dict):
        print("ERROR: expected engine policy runtime object", file=sys.stderr)
        return 1
    motion = out.get("motion_constraints")
    post = out.get("post_process_order")
    if not isinstance(motion, list) or len(motion) != 1:
        print("ERROR: motion constraints runtime projection invalid", file=sys.stderr)
        return 1
    if not isinstance(post, list) or len(post) != 2:
        print("ERROR: post process runtime projection invalid", file=sys.stderr)
        return 1
    if out.get("retry_provider_switch", {}).get("next_provider") != "wan_dashscope":
        print("ERROR: retry provider switch projection missing", file=sys.stderr)
        return 1
    print("OK: worker engine policy runtime smoke")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

