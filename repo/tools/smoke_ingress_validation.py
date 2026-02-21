#!/usr/bin/env python3
import json
import pathlib
import sys
import uuid
from datetime import datetime, timezone

# Add repo root to sys.path
repo_root = pathlib.Path(__file__).resolve().parents[2]
sys.path.append(str(repo_root))

from repo.services.ingress.persistence import LocalFilePersistence

# Try importing jsonschema, or skip if not available
try:
    import jsonschema

    HAS_JSONSCHEMA = True
except ImportError:
    HAS_JSONSCHEMA = False

SCHEMA_PATH = repo_root / "repo" / "shared" / "plan_request.v1.schema.json"


def test_validation():
    print("Testing Ingress Validation...")

    with open(SCHEMA_PATH, "r") as f:
        schema = json.load(f)

    # 1. Valid Payload
    valid_payload = {
        "version": "plan_request.v1",
        "source": "smoke_test",
        "received_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "nonce": "smoke-nonce-123",
        "type": "daily_plan",
        "brief_text": "Mochi dino dancing in the park",
        "lanes": {"a": 1, "b": 1, "c": 1},
    }

    if HAS_JSONSCHEMA:
        try:
            jsonschema.validate(instance=valid_payload, schema=schema)
            print("  [PASS] Valid payload accepted by schema.")
        except jsonschema.ValidationError as e:
            print(f"  [FAIL] Valid payload rejected: {e.message}")
            sys.exit(1)
    else:
        print("  [SKIP] jsonschema not installed, skipping schema validation.")

    # 2. Invalid Payload (missing version)
    invalid_payload = {"source": "smoke_test", "received_at": "invalid-date"}

    if HAS_JSONSCHEMA:
        try:
            jsonschema.validate(instance=invalid_payload, schema=schema)
            print("  [FAIL] Invalid payload accepted by schema.")
            sys.exit(1)
        except jsonschema.ValidationError:
            print("  [PASS] Invalid payload rejected by schema.")

    # 3. Persistence Test
    persistence = LocalFilePersistence(str(repo_root / "sandbox"))
    location = persistence.save_request(valid_payload)

    path = pathlib.Path(location)
    if path.exists():
        print(f"  [PASS] Payload persisted to: {location}")
        # Verify content
        with open(path, "r") as f:
            saved = json.load(f)
        assert saved["nonce"] == "smoke-nonce-123"
        # Cleanup
        path.unlink()
    else:
        print(f"  [FAIL] Payload not persisted to: {location}")
        sys.exit(1)

    print("Ingress validation smoke test PASSED!")


if __name__ == "__main__":
    test_validation()
