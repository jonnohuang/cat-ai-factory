import argparse
import json
import pathlib
import re
import sys

SCHEMA_PATH = pathlib.Path(__file__).resolve().parents[1] / "shared" / "job.schema.json"


def _err(errors, msg):
    errors.append(msg)


def _is_str(value):
    return isinstance(value, str)


def _check_required(obj, key, errors, ctx):
    if key not in obj:
        _err(errors, f"Missing required field: {ctx}.{key}")
        return False
    return True


def _load_schema(errors):
    try:
        return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        _err(errors, f"Failed to read schema: {exc}")
        return None


def _validate_with_jsonschema(job, schema, errors):
    try:
        import jsonschema
    except Exception:
        print("ERROR: jsonschema not installed.")
        print("Install: python3 -m pip install jsonschema")
        print("Or (recommended): python3 -m pip install -r repo/requirements-dev.txt")
        raise SystemExit(2)

    try:
        jsonschema.validate(job, schema)
        return True
    except jsonschema.ValidationError as exc:
        _err(errors, f"Schema validation error: {exc.message}")
        return False


# Optional: keep basic validation as a belt-and-suspenders sanity check,
# but do NOT use it as a replacement for schema validation.
def _validate_basic_sanity(job, errors):
    # Fix: regexes must not double-escape in raw strings.
    date_re = re.compile(r"^\d{4}-\d{2}-\d{2}$")
    hashtag_re = re.compile(r"^#\w[\w_]*$")

    if not _check_required(job, "job_id", errors, "job"):
        return
    if not _is_str(job["job_id"]) or len(job["job_id"]) < 6:
        _err(errors, "job.job_id must be a string with length >= 6")

    if _check_required(job, "date", errors, "job"):
        if not _is_str(job["date"]) or not date_re.match(job["date"]):
            _err(errors, "job.date must be YYYY-MM-DD")

    if _check_required(job, "hashtags", errors, "job"):
        hashtags = job.get("hashtags", [])
        if not isinstance(hashtags, list):
            _err(errors, "job.hashtags must be a list")
        else:
            for i, tag in enumerate(hashtags):
                if not _is_str(tag):
                    _err(errors, f"hashtags[{i}] must be a string")
                elif not hashtag_re.match(tag):
                    _err(errors, f"hashtags[{i}] must match ^#\\w[\\w_]*$")


def main():
    parser = argparse.ArgumentParser(description="Validate job.json against schema.")
    parser.add_argument("job_path", help="Path to job.json")
    args = parser.parse_args()

    job_path = pathlib.Path(args.job_path)
    if not job_path.exists():
        raise SystemExit(f"Job file not found: {job_path}")

    job = json.loads(job_path.read_text(encoding="utf-8"))
    errors = []

    schema = _load_schema(errors)
    if schema is None:
        print("Validation failed:")
        for err in errors:
            print(f"- {err}")
        raise SystemExit(1)

    ok = _validate_with_jsonschema(job, schema, errors)

    # Optional additional sanity check (should not diverge from schema).
    _validate_basic_sanity(job, errors)

    if errors or not ok:
        print("Validation failed:")
        for err in errors:
            print(f"- {err}")
        raise SystemExit(1)

    print("Validation OK:", job_path)


if __name__ == "__main__":
    main()
