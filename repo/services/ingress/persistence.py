import json
import pathlib
import os
from datetime import datetime, timezone
from abc import ABC, abstractmethod

class PersistenceProvider(ABC):
    @abstractmethod
    def save_request(self, payload: dict) -> str:
        """Persists the request and returns a unique identifier (e.g. filename or document ID)."""
        pass

    @abstractmethod
    def save_control_artifact(self, artifact_type: str, job_id: str, payload: dict) -> str:
        """Persists a control artifact (e.g. approval or publish trigger)."""
        pass

class LocalFilePersistence(PersistenceProvider):
    def __init__(self, sandbox_root: str):
        self.inbox_dir = pathlib.Path(sandbox_root) / "inbox"
        self.inbox_dir.mkdir(parents=True, exist_ok=True)

    def save_request(self, payload: dict) -> str:
        nonce = payload.get("nonce") or os.urandom(4).hex()
        source = payload.get("source", "unknown")
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        
        filename = f"plan-{timestamp}-{source}-{nonce}.json"
        target_path = self.inbox_dir / filename
        
        with open(target_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, sort_keys=True)
            
        return str(target_path)

    def save_control_artifact(self, artifact_type: str, job_id: str, payload: dict) -> str:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        filename = f"control-{artifact_type}-{job_id}-{timestamp}.json"
        target_path = self.inbox_dir / filename

        # Ensure we have the basic fields
        artifact = {
            "type": artifact_type,
            "job_id": job_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "payload": payload
        }
        
        with open(target_path, "w", encoding="utf-8") as f:
            json.dump(artifact, f, indent=2, sort_keys=True)
            
        return str(target_path)

class CloudPersistenceStub(PersistenceProvider):
    """Stub for future Firestore/GCS integration."""
    def save_request(self, payload: dict) -> str:
        print(f"STUB: Saving request to cloud: {payload.get('nonce')}")
        return "stub-cloud-id"

    def save_control_artifact(self, artifact_type: str, job_id: str, payload: dict) -> str:
        print(f"STUB: Saving control artifact {artifact_type} for {job_id} to cloud")
        return f"stub-control-{artifact_type}-id"

def get_persistence() -> PersistenceProvider:
    # Use LocalFilePersistence by default for now, can be switched via env var.
    mode = os.environ.get("CAF_INGRESS_MODE", "local")
    if mode == "cloud":
        return CloudPersistenceStub()
    
    # Default to local
    repo_root = pathlib.Path(__file__).resolve().parents[3]
    return LocalFilePersistence(str(repo_root / "sandbox"))
