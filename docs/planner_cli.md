
## Planner CLI (PR5)

The planner CLI runs locally and does NOT require the Clawdbot gateway.

Requirements:
- `GEMINI_API_KEY` must be set at runtime

Run:

```bash
# set GEMINI_API_KEY in your shell environment first
python3 -m repo.services.planner.planner_cli \
  --prd sandbox/PRD.json \
  --inbox sandbox/inbox \
  --out sandbox/jobs \
  --provider gemini_ai_studio
```

On success, a new `/sandbox/jobs/<job_id>.job.json` is created (or `-v2`, `-v3`, etc on collision).
