"""Vision-based content extraction from a benchmark Instagram post.

Reads the post's slide images via Gemini Vision and outputs a slide list whose
text matches the ORIGINAL post — used when the user wants to remix a competitor's
content (paste their reels URL → get the same slides as a starting point).

Distinct from template extraction (template_studio.py): that one captures
visual STYLE; this one captures CONTENT.
"""

import json
import logging
from pathlib import Path

import httpx

from app.agents.llm_client import gemini_vision
from app.config import settings

logger = logging.getLogger(__name__)

CACHE_DIR = settings.DATA_DIR / "content_extractor_cache"


SYSTEM_PROMPT = """You read an Instagram carousel post and extract the actual \
text shown on each slide. Output a strict JSON list of slides, preserving the \
original wording (including the original language). Do NOT invent or rewrite \
content."""


USER_PROMPT_TEMPLATE = """Read the {n} slides of this Instagram carousel and \
return a JSON list with one entry per slide.

# Output schema
```json
[
  {{
    "index": 0,
    "type": "cover" | "content" | "cta",
    "tag": "small badge/label text (often in a colored pill at top or bottom — e.g. 'What to Eat', 'Where to Go', '#01', 'TIP'). Empty if no badge.",
    "headline": "main visible title text",
    "body": "supporting/body text, items collapsed into one string with newlines",
    "subtext": "secondary/subtitle text if any (or empty)",
    "items": [
      {{"title": "item title", "subtitle": "optional", "description": "item description"}}
    ]
  }},
  ...
]
```

# Rules
- ONLY the slide at index 0 is `cover` (the title slide). Slides at index 1 \
or higher are NEVER `cover` — they are `content` (or `cta` if a real \
call-to-action). This holds even for "one info per slide" carousels where \
every slide is a big headline over a full-bleed photo: a big-headline slide \
in the MIDDLE of the carousel is still `content`, not `cover`. Do not let a \
slide's cover-like visual style override its position.
- A slide is `cta` ONLY if it is a real call-to-action — e.g. "팔로우해주세요", \
"저장 / 공유 부탁드려요", "더 보러가기 → 프로필 링크", a single instruction with \
no product/place items. Last position in the carousel is NOT enough to call it \
cta; many carousels end with another content slide.
- If the last slide has items, products, places, or substantive content text, \
mark it `content`, not `cta`.
- Slides showing a list/grid of items: populate `items[]` with each item's text.
- Slides with one big headline + paragraph: leave `items` empty, use `headline` + `body`.
- ALWAYS look for small badge/pill labels (typically "What to Eat", "Where to Go", \
"#01", "TIP", category words in a small colored box) and put them in `tag`. If \
none, return empty string.
- Preserve the ORIGINAL TEXT exactly — Korean stays Korean, do not translate.
- Output ONLY the JSON array. No prose."""


async def _download_slide_images(image_urls: list[str], cache_subdir: str) -> list[str]:
    out_dir = CACHE_DIR / cache_subdir
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: list[str] = []
    async with httpx.AsyncClient(timeout=30.0, headers={"User-Agent": "Mozilla/5.0"}) as client:
        for i, url in enumerate(image_urls):
            ext = ".webp" if ".webp" in url else ".jpg"
            path = out_dir / f"slide_{i}{ext}"
            if not path.exists():
                resp = await client.get(url)
                resp.raise_for_status()
                path.write_bytes(resp.content)
            paths.append(str(path))
    return paths


# Max slides per Vision call. With ~4 items × {title, subtitle, description}
# per slide plus the cover/CTA boilerplate, a 9-slide carousel can push the JSON
# response past 8192 tokens — Vision then truncates or merges, which manifests
# as "page N's items appear on page M" in the editor. Chunking keeps each call
# safely under the limit.
_VISION_CHUNK_SIZE = 6


def _unwrap_raw(raw):
    """Strip common JSON wrappers Vision uses ({slides: [...]}, {data: [...]}, ...)."""
    if isinstance(raw, dict) and "raw" in raw:
        logger.warning(f"[content_extractor] Vision returned non-JSON: {raw['raw'][:200]}")
        return None
    if isinstance(raw, dict):
        for key in ("slides", "data", "items"):
            if key in raw and isinstance(raw[key], list):
                return raw[key]
    if isinstance(raw, list):
        return raw
    return None


async def _vision_extract_chunk(paths: list[str], *, offset: int, total: int, model: str) -> list[dict]:
    """Run Vision over a slice of slide images, returning {pos: entry} keyed by
    the slide's GLOBAL position in the original carousel (offset + local index).
    Uses Vision's reported `index` when present so a dropped/merged response
    doesn't silently shift content onto the wrong page.
    """
    prompt = USER_PROMPT_TEMPLATE.format(n=len(paths))
    if offset > 0 or len(paths) < total:
        # Help the model number this chunk's slides against the full carousel
        prompt += (
            f"\n\n# Chunk context\nThis batch covers slides {offset}–{offset + len(paths) - 1} "
            f"of a {total}-slide carousel. Use those absolute indices in the `index` field."
        )

    raw = await gemini_vision(
        image_paths=paths,
        prompt=prompt,
        system=SYSTEM_PROMPT,
        model=model,
        json_mode=True,
        max_tokens=8192,
    )
    raw = _unwrap_raw(raw)
    if raw is None:
        return []

    out: list[dict] = []
    for local_i, s in enumerate(raw):
        if not isinstance(s, dict):
            continue
        # Trust Vision's reported index when it falls inside this chunk; otherwise
        # fall back to positional. Bounds-check to reject hallucinated indices.
        reported = s.get("index")
        global_pos = offset + local_i
        if isinstance(reported, int) and offset <= reported < offset + len(paths):
            global_pos = reported
        s = {**s, "_global_pos": global_pos}
        out.append(s)
    return out


async def extract_slides_from_post_images(
    image_urls: list[str],
    *,
    cache_key: str,
    model: str = "gemini-flash-lite",
) -> list[dict]:
    """Run Gemini Vision over the slide images and return extracted slide list."""
    if not image_urls:
        return []

    paths = await _download_slide_images(image_urls, cache_subdir=cache_key)
    total = len(paths)

    # Chunk the call when there are many slides — keeps each response under the
    # token cap so Vision doesn't drop/merge entries (which would shift items
    # onto the wrong page downstream).
    raw_entries: list[dict] = []
    for start in range(0, total, _VISION_CHUNK_SIZE):
        chunk = paths[start : start + _VISION_CHUNK_SIZE]
        chunk_entries = await _vision_extract_chunk(
            chunk, offset=start, total=total, model=model
        )
        if len(chunk_entries) != len(chunk):
            logger.warning(
                f"[content_extractor] Vision returned {len(chunk_entries)} entries for "
                f"{len(chunk)}-slide chunk (offset={start}). Page assignment relies on "
                "Vision's `index` field for the missing ones."
            )
        raw_entries.extend(chunk_entries)

    if not raw_entries:
        return []

    # Bucket by global position so each carousel slide gets exactly one entry.
    # Last-write-wins for duplicates; gaps stay as empty placeholders so the
    # rendered slide count matches the source.
    by_pos: dict[int, dict] = {}
    for s in raw_entries:
        pos = s.get("_global_pos")
        if not isinstance(pos, int) or not (0 <= pos < total):
            continue
        by_pos[pos] = s

    cleaned: list[dict] = []
    for i in range(total):
        s = by_pos.get(i)
        if s is None:
            # Vision skipped this slide entirely — render a blank placeholder
            # so it doesn't silently shift subsequent slides up.
            logger.warning(f"[content_extractor] Vision dropped slide {i}; inserting empty placeholder")
            cleaned.append({
                "index": i,
                "type": "cover" if i == 0 else "content",
                "tag": "", "headline": "", "body": "", "subtext": "", "items": [],
            })
            continue
        ttype = (s.get("type") or "").strip().lower()
        if ttype not in ("cover", "content", "cta"):
            ttype = "cover" if i == 0 else "content"
        # A cover is by definition the title slide — only index 0 can be one.
        # Vision tends to label EVERY slide "cover" for "1 info per slide"
        # carousels, where each slide is a big headline over a full-bleed photo
        # and so looks cover-like. That mislabels the whole carousel as title
        # slides and breaks downstream layout picking. Demote any non-zero
        # "cover" to content. (The chunked Vision calls make this worse: the
        # 2nd+ chunk has no "slide 0" in view at all.)
        if ttype == "cover" and i != 0:
            ttype = "content"
        # If Vision said "cta" but the slide actually carries items[], treat
        # it as content — items unambiguously mean it's a product/place list,
        # not a follow/share prompt. Pure-text CTAs stay as cta.
        if ttype == "cta" and (s.get("items") or []):
            ttype = "content"
        cleaned.append({
            "index": i,
            "type": ttype,
            "tag": (s.get("tag") or "").strip(),
            "headline": (s.get("headline") or "").strip(),
            "body": (s.get("body") or "").strip(),
            "subtext": (s.get("subtext") or s.get("subtitle") or "").strip(),
            "items": s.get("items") or [],
        })
    return cleaned
