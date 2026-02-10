# Cat AI Factory — Brand Pack (v1)

This document defines the canonical brand identity for **Cat AI Factory (CAF)**.

CAF is a **public, portfolio-grade** repo.  
Brand assets in this repo are **static, repo-owned**, and **safe to publish**.

------------------------------------------------------------

## Canonical Identity

- Brand name: **Cat AI Factory**
- Short name: **CAF**
- Canonical handle: **@cataifactory**

Recommended display names:
- YouTube: `Cat AI Factory`
- Instagram: `Cat AI Factory`
- TikTok: `Cat AI Factory`
- X: `Cat AI Factory`
- Facebook: `Cat AI Factory`
- Snapchat: `Cat AI Factory`
- Threads: `Cat AI Factory`

------------------------------------------------------------

## Platform Accounts (v1)

NOTE: Links may be placeholders until finalized.

- YouTube: <ADD_LINK_HERE>
- Instagram: <ADD_LINK_HERE>
- TikTok: <ADD_LINK_HERE>
- X: <ADD_LINK_HERE>
- Facebook: <ADD_LINK_HERE>
- Snapchat: <ADD_LINK_HERE>
- Threads: <ADD_LINK_HERE>

------------------------------------------------------------

## Repo-Owned Brand Assets

These are static UI assets used for platform setup and branding.

### Profile image (required)
- `repo/assets/brand/profile_1x1.png`

### Optional platform banners
- YouTube: `repo/assets/brand/banner_youtube.png`
- Facebook: `repo/assets/brand/banner_facebook.png`
- X: `repo/assets/brand/banner_x.png`

Rules:
- These assets are **NOT runtime inputs** to the factory pipeline.
- These assets must remain **license-safe** and **repo-owned**.
- Do NOT download or embed third-party art without explicit license clearance.

------------------------------------------------------------

## Watermark (Worker-owned; deterministic)

The CAF watermark is a **Worker-plane deterministic transform**.

Binding decision:
- ADR-0022 — Deterministic watermark overlay (Worker; repo-owned asset; no schema changes)

Canonical watermark asset:
- `repo/assets/watermarks/caf-watermark.png`

Rules (non-negotiable):
- The watermark is applied by the Worker to:
  - `/sandbox/output/<job_id>/final.mp4`
- No schema changes are introduced for watermarking.
- Bundles automatically inherit watermarking because they copy `final.mp4`.
- Watermark placement is deterministic in v1 (single default placement; no per-platform rules).

------------------------------------------------------------

## Posting Workflow Notes (v1)

CAF generates a universal rendered output:
- `/sandbox/output/<job_id>/final.mp4`

This output is suitable for all platforms in v1:
- YouTube
- Instagram
- TikTok
- X
- Facebook
- Snapchat
- Threads

Important:
- **Facebook/Snapchat/Threads do NOT require platform-specific video adapters in v1.**
- CAF produces one universal `final.mp4`.
- Platform differences are handled via **bundle artifacts** (copy files, checklists), not video transforms.

------------------------------------------------------------

## Public Repo Safety Rules

CAF is a public repo. Therefore:

- No secrets are allowed in-repo (API keys, OAuth tokens, refresh tokens, cookies, private keys, service accounts).
- No personal identifiers should be added to docs or configs.
- Any credentialed publishing integrations must live outside this repo
  (private ops repo / separate deployment artifact).

See:
- `docs/briefs/GUARDRAILS.md`
- `SECURITY.md`
