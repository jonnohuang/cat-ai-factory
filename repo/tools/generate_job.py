import datetime
import json
import os
import pathlib
import random

NICHES = ["cute lifelike cat doing funny activities"]

IDEAS = [
    (
        "Cat vs invisible laser",
        "Cat tries to catch a laser dot that keeps teleporting.",
    ),
    ("Cat attempts yoga", "Cat copies yoga poses… very confidently… very incorrectly."),
    ("Cat steals a snack", "Cat executes a heist but the snack keeps sliding away."),
    ("Cat learns to dance", "Cat does accidental dance moves to music beats."),
    ("Cat vs box physics", "Cat tries to sit in a box that is clearly too small."),
]

CAPTION_POOL = [
    "Sneaky mode: ON",
    "WAIT—WHAT?!",
    "He really thought…",
    "This is personal now.",
    "Absolute cinema.",
    "The confidence 💀",
    "You saw that, right?",
]

HASHTAGS = ["#cat", "#cute", "#funnycat", "#catvideos", "#shorts"]


def today_str():
    return datetime.date.today().isoformat()


def make_job(date: str):
    niche = random.choice(NICHES)
    title, premise = random.choice(IDEAS)

    hook = f"{title}… and it gets ridiculous."
    voiceover = (
        f"Today’s episode: {premise} "
        "He plans. He commits. He fails. He recalculates. "
        "And then he looks at the camera like it’s YOUR fault."
    )
    ending = "He walks away pretending he won."

    shots = []
    t = 0
    for cap in random.sample(CAPTION_POOL, k=6):
        shots.append(
            {"t": t, "visual": "home setting", "action": premise, "caption": cap}
        )
        t += 3

    job = {
        "job_id": f"cat-{date}",
        "date": date,
        "niche": niche,
        "video": {
            "length_seconds": 20,
            "aspect_ratio": "9:16",
            "fps": 30,
            "resolution": "1080x1920",
        },
        "script": {"hook": hook, "voiceover": voiceover, "ending": ending},
        "shots": shots[:6],
        "captions": [s["caption"] for s in shots[:6]],
        "hashtags": HASHTAGS,
        "render": {
            "background_asset": "assets/bg.mp4",
            "subtitle_style": "big_bottom",
            "output_basename": f"cat-{date}",
        },
    }
    return job


def main():
    date = os.environ.get("JOB_DATE") or today_str()
    out_dir = pathlib.Path("/sandbox/jobs")
    out_dir.mkdir(parents=True, exist_ok=True)

    job = make_job(date)
    out_path = out_dir / f"{job['job_id']}.job.json"
    out_path.write_text(json.dumps(job, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
