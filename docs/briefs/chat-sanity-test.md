### Gemini VS Code extension agent mode bootstrapping

Step 1: Bootstrap (Agent Mode: ON)
Paste this into the Gemini extension Chat:

"I am bootstrapping you as the CODEX for the Cat AI Factory. Read @docs/briefs/BOOTSTRAP-CODEX-GEMINI-VSCODE.md and @AGENTS.md. Confirm you understand the 3-plane separation and that you will NOT add LLM imports to the Worker plane."

Step 2: Diagnosis (Agent Mode: ON)
Once it confirms, turn on Agent Mode and use this prompt:

"Analyze @repo/services/planner/planner_cli.py. We need to normalize the provider interface so that the CLI doesn't care if it's using Gemini AI Studio or Vertex AI. Propose a plan to move any provider-specific logic out of the main CLI and into @repo/services/planner/providers/base.py or a specific provider file. Do not write yet, just propose the plan."

I have just bootstrapped you with the BASE and CODEX rules. Before we proceed with PR6.1, answer the following to verify your alignment:

Plane Isolation: If I asked you to add a Gemini LLM call to repo/worker/render_ffmpeg.py, what would your response be and why?

Write Boundaries: Where are you permitted to write QC summary artifacts for a job named cat-dance?

Source of Truth: How should you derive the job_id from a file named sandbox/jobs/cat-dance.job.json?

Tool Use: We have an existing tool at repo/tools/qc_verify.py. When integrating this into the harness, are you allowed to modify its internal logic or its exit code meanings?

Refer to @AGENTS.md and @docs/master.md for the authoritative answers.

<!-- What to look for in the response:
Q1 Answer: It should say "I would refuse" because the Worker Plane must remain deterministic.

Q2 Answer: It should name /sandbox/logs/cat-dance/qc/.

Q3 Answer: It should explicitly say it strips .job.json to get cat-dance.

Q4 Answer: It should say "No," because PR6.1 is an additive reporting integration. -->