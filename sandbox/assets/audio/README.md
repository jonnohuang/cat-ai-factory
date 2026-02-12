# Audio Strategy v1

This directory contains the canonical audio assets and manifest for the Cat AI Factory.

## The Audio Manifest
The file `audio_manifest.v1.json` is a **read-only allowlist**. The Planner Agent uses this file to select background audio beds for generated videos.

**Rules:**
* The Planner may ONLY select beds listed in this manifest.
* The Planner must NOT invent filenames or scrape trending audio.
* The manifest defines the license status and metadata for each track.

## License & Safety Rules
The repo is public. We must strictly adhere to copyright safety.

**Allowed License Types:**
* `cc0`: Creative Commons Zero (Public Domain Dedication).
* `public-domain`: Generic public domain.
* `self-created`: Original audio created by the repo owner.
* `explicit-permission`: Audio where written permission has been granted.
* `placeholder`: For local-only testing (not committed).

**`safe_to_commit` Flag:**
* `true`: The asset is safe to be checked into the public git repo (e.g., CC0).
* `false`: The asset is local-only (e.g., a placeholder or licensed track that cannot be redistributed). The manifest entry may exist, but the file should be gitignored or managed outside the repo.

## Adding Local Audio (Development)
To test with local audio without committing it:
1. Place the file in `sandbox/assets/audio/beds/`.
2. Add an entry to `audio_manifest.v1.json` with `"license": { "type": "placeholder", "safe_to_commit": false }`.
   - Ensure the `relpath` starts with `assets/audio/beds/`.
3. Do NOT commit the audio file itself.
   - **Note:** The manifest entry is committed; the audio file is not.

## Validation
Always validate the manifest after editing:

```bash
python3 repo/tools/validate_audio_manifest.py sandbox/assets/audio/audio_manifest.v1.json
```
