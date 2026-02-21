#!/usr/bin/env python3
import pathlib
import subprocess
import sys
import time

# repo/tools/test_harness.py -> <repo_root>
repo_root = pathlib.Path(__file__).resolve().parents[2]

TESTS = [
    ("Hero Registry Validation", ["python3", "repo/shared/hero_registry_validate.py"]),
    ("Asset RAG", ["python3", "repo/tools/smoke_asset_rag.py"]),
    ("Pointer Authority", ["python3", "repo/tools/smoke_pointer_authority.py"]),
    ("QC Strict Routing", ["python3", "repo/tools/smoke_qc_strict_routing.py"]),
    ("Budget Guardrails", ["python3", "repo/tools/smoke_budget_enforcement.py"]),
    ("Ingress Validation", ["python3", "repo/tools/smoke_ingress_validation.py"]),
    ("n8n Ops Triggers", ["python3", "repo/tools/smoke_ops_triggers.py"]),
]


def run_test(name, cmd):
    print(f"Running: {name}...", end="", flush=True)
    start_time = time.time()
    try:
        result = subprocess.run(
            cmd, cwd=str(repo_root), capture_output=True, text=True, timeout=120
        )
        duration = time.time() - start_time
        if result.returncode == 0:
            print(f" [PASS] ({duration:.2f}s)")
            return True, ""
        else:
            print(f" [FAIL] ({duration:.2f}s)")
            return False, result.stdout + result.stderr
    except Exception as e:
        print(" [ERROR]")
        return False, str(e)


def main():
    print("=== Cat AI Factory Test Harness ===\n")
    passed = []
    failed = []

    for name, cmd in TESTS:
        success, error = run_test(name, cmd)
        if success:
            passed.append(name)
        else:
            failed.append((name, error))

    print("\n=== Summary ===")
    print(f"Total: {len(TESTS)}")
    print(f"Passed: {len(passed)}")
    print(f"Failed: {len(failed)}")

    if failed:
        print("\n=== Failures ===")
        for name, err in failed:
            print(f"\n--- {name} ---")
            print(err)
        sys.exit(1)

    print("\nAll tests PASSED!")
    sys.exit(0)


if __name__ == "__main__":
    main()
