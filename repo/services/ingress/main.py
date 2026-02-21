import json
import os
import pathlib
import uuid
from datetime import datetime, timezone
from typing import Optional

import jsonschema
from fastapi import FastAPI, Header, HTTPException, Request, status
from fastapi.responses import JSONResponse

from repo.services.ingress.persistence import get_persistence

app = FastAPI(title="Cat AI Factory Ingress")

# Load schema once
SCHEMA_PATH = (
    pathlib.Path(__file__).resolve().parents[3]
    / "repo"
    / "shared"
    / "plan_request.v1.schema.json"
)
with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
    PLAN_REQUEST_SCHEMA = json.load(f)

# Auth token for simple gateway protection
GATEWAY_TOKEN = os.environ.get("CLAWDBOT_GATEWAY_TOKEN")


# Auth helper
def verify_token(authorization: Optional[str]):
    if GATEWAY_TOKEN and authorization != f"Bearer {GATEWAY_TOKEN}":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid gateway token"
        )


@app.post("/ingress/plan", status_code=status.HTTP_202_ACCEPTED)
async def ingress_plan(request: Request, authorization: Optional[str] = Header(None)):
    verify_token(authorization)

    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON payload"
        )

    # Validate against schema
    try:
        jsonschema.validate(instance=payload, schema=PLAN_REQUEST_SCHEMA)
    except jsonschema.ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Schema validation failed: {e.message}",
        )

    # Ensure received_at is set (or override)
    if not payload.get("received_at"):
        payload["received_at"] = (
            datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        )

    # Generate nonce if missing
    if not payload.get("nonce") and not payload.get("request_id"):
        payload["nonce"] = str(uuid.uuid4())[:8]

    # Persist the request
    persistence = get_persistence()
    location = persistence.save_request(payload)

    return {
        "status": "accepted",
        "job_id": payload.get("request_id") or payload.get("nonce"),
        "location": location,
        "message": "Plan request received and persisted to inbox.",
    }


@app.post("/ops/approve/{job_id}", status_code=status.HTTP_201_CREATED)
async def ops_approve(
    job_id: str, request: Request, authorization: Optional[str] = Header(None)
):
    verify_token(authorization)
    try:
        payload = await request.json()
    except Exception:
        payload = {}

    persistence = get_persistence()
    location = persistence.save_control_artifact("approve", job_id, payload)

    return {"status": "approved", "job_id": job_id, "location": location}


@app.post("/ops/publish/{job_id}", status_code=status.HTTP_201_CREATED)
async def ops_publish(
    job_id: str, request: Request, authorization: Optional[str] = Header(None)
):
    verify_token(authorization)
    try:
        payload = await request.json()
    except Exception:
        payload = {}

    persistence = get_persistence()
    location = persistence.save_control_artifact("publish", job_id, payload)

    return {"status": "published", "job_id": job_id, "location": location}


@app.get("/health")
async def health():
    return {"status": "ok"}
