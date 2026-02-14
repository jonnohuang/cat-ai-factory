## Planner CLI (LOCAL)

The planner CLI runs locally and does NOT require the Clawdbot gateway.

Requirements:
- GEMINI_API_KEY must be set at runtime

Run:

# set GEMINI_API_KEY in your shell environment first and then the following
python3 -m repo.services.planner.planner_cli \
  --prd sandbox/PRD.json \
  --inbox sandbox/inbox \
  --out sandbox/jobs \
  --provider ai_studio

LangGraph demo (planner-only adapter):

python3 -m repo.services.planner.planner_cli \
  --prd sandbox/PRD.json \
  --inbox sandbox/inbox \
  --out sandbox/jobs \
  --provider langgraph_demo

Note: `langgraph_demo` requires `pip install langgraph` and still uses the Gemini AI Studio provider
for the draft step, followed by deterministic schema validation.

CrewAI demo (optional, planner-only):
- Install: `pip install crewai`
- Enable: `CREWAI_ENABLED=1`
- Run the same `langgraph_demo` provider. CrewAI is contained to a single LangGraph node and its
  output is validated deterministically before commit.

Optional (prompt-only):

python3 -m repo.services.planner.planner_cli \
  --prompt "Cat dancing" \
  --out sandbox/jobs \
  --provider ai_studio

On success, a new /sandbox/jobs/<job_id>.job.json is created (or -v2, -v3, etc on collision).
