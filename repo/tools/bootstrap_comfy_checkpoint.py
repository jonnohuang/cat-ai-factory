#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import pathlib
import sys
import urllib.request


def _repo_root() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parents[2]


def _default_comfy_home(root: pathlib.Path) -> pathlib.Path:
    return root / "sandbox" / "third_party" / "ComfyUI"


def _download(url: str, dst: pathlib.Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_suffix(dst.suffix + ".part")
    req = urllib.request.Request(url=url, method="GET")
    with urllib.request.urlopen(req, timeout=120) as resp, tmp.open("wb") as f:
        while True:
            chunk = resp.read(1024 * 1024)
            if not chunk:
                break
            f.write(chunk)
    tmp.replace(dst)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Download a checkpoint model into ComfyUI/models/checkpoints."
    )
    parser.add_argument("--url", default=os.environ.get("COMFYUI_CHECKPOINT_URL", "").strip())
    parser.add_argument(
        "--filename",
        default=os.environ.get("COMFYUI_CHECKPOINT_NAME", "").strip(),
        help="Target checkpoint filename (e.g. model.safetensors).",
    )
    parser.add_argument("--comfy-home", default=os.environ.get("COMFYUI_HOME", "").strip())
    args = parser.parse_args(argv)

    if not args.url:
        print("ERROR: --url or COMFYUI_CHECKPOINT_URL is required", file=sys.stderr)
        return 2

    root = _repo_root()
    comfy_home = pathlib.Path(args.comfy_home) if args.comfy_home else _default_comfy_home(root)
    if args.filename:
        filename = args.filename
    else:
        filename = pathlib.Path(args.url.split("?", 1)[0]).name
        if not filename:
            print("ERROR: cannot infer filename from URL; provide --filename", file=sys.stderr)
            return 2

    dst = comfy_home / "models" / "checkpoints" / filename
    print(f"Downloading checkpoint to: {dst}")
    try:
        _download(args.url, dst)
    except Exception as ex:
        print(f"ERROR: checkpoint download failed: {ex}", file=sys.stderr)
        return 1
    print(f"OK: downloaded {dst}")
    print("Next: restart ComfyUI and run validate_comfy_setup --check-submit")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

