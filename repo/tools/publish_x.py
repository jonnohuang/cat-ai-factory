"""
X (Twitter) Publisher CLI (Wrapper for ADR-0021 Adapter)
Generates 'v1' export bundle for X.
"""
import argparse
import sys
from pathlib import Path

def _get_repo_root() -> Path:
    """Derive repo root from file location (repo/tools/publish_x.py)."""
    return Path(__file__).resolve().parent.parent.parent

# Add repo root to sys.path so we can import 'repo' package
sys.path.append(str(_get_repo_root()))

from repo.tools.publisher_adapters.x import XAdapter

def main():
    parser = argparse.ArgumentParser(description="X Publisher (ADR-0021 Bundle Generator)")
    parser.add_argument("--job-id", required=True, help="Job ID")
    parser.add_argument("--publish-plan", required=True, help="Path to publish_plan.json")
    parser.add_argument("--dist-root", default="sandbox/dist_artifacts", help="Root for dist artifacts")
    
    args = parser.parse_args()
    
    # Write Boundary Enforcement (Strict & Robust to CWD)
    repo_root = _get_repo_root()
    expected_dist_root = (repo_root / "sandbox" / "dist_artifacts").resolve()
    
    given_path = Path(args.dist_root)
    if not given_path.is_absolute():
        resolved_dist = (repo_root / given_path).resolve()
    else:
        resolved_dist = given_path.resolve()
    
    if resolved_dist != expected_dist_root:
        print(f"ERROR: --dist-root must resolve to '{expected_dist_root}'. Got: {resolved_dist}", file=sys.stderr)
        sys.exit(1)

    try:
        adapter = XAdapter()
        bundle_path = adapter.generate_bundle(
            job_id=args.job_id,
            publish_plan_path=args.publish_plan,
            dist_root=args.dist_root
        )
        if bundle_path:
            print(f"SUCCESS: X bundle generated at: {bundle_path}")
            sys.exit(0)
        else:
            print("No plan found for X. Use --publish-plan with correct content.")
            sys.exit(0)

    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
