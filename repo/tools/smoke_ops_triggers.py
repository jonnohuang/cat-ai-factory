#!/usr/bin/env python3
import json
import os
import sys


def main():
    print("Testing n8n Ops Triggers...")

    # Path to n8n workflows
    repo_root = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )
    workflows_dir = os.path.join(repo_root, "repo", "ops", "n8n")

    required_workflows = ["human_approval_v1.json", "manual_publish_v1.json"]

    for wf in required_workflows:
        wf_path = os.path.join(workflows_dir, wf)
        if not os.path.exists(wf_path):
            print(f"FAIL: Missing workflow {wf}")
            sys.exit(1)

        try:
            with open(wf_path, "r") as f:
                data = json.load(f)
                if not isinstance(data, dict):
                    print(f"FAIL: Workflow {wf} is not a valid JSON object")
                    sys.exit(1)
        except Exception as e:
            print(f"FAIL: Failed to parse workflow {wf}: {e}")
            sys.exit(1)

    print("n8n Ops Triggers smoke test PASSED!")
    sys.exit(0)


if __name__ == "__main__":
    main()
