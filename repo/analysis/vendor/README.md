# Vendor Reverse-Prompt Suggestions (Non-Authoritative)

This folder stores optional vendor-derived reverse-prompt suggestion artifacts.

Path conventions:
- repo/analysis/vendor/indiegtm/*.json
- repo/analysis/vendor/nanophoto/*.json
- repo/analysis/vendor/bigspy/*.json

Hard rules:
- These artifacts are suggestions only.
- They must never overwrite deterministic analyzer truth fields.
- Planner may ingest them as optional hints.
- Worker must not depend on them.
- No secrets, credentials, or copyrighted source media in this folder.
