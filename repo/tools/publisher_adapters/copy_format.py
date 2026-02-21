"""
Shared Copy Formatting Logic for Publisher Adapters (ADR-0021 / PR14)
Deterministic formatting of platform-specific copy files.
"""

import re
from typing import Any, Dict, List


def resolve_caption(
    platform_plan: Dict[str, Any], clip: Dict[str, Any], lang: str
) -> str:
    # Priority: clip.caption[lang] > platform_plan.description[lang] > ""
    # Strict: only accept strings, no coercion.

    val = clip.get("caption", {}).get(lang)
    if isinstance(val, str) and val.strip():
        return val

    val = platform_plan.get("description", {}).get(lang)
    if isinstance(val, str) and val.strip():
        return val

    return ""


def resolve_title(platform_plan: Dict[str, Any], lang: str) -> str:
    val = platform_plan.get("title", {}).get(lang)
    if isinstance(val, str) and val.strip():
        return val
    return ""


def normalize_tags(tags: List[str]) -> List[str]:
    # Trim, drop empty, CI-dedupe (preserve first), ensure #, preserve order
    if not tags:
        return []
    seen = set()
    out = []
    for t in tags:
        if not t:
            continue
        s = str(t).strip()  # Defensive coercion just in case for tags
        if not s:
            continue

        if not s.startswith("#"):
            s = "#" + s

        low = s.lower()
        if low not in seen:
            seen.add(low)
            out.append(s)
    return out


def clip_id_dirname(clip: Dict[str, Any], idx: int) -> str:
    # PR14: if clip.id exists and matches ^[A-Za-z0-9._-]+$ -> use it
    # else -> clip-NNN (ordinal)
    ordinal = f"clip-{str(idx + 1).zfill(3)}"
    cid = clip.get("id")
    if isinstance(cid, str) and re.fullmatch(r"[A-Za-z0-9._-]+", cid):
        return cid
    return ordinal


def format_copy(
    platform: str, platform_plan: Dict[str, Any], clip: Dict[str, Any], lang: str
) -> str:
    body = resolve_caption(platform_plan, clip, lang)
    title = resolve_title(platform_plan, lang)
    tags = normalize_tags(platform_plan.get("tags", []))
    pub_time = platform_plan.get("publish_time")

    p = platform.lower()
    if p == "youtube":
        return _fmt_youtube(title, body, tags, pub_time)
    elif p == "instagram":
        return _fmt_instagram(body, tags, pub_time)
    elif p == "tiktok":
        return _fmt_tiktok(body, tags, pub_time)
    elif p == "x":
        return _fmt_x(body, tags, pub_time)
    else:
        # Fallback (safety)
        return body


def _fmt_youtube(title, body, tags, time):
    lines = []
    if title:
        lines.append(f"TITLE: {title}")

    if body:
        lines.append("DESCRIPTION:")
        lines.append(body)

    if tags:
        if lines:
            lines.append("")
        lines.append(f"HASHTAGS: {' '.join(tags)}")

    if time:
        if lines:
            lines.append("")
        lines.append(f"SCHEDULED_PUBLISH_TIME: {time}")

    return "\n".join(lines)


def _fmt_instagram(body, tags, time):
    res = body if body else ""
    if tags:
        if res:
            res += "\n\n"
        res += " ".join(tags)
    if time:
        if res:
            res += "\n\n"
        res += f"SCHEDULED_PUBLISH_TIME: {time}"
    return res


def _fmt_tiktok(body, tags, time):
    res = body if body else ""
    if tags:
        if res:
            res += "\n\n"
        res += " ".join(tags)
    if time:
        if res:
            res += "\n\n"
        res += f"SCHEDULED_PUBLISH_TIME: {time}"
    return res


def _fmt_x(body, tags, time):
    t3 = tags[:3]
    res = body if body else ""
    if t3:
        if res:
            res += " "
        res += " ".join(t3)
    if time:
        if res:
            res += "\n"
        res += f"SCHEDULED_PUBLISH_TIME: {time}"
    return res
