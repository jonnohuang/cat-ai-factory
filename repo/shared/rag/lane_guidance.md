# Lane Guidance (Planner Reference)

- Lane A (`ai_video`): expensive, gated by budget; avoid unless explicitly requested.
- Lane B (`image_motion`): low cost; requires 1–3 seed frames + deterministic motion.
- Lane C (`template_remix`): lowest cost; use templates/clips with deterministic recipes.
- Lane is a non-binding hint; schema must remain permissive.
