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
- Preserve the ORIGINAL TEXT exactly — Korean stays Korean, do not translate.{extra_rules}
- Output ONLY the JSON array. No prose."""


# Appended to the Vision prompt when the chosen output template renders one
# subject per slide — keeps Vision from splitting a single subject's attribute
# lines (지역/날짜/가격 …) into separate `items[]`.
_SINGLE_CONTENT_RULE = (
    "\n- ⚠ TARGET TEMPLATE — ONE SUBJECT PER SLIDE: the output carousel uses a "
    "template where every slide renders exactly ONE subject with ONE image. So "
    "`items` MUST be empty ([]) for EVERY slide (cover, content, cta alike). "
    "NEVER split a slide into multiple items. A single subject's attribute lines "
    "— location/지역, date/날짜, time/시간, price/가격, address/주소 and similar "
    "\"▶\" metadata bullets — are NOT separate items; keep them inside `body`."
)

# Appended when the template's cover / cta layout has no body text slot — the
# slide is title-only, so Vision must not emit a body/subtext for it.
_COVER_TITLE_ONLY_RULE = (
    "\n- The COVER slide (index 0) is TITLE-ONLY in this template: put its "
    "title in `headline`, and leave `body` and `subtext` EMPTY for it."
)
_CTA_TITLE_ONLY_RULE = (
    "\n- The CTA slide is TITLE-ONLY in this template: put its line in "
    "`headline`, and leave `body` and `subtext` EMPTY for it."
)


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


def _fold_items_into_body(slide: dict) -> None:
    """Collapse a slide's `items[]` into `body` and clear `items`.

    Used when the target template is one-subject-per-slide: the slide can't
    carry multiple item cells, so any items Vision still produced are merged
    into the body text.
    """
    items = slide.get("items") or []
    if not items:
        return
    lines: list[str] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        parts = [str(it.get(k) or "").strip() for k in ("title", "subtitle", "description")]
        line = " — ".join(p for p in parts if p)
        if line:
            lines.append(line)
    if lines:
        body = (slide.get("body") or "").strip()
        slide["body"] = (body + "\n" + "\n".join(lines)).strip() if body else "\n".join(lines)
    slide["items"] = []


async def _vision_extract_chunk(paths: list[str], *, offset: int, total: int, model: str, extra_rules: str = "") -> list[dict]:
    """Run Vision over a slice of slide images, returning {pos: entry} keyed by
    the slide's GLOBAL position in the original carousel (offset + local index).
    Uses Vision's reported `index` when present so a dropped/merged response
    doesn't silently shift content onto the wrong page.
    """
    prompt = USER_PROMPT_TEMPLATE.format(n=len(paths), extra_rules=extra_rules)
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
    template_profile: dict | None = None,
) -> list[dict]:
    """Run Gemini Vision over the slide images and return extracted slide list.

    template_profile: optional {"single_content": bool}. When single_content is
    True the chosen output template renders one subject per slide, so Vision is
    told not to split slides and any stray `items[]` are folded into `body`.
    """
    if not image_urls:
        return []

    single_content = bool(template_profile and template_profile.get("single_content"))
    cover_headline_only = bool(template_profile and template_profile.get("cover_headline_only"))
    cta_headline_only = bool(template_profile and template_profile.get("cta_headline_only"))
    extra_rules = _SINGLE_CONTENT_RULE if single_content else ""
    if cover_headline_only:
        extra_rules += _COVER_TITLE_ONLY_RULE
    if cta_headline_only:
        extra_rules += _CTA_TITLE_ONLY_RULE

    paths = await _download_slide_images(image_urls, cache_subdir=cache_key)
    total = len(paths)

    # Chunk the call when there are many slides — keeps each response under the
    # token cap so Vision doesn't drop/merge entries (which would shift items
    # onto the wrong page downstream).
    raw_entries: list[dict] = []
    for start in range(0, total, _VISION_CHUNK_SIZE):
        chunk = paths[start : start + _VISION_CHUNK_SIZE]
        chunk_entries = await _vision_extract_chunk(
            chunk, offset=start, total=total, model=model, extra_rules=extra_rules
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
        if single_content:
            _fold_items_into_body(s)
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
        body = (s.get("body") or "").strip()
        subtext = (s.get("subtext") or s.get("subtitle") or "").strip()
        # cover/cta whose template layout is title-only: drop body/subtext so
        # the extraction matches the template (no orphan description field).
        if (i == 0 and cover_headline_only) or (ttype == "cta" and cta_headline_only):
            body = ""
            subtext = ""
        cleaned.append({
            "index": i,
            "type": ttype,
            "tag": (s.get("tag") or "").strip(),
            "headline": (s.get("headline") or "").strip(),
            "body": body,
            "subtext": subtext,
            "items": s.get("items") or [],
        })
    return cleaned
