# CAF — Antigravity CODEX Safety Checklist (Pre-Write + Pre-PR)

Use this checklist **every time before you modify any files** in an IDE Agent Manager
(Antigravity / Cursor / Windsurf) running in **CODEX role**.

Goal: prevent invariant drift, schema accidents, secret leakage, and scope creep.

------------------------------------------------------------

## 0) Role + Scope Confirmation (MUST)

- [ ] Role is explicitly **CODEX** (implementation only).
- [ ] A single PR scope is declared in this chat.
- [ ] You can list “In scope” vs “Out of scope” in 3 bullets max.
- [ ] If anything is ambiguous, ask **exactly ONE** clarification question and stop.

------------------------------------------------------------

## 1) Authority Order (MUST)

Before making changes, confirm you have (or were given) the relevant parts of:
- [ ] PR prompt in chat (highest priority)
- [ ] docs/master.md
- [ ] docs/decisions.md
- [ ] docs/architecture.md
- [ ] AGENTS.md

Non-authoritative (do not treat as binding):
- [ ] docs/memory.md

------------------------------------------------------------

## 2) Invariants Gate (MUST PASS)

### 2.1 Three-plane invariant (absolute)
- [ ] Planner writes **job contracts only** (`/sandbox/jobs/*.job.json`)
- [ ] Control Plane writes **logs/state only** (`/sandbox/logs/<job_id>/**`)
- [ ] Worker writes **outputs only** (`/sandbox/output/<job_id>/**`)
- [ ] Distribution/Ops is **post-factory** and must not mutate worker outputs

### 2.2 Files-as-bus
- [ ] No agent-to-agent RPC, no shared memory coordination introduced
- [ ] No “side channel” bypass around `/sandbox/**` semantics

### 2.3 Dist artifacts authority (when relevant)
- [ ] Derived artifacts live under: `/sandbox/dist_artifacts/<job_id>/`
- [ ] Publish idempotency authority is:
      `/sandbox/dist_artifacts/<job_id>/<platform>.state.json`
- [ ] Idempotency key remains `{job_id, platform}`

------------------------------------------------------------

## 3) Prohibited Changes Gate (STOP if any are true)

- [ ] You are about to edit a JSON schema / contract that wasn’t explicitly scoped
- [ ] You are about to append/modify ADRs (ARCH-only; CODEX never does this)
- [ ] You are about to change tool CLI flags/semantics outside an explicit “tool normalization” PR
- [ ] You are about to add platform credentials / OAuth tokens / secrets handling into repo
- [ ] You are about to write to `sandbox/**` (repo-only writes)
- [ ] You are about to modify `sandbox/assets/manifest.json` in any way
      (do NOT overwrite, reformat, reorder keys, or “touch” it)

If any box above is checked: **STOP and escalate to ARCH/IMPL.**

------------------------------------------------------------

## 4) Security Gate (MUST PASS)

- [ ] No secrets in code, docs, logs, or example files
- [ ] No tokens / API keys / refresh tokens in diffs
- [ ] `.env` is never modified or committed
- [ ] Debug output does not print raw model output that could contain secrets
- [ ] Any new cloud-facing tooling supports **--dry-run** (when applicable)
- [ ] Any IAM/service-account guidance is least-privilege and out-of-repo

------------------------------------------------------------

## 5) Determinism + Idempotency Gate (MUST PASS)

- [ ] New tooling is deterministic given the same artifact inputs
- [ ] Re-running does not create duplicate side effects
- [ ] Any “publish/push/upload” behavior is either:
  - bundle-only (default), OR
  - explicitly opt-in and scoped (YouTube first), AND never blocks the bundle path

------------------------------------------------------------

## 6) Edit Strategy Gate (MUST PASS)

- [ ] Prefer minimal diffs; avoid large rewrites of existing files
- [ ] `cat <<'EOF'` is used only for **new** files (unless PR explicitly requests full rewrite)
- [ ] You can list exact files touched before you start

------------------------------------------------------------

## 7) Deliverables Gate (Required Outputs)

Before finalizing work, ensure you can provide:
- [ ] Implementation plan (3–6 steps)
- [ ] File-level diff list (what changed/added)
- [ ] Smoke test commands (human-runnable)
- [ ] Pass criteria (what “good” looks like)

------------------------------------------------------------

## 8) Final Self-Check (30 seconds)

- [ ] No schema changes slipped in
- [ ] No ADR changes slipped in
- [ ] No sandbox writes
- [ ] No manifest modification
- [ ] Scope stayed within PR
- [ ] Determinism + idempotency preserved

If all boxes are checked, you may proceed with implementation output.

