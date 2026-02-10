# CAF — Hero Consistency Rules (v1)

Applies to: Hero characters, mascot assets, watermark marks, expression packs

## Purpose
Maintain a single recognizable hero character identity across all generated assets, expressions, and future content.

This document prevents **style drift** (the hero subtly changing every time) which destroys branding.

---

## 1) Canonical Hero Definition

### Hero #1 (primary mascot)
- Species: cat  
- Color: orange tabby  
- Style: cute mascot / sticker style  
- Eyes: large, shiny, expressive  
- Mood range: cute (never scary)  
- Background: transparent PNG for final assets  

### Hero naming
- Choose ONE name and stick to it in all docs and copy.
- Recommended names: **Mango / Pumpkin / Sunny / Cheddar / Tangy**

### Optional signature feature (choose 1 only)
- heart-shaped nose OR tiny fang OR swirl cheek mark OR freckles

### Optional accessory (choose 1 only)
- bandana OR bell collar OR bowtie  
- Do NOT stack accessories.

---

## 2) Golden Rule: Generate ONCE, Then Reference

You MUST generate a single **MASTER HERO** image first.

All future expressions and variants must be generated using the MASTER HERO
as a reference (image-to-image / character reference), NOT by prompting from scratch.

If the generator cannot reliably keep the same character:
- stop generating
- switch to manual edits (Photoshop/Procreate) for expressions

---

## 3) Required Asset Pack (Minimal)

Minimum hero pack required for CAF PR15+:

1) `hero_orange_base.png`  
2) `hero_orange_happy.png`  
3) `hero_orange_shocked.png`  
4) `hero_orange_angry.png` (cute angry)

Optional (later):
- `hero_orange_sitting.png`
- `hero_orange_waving.png`

---

## 4) Output Specs (Non-negotiable)

### Format
- PNG with transparent background

### Resolution
- Preferred: **2048 x 2048**
- Acceptable: **1024 x 1024**

### Framing
- The hero must be centered and cropped consistently across all expressions.
- The hero must occupy roughly the same percentage of the canvas in every file.

### Style
- Keep outline thickness consistent.
- Keep palette consistent.
- Avoid complex painterly textures or realistic fur.

---

## 5) Consistency Checklist (Pass/Fail)

An expression variant is considered VALID only if:
- same head shape
- same eye shape + placement
- same ear shape + placement
- same fur stripe pattern (or simplified consistent markings)
- same color palette
- same art style and line thickness
- same overall proportions

If any of these drift noticeably, regenerate using the MASTER HERO reference.

---

## 6) Approved Generation Workflow (Gemini Nano Banana)

Step 1: Generate MASTER HERO
- front-facing
- centered
- plain background
- no props
- no text

Step 2: Generate expressions using MASTER HERO reference
- happy
- shocked
- cute-angry

Step 3: Cleanup + export
- remove background
- standardize crop framing
- export transparent PNGs

---

## 7) File Naming Convention

Use lowercase, deterministic filenames:

- `hero_orange_base.png`
- `hero_orange_happy.png`
- `hero_orange_shocked.png`
- `hero_orange_angry.png`

---

## 8) Brand Usage Rules

### Brand name
- Canonical: **Cat AI Factory**

### Handle (goal)
- `@cataifactory`

### Watermark usage
- Watermark should use the hero head mark or `@handle`.
- Watermark must be subtle (semi-transparent) and placed in a corner safe zone.

---
