#!/usr/bin/env python3
import sys
import json
import os
import re
import argparse
from jsonschema import validate, ValidationError

# Secret guard patterns
SECRET_PATTERNS = [
    r"api_key", r"token", r"cookie", r"authorization", 
    r"secret", r"password", r"bearer"
]
SECRET_REGEX = re.compile("|".join(SECRET_PATTERNS), re.IGNORECASE)

def scan_for_secrets(data, path=""):
    """Recursively scan keys for secret patterns."""
    if isinstance(data, dict):
        for key, value in data.items():
            current_path = f"{path}.{key}" if path else key
            if SECRET_REGEX.search(key):
                print(f"SECURITY ERROR: Potential secret found in key: {current_path}")
                return True
            if scan_for_secrets(value, current_path):
                return True
    elif isinstance(data, list):
        for i, item in enumerate(data):
            current_path = f"{path}[{i}]"
            if scan_for_secrets(item, current_path):
                return True
    return False

def check_lineage(data, filepath):
    """Verify job_id matches parent directory name."""
    job_id = data.get("job_id")
    if not job_id:
        return False
        
    parent_dir = os.path.basename(os.path.dirname(os.path.abspath(filepath)))
    if job_id != parent_dir:
        print(f"LINEAGE ERROR: job_id '{job_id}' does not match parent directory '{parent_dir}'")
        return False
    return True

def check_semantic_rules(data):
    """Check semantic rules (e.g. duplicate clip IDs)."""
    has_error = False
    platforms = data.get("platform_plans", {})
    
    for platform, plan in platforms.items():
        clip_ids = set()
        for i, clip in enumerate(plan.get("clips", [])):
            cid = clip.get("id")
            if cid:
                if cid in clip_ids:
                    print(f"SEMANTIC ERROR: Duplicate clip id '{cid}' in platform '{platform}'")
                    has_error = True
                clip_ids.add(cid)
    
    return not has_error

def main():
    parser = argparse.ArgumentParser(description="Validate publish_plan.json")
    parser.add_argument("file", help="Path to publish_plan.json")
    args = parser.parse_args()
    
    try:
        with open(args.file, 'r') as f:
            data = json.load(f)
    except Exception as e:
        print(f"JSON ERROR: {e}")
        sys.exit(1)
        
    # 1. Secret Guard
    if scan_for_secrets(data):
        sys.exit(1)
        
    # 2. Schema Validation
    schema_path = os.path.join(os.path.dirname(__file__), "../shared/publish_plan.schema.json")
    try:
        with open(schema_path, 'r') as f:
            schema = json.load(f)
        validate(instance=data, schema=schema)
    except ValidationError as e:
        print(f"SCHEMA ERROR: {e.message} at path {e.json_path}")
        sys.exit(1)
    except Exception as e:
        print(f"SCHEMA LOAD ERROR: {e}")
        sys.exit(1)
        
    # 3. Lineage Check
    if not check_lineage(data, args.file):
        sys.exit(1)

    # 4. Semantic Checks
    if not check_semantic_rules(data):
        sys.exit(1)
        
    print("VALID: publish_plan.json is compliant.")
    sys.exit(0)

if __name__ == "__main__":
    main()
