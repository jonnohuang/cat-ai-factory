import json
import pathlib
import re
import sys

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
HASHTAG_RE = re.compile(r"^#\w[\w_]*$")

def fail(msg: str) -> None:
    raise SystemExit(msg)

def require_fields(obj: dict, fields: list[str], ctx: str) -> None:
    for field in fields:
        if field not in obj:
            fail(f"Missing required field {ctx}.{field}")

def validate_job(job: dict) -> None:
    require_fields(job, ["job_id", "date", "niche", "video", "script", "shots", "captions", "hashtags", "render"], "job")
    if not isinstance(job["job_id"], str) or len(job["job_id"]) < 6:
        fail("job.job_id must be a string with length >= 6")
    if not isinstance(job["date"], str) or not DATE_RE.match(job["date"]):
        fail("job.date must be YYYY-MM-DD")
    if not isinstance(job["niche"], str):
        fail("job.niche must be a string")

    video = job["video"]
    require_fields(video, ["length_seconds", "aspect_ratio", "fps", "resolution"], "video")
    if not isinstance(video["length_seconds"], int) or not (10 <= video["length_seconds"] <= 60):
        fail("video.length_seconds must be int 10..60")
    if video["aspect_ratio"] != "9:16":
        fail("video.aspect_ratio must be 9:16")
    if not isinstance(video["fps"], int) or not (24 <= video["fps"] <= 60):
        fail("video.fps must be int 24..60")
    if video["resolution"] != "1080x1920":
        fail("video.resolution must be 1080x1920")

    script = job["script"]
    require_fields(script, ["hook", "voiceover", "ending"], "script")
    for field, min_len, max_len in [("hook", 3, 120), ("voiceover", 20, 900), ("ending", 3, 120)]:
        val = script[field]
        if not isinstance(val, str) or not (min_len <= len(val) <= max_len):
            fail(f"script.{field} length must be {min_len}..{max_len}")

    shots = job["shots"]
    if not isinstance(shots, list) or not (6 <= len(shots) <= 14):
        fail("shots must be list length 6..14")
    for idx, shot in enumerate(shots):
        if not isinstance(shot, dict):
            fail(f"shots[{idx}] must be an object")
        require_fields(shot, ["t", "visual", "action", "caption"], f"shots[{idx}]")
        if not isinstance(shot["t"], int) or not (0 <= shot["t"] <= 60):
            fail(f"shots[{idx}].t must be int 0..60")
        for key in ["visual", "action", "caption"]:
            if not isinstance(shot[key], str):
                fail(f"shots[{idx}].{key} must be a string")

    captions = job["captions"]
    if not isinstance(captions, list) or not (4 <= len(captions) <= 24):
        fail("captions must be list length 4..24")
    for idx, cap in enumerate(captions):
        if not isinstance(cap, str) or not (1 <= len(cap) <= 80):
            fail(f"captions[{idx}] length must be 1..80")

    hashtags = job["hashtags"]
    if not isinstance(hashtags, list) or not (3 <= len(hashtags) <= 20):
        fail("hashtags must be list length 3..20")
    for idx, tag in enumerate(hashtags):
        if not isinstance(tag, str) or not HASHTAG_RE.match(tag):
            fail(f"hashtags[{idx}] must match {HASHTAG_RE.pattern}")

    render = job["render"]
    require_fields(render, ["background_asset", "subtitle_style", "output_basename"], "render")
    if not isinstance(render["background_asset"], str):
        fail("render.background_asset must be a string")
    if render["subtitle_style"] not in ["big_bottom", "karaoke_bottom"]:
        fail("render.subtitle_style must be big_bottom or karaoke_bottom")
    if not isinstance(render["output_basename"], str):
        fail("render.output_basename must be a string")

def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python3 repo/tools/validate_job.py /sandbox/jobs/<job>.job.json")
    path = pathlib.Path(sys.argv[1])
    job = json.loads(path.read_text(encoding="utf-8"))
    validate_job(job)
    print("OK")

if __name__ == "__main__":
    main()
