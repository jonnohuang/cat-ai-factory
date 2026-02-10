# CAF — Brand Spec (v1)

This folder defines the **canonical branding** for Cat AI Factory (CAF).
These rules exist to keep the brand consistent across:
- hero character assets
- watermarks
- platform handles
- per-platform copy formatting
- channel profile/banners

---

## 1) Canonical Brand Name

Primary (canonical):
- **Cat AI Factory**

Backup (only if needed):
- **Cat AI Studio**

Rule:
- Use **Cat AI Factory** everywhere unless a platform name conflict forces fallback.

---

## 2) Canonical Handle Strategy

Goal:
- Use the **same handle** on every platform.

Preferred handle:
- `@cataifactory`

Fallback order:
1) `@cat_ai_factory`
2) `@catai_factory`
3) `@cataifactorystudio`
4) `@cataifactoryhq`
5) `@cataifactoryofficial`

Rule:
- If the exact handle is not available everywhere, choose the closest consistent fallback
  and use it universally across all platforms.

---

## 3) Platforms (Initial Targets)

Register early (even if not posting yet):
- YouTube (channel)
- TikTok
- Instagram
- X (Twitter)

Later / Phase 2:
- Douyin
- Bilibili
- Xiaohongshu

---

## 4) Watermark Policy (Visual Branding)

Purpose:
- discourage lazy reposting
- preserve attribution when reposted
- increase brand recognition

Guidelines:
- watermark must be **small** and **semi-transparent**
- place in a corner safe zone (default bottom-right)
- avoid large center watermarks (hurts platform quality ranking)
- watermark should contain:
  - hero head mark OR
  - `@handle` text
- do not clutter: one mark only

Note:
- Watermarking is a deterministic Worker Plane transform.
- It must remain ADR-compliant and deterministic.

---

## 5) Copy / Caption Branding (Text Branding)

When adding copyright notice text to captions/descriptions:
- Keep it short and non-spammy.
- Prefer a single line for YouTube description.

Example:
- `© Cat AI Factory`

---

## 6) Hero Character Policy

The primary hero is defined in:
- `docs/brand/hero_consistency.md`

Rule:
- All hero variants must be derived from the MASTER HERO reference.
- Do not generate new heroes or expressions from scratch unless explicitly approved.

---

## 7) Repo Visibility & Secrets (Public Repo Safety)

CAF is intended to be public.
Therefore:
- no API keys
- no tokens
- no cookies
- no OAuth secrets
- no refresh tokens
- no .env committed (only .env.example)
- no credential JSON files

Any PR introducing real publishing authentication must be designed so that
credentials can live in a private ops repo or secret manager.

---
