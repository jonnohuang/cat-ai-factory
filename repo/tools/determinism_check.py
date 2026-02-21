import argparse
import hashlib
import pathlib

DEFAULT_FILES = ["final.mp4", "final.srt", "result.json"]


def sha256_file(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser(description="Compare outputs across two runs.")
    parser.add_argument("run_a", help="Path to first run output directory")
    parser.add_argument("run_b", help="Path to second run output directory")
    parser.add_argument(
        "--files",
        nargs="+",
        default=DEFAULT_FILES,
        help="Files to compare (default: final.mp4 final.srt result.json)",
    )
    args = parser.parse_args()

    run_a = pathlib.Path(args.run_a)
    run_b = pathlib.Path(args.run_b)

    errors = []
    for run in [run_a, run_b]:
        if not run.exists():
            errors.append(f"Missing run directory: {run}")

    if errors:
        print("Determinism check failed:")
        for err in errors:
            print(f"- {err}")
        raise SystemExit(1)

    mismatches = []
    for name in args.files:
        a_path = run_a / name
        b_path = run_b / name
        if not a_path.exists():
            mismatches.append(f"Missing {name} in {run_a}")
            continue
        if not b_path.exists():
            mismatches.append(f"Missing {name} in {run_b}")
            continue
        a_hash = sha256_file(a_path)
        b_hash = sha256_file(b_path)
        if a_hash != b_hash:
            mismatches.append(f"{name} differs: {a_hash} != {b_hash}")

    if mismatches:
        print("Determinism check failed:")
        for msg in mismatches:
            print(f"- {msg}")
        raise SystemExit(1)

    print("Determinism check OK.")


if __name__ == "__main__":
    main()
