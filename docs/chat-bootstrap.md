# Cat AI Factory — Chat Bootstrap Prompt

Paste this as the first message in any new chat.

------------------------------------------------------------

You are assisting with the Cat AI Factory project.

Context:
- Headless, agent-driven content pipeline
- File-based deterministic workflows
- Planner (Clawdbot), Orchestrator (Ralph Loop), Worker (FFmpeg)
- Local Docker sandbox first, GCP Cloud Run target
- Security-first: loopback-only gateway, token auth, no secrets in Git
- This project is a portfolio artifact for ML Infrastructure / Platform roles

Current State (update occasionally):
- Local pipeline generates /sandbox/jobs/*.job.json
- Worker renders with FFmpeg to /sandbox/output (requires /sandbox/assets/bg.mp4)
- Clawdbot gateway running in Docker; bound to 127.0.0.1 with token auth
- Docs present: README.md, AGENTS.md, docs/memory.md, docs/master.md, docs/decisions.md
- Git hooks installed via scripts/install-githooks.sh

Rules for this chat:
- Focus ONLY on: [INSERT SCOPE — Docker / GCP / Agent logic / CI]
- Do NOT redesign architecture unless explicitly asked
- Prefer production-grade patterns over quick hacks
- Assume strong engineering background; avoid beginner explanations
- Flag architectural changes instead of silently applying them

File Operations:
- When creating or editing files, ALWAYS provide copy-pasteable:
  - cat > path/to/file <<'EOF' ... EOF
  - cat >> path/to/file <<'EOF' ... EOF
- For small edits, provide safe CLI edits (e.g., perl -pi -e ...) only when necessary.
- Never output large files without a cat command.
