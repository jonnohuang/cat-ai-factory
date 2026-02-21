#!/usr/bin/env python3
"""Minimal Cloud Run HTTP stub for orchestrator trigger (PR-24)."""

from __future__ import annotations

import argparse
import json
import os
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict


def _json_response(
    handler: BaseHTTPRequestHandler, code: int, payload: Dict[str, Any]
) -> None:
    body = json.dumps(payload, sort_keys=True).encode("utf-8")
    handler.send_response(code)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _read_json(handler: BaseHTTPRequestHandler) -> Dict[str, Any]:
    raw_len = handler.headers.get("Content-Length", "0")
    try:
        length = int(raw_len)
    except ValueError:
        raise ValueError("invalid Content-Length")
    if length <= 0:
        raise ValueError("request body required")
    raw = handler.rfile.read(length)
    try:
        payload = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise ValueError(f"invalid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("JSON body must be an object")
    return payload


def _validate_trigger_payload(payload: Dict[str, Any]) -> str:
    job_id = payload.get("job_id")
    if not isinstance(job_id, str) or not job_id.strip():
        raise ValueError("field 'job_id' is required and must be a non-empty string")
    return job_id


class _Handler(BaseHTTPRequestHandler):
    server_version = "caf-orchestrator-stub/1.0"

    def do_GET(self) -> None:  # noqa: N802
        if self.path in ("/", "/healthz"):
            _json_response(
                self,
                HTTPStatus.OK,
                {
                    "ok": True,
                    "service": "orchestrator",
                    "stub": True,
                    "message": "Cloud Run stub healthy",
                },
            )
            return
        _json_response(self, HTTPStatus.NOT_FOUND, {"ok": False, "error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/trigger":
            _json_response(
                self, HTTPStatus.NOT_FOUND, {"ok": False, "error": "not found"}
            )
            return
        try:
            payload = _read_json(self)
            job_id = _validate_trigger_payload(payload)
        except ValueError as exc:
            _json_response(  # bad input must fail loud and deterministic
                self, HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)}
            )
            return

        _json_response(
            self,
            HTTPStatus.ACCEPTED,
            {
                "ok": True,
                "stub": True,
                "service": "orchestrator",
                "action": "trigger",
                "job_id": job_id,
                "message": "Accepted by stub. No orchestration executed.",
            },
        )

    def log_message(self, fmt: str, *args: Any) -> None:
        # Keep logs terse and deterministic for local stub usage.
        return


def main() -> int:
    parser = argparse.ArgumentParser(description="Cloud Run orchestrator HTTP stub.")
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("PORT", "8080")),
        help="HTTP port (default: PORT env or 8080)",
    )
    args = parser.parse_args()

    server = ThreadingHTTPServer(("0.0.0.0", args.port), _Handler)
    print(f"orchestrator stub listening on :{args.port}")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
