#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import pathlib
import signal
import socket
import subprocess
import sys
from typing import Optional


def _repo_root() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parents[2]


def _default_comfy_home(root: pathlib.Path) -> pathlib.Path:
    return root / "sandbox" / "third_party" / "ComfyUI"


def _runtime_dir(root: pathlib.Path) -> pathlib.Path:
    return root / "sandbox" / "logs" / "comfyui"


def _pid_path(root: pathlib.Path) -> pathlib.Path:
    return _runtime_dir(root) / "comfyui.pid"


def _log_path(root: pathlib.Path) -> pathlib.Path:
    return _runtime_dir(root) / "comfyui.runtime.log"


def _is_port_open(host: str, port: int, timeout_s: float = 0.5) -> bool:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout_s)
    try:
        s.connect((host, port))
        return True
    except OSError:
        return False
    finally:
        s.close()


def _read_pid(path: pathlib.Path) -> Optional[int]:
    if not path.exists():
        return None
    raw = path.read_text(encoding="utf-8").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _listener_pid(host: str, port: int) -> Optional[int]:
    try:
        proc = subprocess.run(
            ["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN"],
            capture_output=True,
            text=True,
            check=False,
        )
    except Exception:
        return None
    if proc.returncode != 0:
        return None
    lines = [ln for ln in proc.stdout.splitlines() if ln.strip()]
    if len(lines) < 2:
        return None
    for line in lines[1:]:
        parts = line.split()
        if len(parts) < 2:
            continue
        name = parts[0].lower()
        if "python" not in name:
            continue
        try:
            return int(parts[1])
        except ValueError:
            continue
    return None


def _pid_cmdline(pid: int) -> str:
    try:
        proc = subprocess.run(
            ["ps", "-p", str(pid), "-o", "command="],
            capture_output=True,
            text=True,
            check=False,
        )
    except Exception:
        return ""
    if proc.returncode != 0:
        return ""
    return proc.stdout.strip()


def _install_comfy(comfy_home: pathlib.Path) -> int:
    comfy_home.parent.mkdir(parents=True, exist_ok=True)
    if comfy_home.exists():
        print(f"ComfyUI already exists: {comfy_home}")
        return 0
    cmd = ["git", "clone", "https://github.com/comfyanonymous/ComfyUI.git", str(comfy_home)]
    print("Running:", " ".join(cmd))
    rc = subprocess.call(cmd)
    if rc != 0:
        print("ERROR: failed to clone ComfyUI", file=sys.stderr)
        return rc
    print(f"Installed ComfyUI at: {comfy_home}")
    print("Next: run `python3 -m repo.tools.manage_comfy_runtime setup` to install dependencies.")
    return 0


def _setup_comfy(comfy_home: pathlib.Path, python_bin: str) -> int:
    main_py = comfy_home / "main.py"
    if not main_py.exists():
        print(f"ERROR: missing ComfyUI main.py at {main_py}", file=sys.stderr)
        print("Run with `install` first or set COMFYUI_HOME.", file=sys.stderr)
        return 2
    # Build an isolated runtime venv under ComfyUI to avoid PEP668/system Python issues.
    venv_dir = comfy_home / ".venv"
    venv_python = venv_dir / "bin" / "python"
    if not venv_python.exists():
        mkvenv_cmd = [python_bin, "-m", "venv", str(venv_dir)]
        print("Running:", " ".join(mkvenv_cmd))
        rc = subprocess.call(mkvenv_cmd, cwd=str(comfy_home))
        if rc != 0:
            print("ERROR: failed creating ComfyUI venv", file=sys.stderr)
            return rc
    # Upgrade pip inside venv first.
    rc = subprocess.call([str(venv_python), "-m", "pip", "install", "--upgrade", "pip"], cwd=str(comfy_home))
    if rc != 0:
        print("ERROR: failed upgrading pip in ComfyUI venv", file=sys.stderr)
        return rc

    root = _repo_root()
    caf_req = root / "requirements-comfy-runtime.txt"
    req_files = []
    if caf_req.exists():
        req_files.append(caf_req)
    req_files.extend([comfy_home / "requirements.txt", comfy_home / "manager_requirements.txt"])
    seen = set()
    for req in req_files:
        key = str(req.resolve()) if req.exists() else str(req)
        if key in seen:
            continue
        seen.add(key)
        if not req.exists():
            continue
        cmd = [str(venv_python), "-m", "pip", "install", "-r", str(req)]
        print("Running:", " ".join(cmd))
        rc = subprocess.call(cmd, cwd=str(comfy_home))
        if rc != 0:
            print(f"ERROR: failed installing requirements from {req.name}", file=sys.stderr)
            return rc
    print("ComfyUI dependencies installed.")
    print(f"ComfyUI venv python: {venv_python}")
    return 0


def _status(root: pathlib.Path, host: str, port: int) -> int:
    pid_file = _pid_path(root)
    log_file = _log_path(root)
    pid = _read_pid(pid_file)
    port_open = _is_port_open(host, port)
    listen_pid = _listener_pid(host, port) if port_open else None
    pid_alive = _pid_alive(pid) if pid is not None else False
    listener_cmd = _pid_cmdline(listen_pid) if listen_pid is not None else ""
    managed = pid is not None and pid_alive and listen_pid is not None and int(pid) == int(listen_pid)
    unmanaged_listener = listen_pid is not None and not managed
    print(f"comfy_host: {host}")
    print(f"comfy_port: {port}")
    print(f"port_open: {port_open}")
    print(f"runtime_dir: {_runtime_dir(root)}")
    if pid is not None:
        print(f"pid_file: {pid_file}")
        print(f"pid: {pid}")
        print(f"pid_alive: {pid_alive}")
    else:
        print(f"pid_file: {pid_file} (missing)")
    if listen_pid is not None:
        print(f"listener_pid: {listen_pid}")
        if listener_cmd:
            print(f"listener_cmd: {listener_cmd}")
    print(f"managed_listener: {managed}")
    print(f"unmanaged_listener: {unmanaged_listener}")
    print(f"log_path: {log_file}")
    return 0


def _start(
    root: pathlib.Path,
    comfy_home: pathlib.Path,
    host: str,
    port: int,
    python_bin: str,
    extra_args: list[str] | None = None,
) -> int:
    if _is_port_open(host, port):
        print(f"ComfyUI already reachable at http://{host}:{port}")
        return 0

    main_py = comfy_home / "main.py"
    if not main_py.exists():
        print(f"ERROR: missing ComfyUI main.py at {main_py}", file=sys.stderr)
        print("Run with --install first or set COMFYUI_HOME to an existing ComfyUI checkout.", file=sys.stderr)
        return 2

    rdir = _runtime_dir(root)
    rdir.mkdir(parents=True, exist_ok=True)
    log_file = _log_path(root)
    pid_file = _pid_path(root)

    # Prefer non-blocking detached start; logs are persisted to sandbox/logs/comfyui.
    venv_python = comfy_home / ".venv" / "bin" / "python"
    runtime_python = str(venv_python) if venv_python.exists() else python_bin
    cmd = [runtime_python, str(main_py), "--listen", host, "--port", str(port)]
    resolved_extra_args = list(extra_args or [])
    # GPU/MPS-first by default, but auto-fallback to CPU when torch reports no usable accelerator.
    if not resolved_extra_args:
        probe = subprocess.run(  # noqa: S603,S607
            [
                runtime_python,
                "-c",
                (
                    "import torch; "
                    "mps_ok=bool(getattr(torch.backends,'mps',None) and torch.backends.mps.is_available()); "
                    "cuda_ok=bool(torch.cuda.is_available()); "
                    "print('1' if (mps_ok or cuda_ok) else '0')"
                ),
            ],
            cwd=str(comfy_home),
            capture_output=True,
            text=True,
            check=False,
        )
        has_accel = (probe.returncode == 0 and probe.stdout.strip() == "1")
        if not has_accel:
            resolved_extra_args = ["--cpu"]
            print("INFO: No GPU/MPS backend detected; auto-applying CPU fallback (--cpu).")
    if resolved_extra_args:
        cmd.extend(resolved_extra_args)
    print("Starting ComfyUI:", " ".join(cmd))
    with log_file.open("a", encoding="utf-8") as lf:
        proc = subprocess.Popen(  # noqa: S603,S607
            cmd,
            cwd=str(comfy_home),
            stdout=lf,
            stderr=lf,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
            close_fds=True,
        )
    pid_file.write_text(f"{proc.pid}\n", encoding="utf-8")
    print(f"pid: {proc.pid}")

    # short readiness wait
    for _ in range(20):
        if _is_port_open(host, port):
            print(f"OK: ComfyUI listening at http://{host}:{port}")
            return 0
        if proc.poll() is not None:
            print("ERROR: ComfyUI process exited early; recent runtime log tail:", file=sys.stderr)
            try:
                tail = log_file.read_text(encoding="utf-8").splitlines()[-40:]
                for line in tail:
                    print(line, file=sys.stderr)
            except Exception:
                pass
            return 3
        import time
        time.sleep(0.5)

    if proc.poll() is not None:
        print("ERROR: ComfyUI process exited after readiness window; recent runtime log tail:", file=sys.stderr)
        try:
            tail = log_file.read_text(encoding="utf-8").splitlines()[-40:]
            for line in tail:
                print(line, file=sys.stderr)
        except Exception:
            pass
        return 3
    print("WARNING: process started but port not yet open; check runtime log.")
    return 0


def _stop(root: pathlib.Path) -> int:
    pid_file = _pid_path(root)
    pid = _read_pid(pid_file)
    if pid is None:
        print("No pid file; nothing to stop.")
        return 0
    if not _pid_alive(pid):
        print(f"PID {pid} is not alive; cleaning pid file.")
        pid_file.unlink(missing_ok=True)
        return 0
    print(f"Stopping ComfyUI pid={pid}")
    os.kill(pid, signal.SIGTERM)
    pid_file.unlink(missing_ok=True)
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="CAF-managed ComfyUI runtime helper.")
    parser.add_argument("action", choices=["install", "setup", "start", "stop", "status"])
    parser.add_argument("--comfy-home", default=os.environ.get("COMFYUI_HOME", "").strip())
    parser.add_argument("--host", default=os.environ.get("COMFYUI_HOST", "127.0.0.1").strip() or "127.0.0.1")
    parser.add_argument("--port", type=int, default=int(os.environ.get("COMFYUI_PORT", "8188") or 8188))
    parser.add_argument("--python-bin", default=os.environ.get("COMFYUI_PYTHON_BIN", "python3").strip() or "python3")
    parser.add_argument(
        "--extra-args",
        default=os.environ.get("COMFYUI_EXTRA_ARGS", "").strip(),
        help="Optional extra args passed to ComfyUI main.py, e.g. '--cpu'",
    )
    args = parser.parse_args(argv)

    root = _repo_root()
    comfy_home = pathlib.Path(args.comfy_home) if args.comfy_home else _default_comfy_home(root)

    raw_extra_args = (args.extra_args or "").strip()
    # Keep GPU/MPS as default runtime path; only opt into CPU when explicitly requested.
    # Also ignore placeholder values commonly used in .env.example.
    if raw_extra_args.lower() in {"changeme", "placeholder"}:
        raw_extra_args = ""
    extra_args = [tok for tok in (raw_extra_args.split() if raw_extra_args else []) if tok]

    if args.action == "install":
        return _install_comfy(comfy_home)
    if args.action == "setup":
        return _setup_comfy(comfy_home, args.python_bin)
    if args.action == "start":
        return _start(root, comfy_home, args.host, args.port, args.python_bin, extra_args=extra_args)
    if args.action == "stop":
        return _stop(root)
    return _status(root, args.host, args.port)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
