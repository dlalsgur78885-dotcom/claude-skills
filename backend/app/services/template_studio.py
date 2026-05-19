"""Template Studio - generate Template from a benchmark Instagram post.

Calls Gemini Vision once per benchmark post; the resulting Template is saved to DB
and reused for all future posts of that channel (Gemini cost = 1 per template).
"""

import json
import logging
import re
from pathlib import Path

import httpx
from PIL import Image
from pydantic import ValidationError
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.llm_client import gemini_vision
from app.config import settings
from app.models.channel import BenchmarkChannel
from app.models.template import CarouselTemplate
from app.schemas.carousel_blueprint import LayoutType
from app.schemas.template_spec import Template
from app.services.instagram import InstagramAPI
from app.services.template_validator import (
    snap_canvas_to_instagram_preset,
    validate_and_fix_template,
)
from app.services.cv_detector import analyze_slides, SlideAnalysis
from app.services.gradient_analyzer import analyze_background, to_background_dict
from app.services.bg_vision import analyze_background_vision, vision_to_background_dict

logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
CACHE_DIR = settings.DATA_DIR / "template_studio_cache"
# No hard cap — users decide how many template variants they want per channel.
# Each new template costs ~$0.07-0.14 in Gemini Vision, so creation is intentional.


SYSTEM_PROMPT = """You are a senior carousel designer. You analyse an Instagram \
carousel post (sequence of slide images) and output a strict JSON template that \
captures its visual style — positions, colors, fonts, decorations — so the same \
template can be reused to render new content with different copy.

You MUST output JSON conforming exactly to the Template schema described in the \
user prompt. Do not invent new fields. Pick the closest matching layout from the \
allowed enum for each slide. The canvas dimensions are specified in the user prompt \
— ALL pixel coordinates must fall within that canvas, and you must scale the design \
to fill that canvas (not leave large empty bands at top/bottom)."""


VALID_LAYOUTS = ", ".join(f'"{l.value}"' for l in LayoutType)


def _hint_group_key(h: dict, slide_index: int) -> tuple:
    """Group key for a layout hint: same key = same layout class.

    Grid slides with identical (rows, cols) share a group → Vision sees the
    layout once. Single slides are kept distinct (cover vs closing usually
    look different even though both are "single") so each gets its own image.
    """
    kind = (h.get("kind") or "single").lower()
    if kind == "grid":
        return ("grid", int(h.get("rows") or 2), int(h.get("cols") or 2))
    return ("single", slide_index, 0)


def _pick_representative_indices(hints: list[dict], slide_count: int) -> tuple[list[int], dict[int, int]]:
    """Pick one representative slide per unique layout group.

    Returns (representative_indices_in_order, dup_map) where dup_map maps every
    slide index → the representative it belongs to. Without hints, every slide
    is its own representative (no dedup).
    """
    if not hints:
        idxs = list(range(slide_count))
        return idxs, {i: i for i in idxs}
    by_idx = {int(h.get("slide_index", -1)): h for h in hints if isinstance(h, dict)}
    seen: dict[tuple, int] = {}
    dup_map: dict[int, int] = {}
    reps: list[int] = []
    for i in range(slide_count):
        h = by_idx.get(i) or {"kind": "single"}
        key = _hint_group_key(h, i)
        if key not in seen:
            seen[key] = i
            reps.append(i)
        dup_map[i] = seen[key]
    return reps, dup_map


def _format_layout_hints(
    hints: list[dict] | None,
    slide_count: int,
    dup_map: dict[int, int] | None = None,
    rep_order: list[int] | None = None,
) -> str:
    """Render user-supplied per-slide layout hints into a prompt section.

    When `dup_map` and `rep_order` are provided (dedup mode), each line marks
    whether the slide is the representative image actually sent to the model
    or a duplicate sharing the representative's layout.
    """
    if not hints:
        return ""
    by_idx = {int(h.get("slide_index", -1)): h for h in hints if isinstance(h, dict)}
    rep_position = {idx: pos + 1 for pos, idx in enumerate(rep_order or [])}
    lines = []
    for i in range(slide_count):
        h = by_idx.get(i)
        if not h:
            lines.append(f"- Slide {i+1}: (unspecified — pick best layout)")
            continue
        kind = h.get("kind") or "single"
        if kind == "grid":
            rows = int(h.get("rows") or 2)
            cols = int(h.get("cols") or 2)
            layout_desc = f"grid {rows}×{cols} — use the `grid_{rows}x{cols}` layout"
        else:
            layout_desc = "single (one main content slot, NOT a grid)"
        # Annotate dedup status
        if dup_map is not None:
            rep_idx = dup_map[i]
            if rep_idx == i:
                pos = rep_position.get(i)
                tag = f" ← REPRESENTATIVE (this is image #{pos} in your input batch)" if pos else ""
            else:
                tag = f" (DUPLICATE of slide {rep_idx+1} — no image sent, layout is identical)"
        else:
            tag = ""
        lines.append(f"- Slide {i+1}: {layout_desc}.{tag}")
    header = (
        "\n# User-classified layouts (TRUST THESE — human pre-classified each slide)\n\n"
        "Honor these per-slide layout kinds. Define each unique layout ONCE — the\n"
        "renderer applies it to every slide tagged with that same layout.\n"
    )
    if dup_map is not None and rep_order is not None:
        header += (
            f"\nTo save tokens, only the {len(rep_order)} unique representative slides "
            f"are attached as images (the {slide_count - len(rep_order)} duplicates are "
            f"omitted). Apply each REPRESENTATIVE's layout to its duplicates.\n"
        )
    return header + "\n" + "\n".join(lines) + "\n"


def _build_user_prompt(
    template_id: str,
    template_name: str,
    slide_count: int,
    canvas_w: int,
    canvas_h: int,
    aspect_label: str,
    layout_hints: list[dict] | None = None,
    dup_map: dict[int, int] | None = None,
    rep_order: list[int] | None = None,
) -> str:
    hints_block = _format_layout_hints(layout_hints, slide_count, dup_map, rep_order)
    return f"""Analyse the {slide_count} slides of this Instagram carousel and produce \
a Template JSON.

# Canvas

The output canvas is **{canvas_w}×{canvas_h} px** ({aspect_label}). Every position, \
size, and offset MUST be in this coordinate space (0 ≤ x < {canvas_w}, \
0 ≤ y < {canvas_h}). Treat the reference slides as already filling this canvas — \
do NOT shrink the design to a centered square.
{hints_block}

# Required output shape

```json
{{
  "id": "{template_id}",
  "name": "{template_name}",
  "canvas": {{"width": {canvas_w}, "height": {canvas_h}}},
  "brand": {{
    "primary_color": "#RRGGBB",
    "background_color": "#RRGGBB",
    "font_family": "Pretendard"
  }},
  "created_by": "gemini_vision",
  "layouts": {{
    "<LAYOUT_TYPE>": {{
      "background": {{
        "type": "color" | "image_keyword" | "image_path" | "gradient",
        "value": "<color hex or descriptive English keyword for background image>",
        "overlay_color": "#000000" or null,
        "overlay_opacity": 0.0
      }},
      "decorations": [
        {{
          "kind": "logo" | "shape" | "image",
          "position": {{"x": 0, "y": 0, "anchor": "top-left"|"center"|"top-center"|"bottom-center"}},
          "size": {{"width": 0, "height": 0}},
          "src": null,
          "fill": null
        }}
      ],
      "text_slots": [
        {{
          "role": "headline" | "subheadline" | "tag" | "footer" | "body" | "description" | "label" | "caption" | "cta_button" | "page_number" | "cell_title_r{{R}}c{{C}}" | "cell_subtitle_r{{R}}c{{C}}" | "cell_description_r{{R}}c{{C}}",
          "position": {{"x": 0, "y": 0, "anchor": "top-left"}},
          "size": {{"width": 0, "height": 0}},
          "style": {{
            "font_size": 0,
            "font_family": "Pretendard",
            "font_weight": "400" | "600" | "700" | "800",
            "fill": "#RRGGBB",
            "text_align": "left" | "center" | "right",
            "line_height": 1.4
          }}
        }}
      ],
      "grid": null OR {{
        "rows": 0, "cols": 0,
        "cell_size": {{"width": 0, "height": 0}},
        "gap_x": 0, "gap_y": 0,
        "origin": {{"x": 0, "y": 0, "anchor": "top-left"}},
        "item_box": {{
          "image_area": {{"x": 0, "y": 0, "width": 0, "height": 0, "border_radius": 0}},
          "title_style": {{...TextStyle...}},
          "title_offset_y": 0,
          "subtitle_style": null OR {{...TextStyle...}},
          "subtitle_offset_y": null,
          "description_style": null OR {{...TextStyle...}},
          "description_offset_y": null
        }}
      }}
    }}
  }}
}}
```

# Allowed layout types
{VALID_LAYOUTS}

# Rules

- Pick the BEST-MATCHING layout for each unique slide kind you see. If multiple \
slides share the same visual structure (e.g. several 2x2 grid pages), define \
that layout ONCE.
- For background images, use a short descriptive English keyword (e.g. \
"yakiniku grill flame", "white marble kitchen") that an image search engine \
would understand. Don't link to the original Instagram CDN URLs.
- For grid layouts, set `text_slots` to [] (per-item text lives in the grid's \
`item_box`). For non-grid layouts, set `grid` to null.
- **For IRREGULAR cell layouts that cannot be described as a uniform rows×cols \
grid** (e.g. zig-zag: cell 0 image top-left + text top-right, cell 1 image \
bottom-right + text bottom-left; or any asymmetric per-cell arrangement):
  1. Set `grid` to `null` (NOT a regular grid).
  2. For each cell, emit text slots with role pattern \
`cell_title_r{R}c{C}`, `cell_subtitle_r{R}c{C}`, `cell_description_r{R}c{C}` \
where `{R}` and `{C}` are the cell's row and column indices in reading order \
(top-to-bottom, left-to-right; both start at 0). The `position` and `size` \
of each slot are the absolute canvas coords of that piece of text — NOT \
offsets within a cell. Example role: `cell_title_r0c1` (first row, second \
column).
  3. For each cell's image area, emit a `decoration` with `kind: "image"` and \
the absolute `position` + `size` of the image rectangle. **List image \
decorations in the same reading order as the cells** — the renderer pairs \
`items[i]` with the i-th cell and the i-th image decoration, so the order \
must match.
  4. Include each cell's title/subtitle/description style in the slot's \
`style` field, exactly like other text_slots.
  Use this pattern ONLY when the cells truly don't form a uniform grid. \
For a regular 2×2 / 1×2 / 2×1 / 3×1 grid, prefer the `grid` block above \
(simpler, fewer slots to author).
- For grid layouts, the per-cell text MUST sit BELOW the image_area inside the \
cell. Concretely: `title_offset_y >= image_area.y + image_area.height + 12`, and \
subtitle/description stack below that. Text must NEVER overlap the image_area.
- For grid layouts, `cell_size.height` MUST be LARGER than `image_area.height` \
by at least enough room for all the text rows (title + subtitle + description) \
plus padding. Never set `cell_size.height` equal to `image_area.height` — that \
pushes the text into the gap between cells where it visually attaches to the \
WRONG image. Typical good ratio: `image_area.height ≈ 65–75% of cell_size.height`.
- The reference design fills the whole canvas. Your grid (or fullbg layout) \
must reach near all FOUR edges of the canvas — top/bottom/left/right. Do NOT \
leave a large empty band at the top or bottom. Symmetric margins are fine \
(e.g. 60px on each side) but huge dead space (>120px) on one edge means you \
shrunk the design too much. Size the grid so that:
  - `origin.x + cols*cell_w + (cols-1)*gap_x + origin.x ≈ canvas_w`
  - `origin.y + rows*cell_h + (rows-1)*gap_y + origin.y ≈ canvas_h`
- Text slots inside the same layout must not overlap each other vertically — \
stack them with at least 8px gap.
- Each `text_slot` and each `decoration` must correspond to a DISTINCT visual \
element actually present in the reference. NEVER emit two slots or two \
decorations at the same `(x, y)` coordinates — no placeholder duplication, no \
"extra empty slots". If you see one logo in the reference, output exactly one \
logo decoration.
- All positions and sizes MUST fit inside the canvas — never let a slot extend \
past the right or bottom edge.
- Do not include any text content (headlines, item names) — those are \
data, not template. Only positions/sizes/styles.
- Output ONLY the JSON. No prose, no markdown fences."""


# ─── Helpers ───

async def _download_slide_images(image_urls: list[str], cache_subdir: str) -> list[str]:
    """Download carousel slide images locally and return the paths."""
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


def _slug(text: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9가-힣_]+", "_", text).strip("_").lower()
    return s or "template"


def _detect_canvas_from_slides(slide_paths: list[str]) -> tuple[int, int, str]:
    """Measure the first slide and snap to an Instagram-standard canvas.

    Reels/posts can be 1:1, 4:5, 9:16, or 1.91:1. We sample the first slide
    (carousel slides share aspect ratio) and pick the closest preset so the
    template covers the whole reference instead of cropping top/bottom.
    """
    for p in slide_paths:
        try:
            with Image.open(p) as img:
                return snap_canvas_to_instagram_preset(img.width, img.height)
        except Exception as e:
            logger.warning("[TemplateStudio] failed to measure slide %s: %s", p, e)
    return snap_canvas_to_instagram_preset(0, 0)


# ─── Core ───

def _apply_cv_overrides(
    raw: dict,
    cv_results: list[SlideAnalysis],
    bg_dict: dict | None,
    bg_kind: str | None,
) -> None:
    """Replace Gemini's guesses with measured CV values, in place.

    1. If any slide yielded a grid, slot that grid into the matching `grid_NxM`
       layout (or `grid_2x2` as the default name in our LayoutType enum).
    2. If the background classifier returned solid/gradient, override the
       background block of all "full-background" layouts and the grid layout's
       background.
    """
    if not cv_results:
        return

    # Pick the cleanest grid: prefer the one with the most cells, tiebreak by
    # smallest gap variance (i.e. most regular).
    grid_candidates = [a.grid for a in cv_results if a.grid]
    chosen = None
    if grid_candidates:
        chosen = max(grid_candidates, key=lambda g: g.rows * g.cols)

    layouts = raw.get("layouts") or {}

    if chosen is not None:
        layout_key = _grid_layout_key(chosen.rows, chosen.cols, layouts)
        if layout_key:
            layout = layouts[layout_key]
            existing_box = (layout.get("grid") or {}).get("item_box") or {}
            canvas = raw.get("canvas") or {}
            cw = int(canvas.get("width") or 1080)
            ch = int(canvas.get("height") or 1350)
            layout["grid"] = _grid_dict_from_cv(chosen, existing_box, cw, ch)
            new_grid = layout["grid"]
            logger.info(
                "[TemplateStudio] CV grid %s fit-to-canvas: %dx%d cell=%dx%d image_ratio=%.2f",
                layout_key, chosen.rows, chosen.cols,
                new_grid["cell_size"]["width"], new_grid["cell_size"]["height"],
                new_grid["item_box"]["image_area"]["height"] / max(1, new_grid["cell_size"]["height"]),
            )

    # Background override — solid/gradient/composite all replace Gemini's guess.
    # For `photo` kind we keep Gemini's image_keyword but STILL merge overlay_*
    # fields from Vision (it may have detected a gradient overlay over the photo).
    has_overlay = bool(bg_dict and bg_dict.get("overlay_kind"))
    if bg_dict is not None and (bg_kind in ("solid", "gradient", "composite") or has_overlay):
        # Vision sometimes omits image_keyword for composite. Fall back to
        # the first non-empty image_keyword seen in Gemini's raw layouts.
        if bg_kind == "composite" and not (bg_dict.get("value") or "").strip():
            fallback_kw = ""
            for ldata in layouts.values():
                if not isinstance(ldata, dict):
                    continue
                cur = ldata.get("background") or {}
                if cur.get("type") in ("image_keyword", "image_path") and (cur.get("value") or "").strip():
                    fallback_kw = cur["value"].strip()
                    break
            if fallback_kw:
                bg_dict["value"] = fallback_kw
                top = bg_dict.get("top")
                if isinstance(top, dict) and not (top.get("value") or "").strip():
                    top["value"] = fallback_kw
                logger.info("[TemplateStudio] composite image_keyword fallback: %r", fallback_kw)
        PHOTO_BG_TYPES = {"image_keyword", "image_path"}
        for lname, ldata in layouts.items():
            if not isinstance(ldata, dict):
                continue
            current = ldata.get("background") or {}
            cur_type = current.get("type")
            if bg_kind == "composite":
                # Replace background entirely with the composite structure
                ldata["background"] = {**current, **bg_dict}
            elif bg_kind == "photo" and has_overlay:
                # Only stamp the overlay on layouts that ACTUALLY have a photo bg
                # (image_keyword / image_path). Skipping solid-color or gradient bg
                # layouts (e.g. phone_mockup with #F5F5F5) keeps the fade off
                # surfaces it doesn't belong on.
                if cur_type in PHOTO_BG_TYPES:
                    overlay_only = {k: v for k, v in bg_dict.items() if k.startswith("overlay_")}
                    ldata["background"] = {**current, **overlay_only}
            elif cur_type in (None, "color", "gradient"):
                ldata["background"] = {**current, **bg_dict}
        logger.info(
            "[TemplateStudio] background override: %s value=%s split_y=%s",
            bg_kind, bg_dict.get("value"), bg_dict.get("split_y"),
        )

    # If Vision detected a composite layout AND Gemini didn't emit a
    # photo_with_caption layout, synthesize a minimal one. Future generate
    # calls will then know this template uses the photo+caption structure.
    if bg_kind == "composite" and "photo_with_caption" not in layouts:
        layouts["photo_with_caption"] = {
            "background": bg_dict,
            "decorations": [],
            "text_slots": [],
            "grid": None,
        }


def _grid_layout_key(rows: int, cols: int, layouts: dict) -> str | None:
    """Map a detected (rows, cols) to one of the known LayoutType keys.

    Falls back to whatever grid-style layout key exists in the Gemini output.
    """
    candidates = [f"grid_{rows}x{cols}"]
    if (rows, cols) == (2, 2):
        candidates.append("grid_2x2")
    if (rows, cols) == (3, 2) or (rows, cols) == (2, 3):
        candidates.extend(["grid_3x2", "grid_2x3"])
    for c in candidates:
        if c in layouts:
            return c
    # Last resort: any layout whose name starts with "grid_"
    for name in layouts:
        if name.startswith("grid_"):
            return name
    return None


STANDARD_MARGIN = 50
STANDARD_GAP = 24


def _grid_dict_from_cv(grid, existing_item_box: dict | None, canvas_w: int, canvas_h: int) -> dict:
    """Build a grid spec from CV detection in a fit-first, ratio-preserving way.

    Step 1 — fit the grid to all four canvas edges with standard margins and
    gaps, computing the cell size by uniform division. This guarantees the
    final design always reaches the canvas edges, regardless of how Gemini
    or the CV detector estimated raw pixel sizes.

    Step 2 — preserve the image_area / cell ratio measured by CV so the
    "photo on top, caption below" balance matches the reference design
    (e.g. CV measured 80% image / 20% text → that ratio survives the resize).
    """
    rows = max(1, grid.rows)
    cols = max(1, grid.cols)

    avail_w = canvas_w - 2 * STANDARD_MARGIN
    avail_h = canvas_h - 2 * STANDARD_MARGIN
    cell_w = max(1, (avail_w - (cols - 1) * STANDARD_GAP) // cols)
    cell_h = max(1, (avail_h - (rows - 1) * STANDARD_GAP) // rows)

    measured_cell_h = max(1, grid.cell_height)
    measured_image_h = max(1, grid.image_area_height)
    ratio_h = min(0.95, max(0.40, measured_image_h / measured_cell_h))
    image_h = int(round(cell_h * ratio_h))
    image_w = cell_w  # span the cell width fully

    item_box = dict(existing_item_box or {})
    item_box["image_area"] = {
        "x": 0,
        "y": 0,
        "width": image_w,
        "height": image_h,
        "border_radius": (item_box.get("image_area") or {}).get("border_radius", 12),
    }
    return {
        "rows": rows,
        "cols": cols,
        "cell_size": {"width": cell_w, "height": cell_h},
        "gap_x": STANDARD_GAP,
        "gap_y": STANDARD_GAP,
        "origin": {"x": STANDARD_MARGIN, "y": STANDARD_MARGIN, "anchor": "top-left"},
        "item_box": item_box,
    }


async def _call_gemini_for_template(
    post_url: str,
    template_name: str,
    template_slug: str,
    layout_hints: list[dict] | None = None,
) -> Template:
    """Fetch post images, call Gemini Vision, validate, return Template."""
    api = InstagramAPI()
    try:
        post = await api.scrape_post(post_url)
    finally:
        await api.close()

    image_urls = post.get("image_urls") or []
    if not image_urls:
        raise ValueError(f"No carousel images found for {post_url}")

    slide_paths = await _download_slide_images(image_urls, cache_subdir=template_slug)
    logger.info(f"[TemplateStudio] {len(slide_paths)} slides downloaded for {template_slug}")

    canvas_w, canvas_h, aspect_label = _detect_canvas_from_slides(slide_paths)
    logger.info(
        "[TemplateStudio] canvas auto-detected: %dx%d (%s) for %s",
        canvas_w, canvas_h, aspect_label, template_slug,
    )

    # Deduplicate: when the user gave layout_hints, only send ONE image per unique
    # layout group to Gemini. The prompt explains the dedup so Gemini knows each
    # representative covers multiple slides.
    rep_indices, dup_map = _pick_representative_indices(layout_hints or [], len(slide_paths))
    vision_paths = [slide_paths[i] for i in rep_indices]
    if layout_hints and len(vision_paths) < len(slide_paths):
        logger.info(
            "[TemplateStudio] layout-hint dedup: %d slides → %d representative images sent to Vision",
            len(slide_paths), len(vision_paths),
        )

    user_prompt = _build_user_prompt(
        template_slug, template_name, len(slide_paths), canvas_w, canvas_h, aspect_label,
        layout_hints=layout_hints,
        dup_map=dup_map if layout_hints else None,
        rep_order=rep_indices if layout_hints else None,
    )
    raw = await gemini_vision(
        image_paths=vision_paths,
        prompt=user_prompt,
        system=SYSTEM_PROMPT,
        model="gemini-3.1-pro",
        json_mode=True,
        max_tokens=32768,
    )

    if isinstance(raw, str):
        raise ValueError(f"Gemini returned non-JSON string: {raw[:300]}")
    if isinstance(raw, list):
        if len(raw) == 1 and isinstance(raw[0], dict):
            raw = raw[0]
        else:
            raise ValueError(f"Gemini returned a list, not a template object: {str(raw)[:300]}")
    if "raw" in raw:
        raise ValueError(f"Gemini returned non-JSON: {raw}")

    raw.setdefault("id", template_slug)
    raw.setdefault("name", template_name)
    raw["created_by"] = "gemini_vision"
    raw["source_post_url"] = post_url
    # Force the canvas we detected — Gemini sometimes ignores the prompt size.
    raw["canvas"] = {"width": canvas_w, "height": canvas_h}

    # ─── CV + Vision background analysis ───
    try:
        cv_results = analyze_slides(slide_paths, canvas_w, canvas_h)
        bg_dict, bg_kind = None, None

        # Prefer Gemini Vision for background classification — pure CV can't tell
        # composite (photo+solid strip) from photo, and can't read gradient stops
        # past simple edge-band averaging. We analyze BOTH the cover slide AND
        # a body slide so we can detect cases where the cover is full-bleed photo
        # but the body slides are photo+caption composites.
        body_vision = None
        cover_vision = None
        if slide_paths:
            cover_vision = await analyze_background_vision(slide_paths[0])
            if len(slide_paths) > 1:
                body_vision = await analyze_background_vision(slide_paths[1])

            # Prefer whichever slide actually has the most structural detail:
            #  1. composite (split_y) > photo with overlay > plain photo
            #  2. between two equals, body slide wins (most content slides match it)
            def _score(v: dict | None) -> int:
                if not v: return 0
                k = v.get("kind")
                if k == "composite": return 3
                if v.get("overlay_kind") in ("solid", "gradient"): return 2
                if k in ("photo", "gradient", "solid"): return 1
                return 0
            cs, bs = _score(cover_vision), _score(body_vision)
            vision = body_vision if bs >= cs else cover_vision
            if vision:
                bg_dict = vision_to_background_dict(vision)
                bg_kind = vision.get("kind")
                logger.info(
                    "[TemplateStudio] bg_vision: cover=%s body=%s → chose %s split_y=%s",
                    (cover_vision or {}).get("kind"),
                    (body_vision or {}).get("kind"),
                    bg_kind,
                    vision.get("split_y"),
                )
            else:
                # Fall back to CV detector + naive gradient analyzer
                first_cv = cv_results[0] if cv_results else None
                if first_cv and first_cv.background_is_uniform:
                    bg_dict = {
                        "type": "color",
                        "value": first_cv.background_hex,
                        "overlay_color": None,
                        "overlay_opacity": 0.0,
                    }
                    bg_kind = "solid"
                else:
                    bp = analyze_background(slide_paths[0])
                    bg_dict = to_background_dict(bp)
                    bg_kind = bp.kind

        _apply_cv_overrides(raw, cv_results, bg_dict, bg_kind)
    except Exception as e:
        logger.warning("[TemplateStudio] CV overrides failed: %s", e)

    # Deterministic post-processing: clamp coords, fix grid text overlap, etc.
    raw = validate_and_fix_template(raw)

    try:
        return Template.model_validate(raw)
    except ValidationError as e:
        logger.error(f"[TemplateStudio] Template validation failed: {e}")
        debug_path = CACHE_DIR / template_slug / "gemini_raw.json"
        debug_path.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
        raise


async def generate_and_save_template(
    db: AsyncSession,
    post_url: str,
    template_name: str,
    user_id: int,
    channel_id: int | None = None,
    template_slug: str | None = None,
    layout_hints: list[dict] | None = None,
) -> CarouselTemplate:
    """Generate a template from a benchmark URL and persist to DB.

    If channel_id is given, sets channel.default_template_id when this is the
    channel's first template.
    """

    slug = template_slug or _slug(template_name)
    template = await _call_gemini_for_template(post_url, template_name, slug, layout_hints=layout_hints)

    # Resolve a unique slug per user (append -2, -3, ...)
    base = slug
    n = 1
    while await db.scalar(
        select(CarouselTemplate.id).where(
            CarouselTemplate.user_id == user_id, CarouselTemplate.slug == slug
        )
    ):
        n += 1
        slug = f"{base}-{n}"

    row = CarouselTemplate(
        user_id=user_id,
        channel_id=channel_id,
        slug=slug,
        name=template_name,
        canvas=template.canvas.model_dump(mode="json"),
        brand=template.brand.model_dump(mode="json"),
        layouts={k.value if hasattr(k, "value") else k: v.model_dump(mode="json") if hasattr(v, "model_dump") else v
                 for k, v in template.layouts.items()},
        source_post_url=post_url,
        created_by="gemini_vision",
    )
    db.add(row)
    await db.flush()  # populate row.id

    # Auto-assign default if channel has no default yet
    if channel_id is not None:
        channel = await db.get(BenchmarkChannel, channel_id)
        if channel and channel.default_template_id is None:
            channel.default_template_id = row.id

    await db.commit()
    await db.refresh(row)
    return row


def template_row_to_dict(row: CarouselTemplate) -> dict:
    return {
        "id": row.id,
        "slug": row.slug,
        "name": row.name,
        "channel_id": row.channel_id,
        "user_id": row.user_id,
        "canvas": row.canvas,
        "brand": row.brand,
        "layouts": row.layouts,
        "source_post_url": row.source_post_url,
        "source_slides": _source_slide_urls(row.slug),
        "created_by": row.created_by,
        "share_code": getattr(row, "share_code", None),
        "is_public": bool(getattr(row, "is_public", False)),
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _source_slide_urls(slug: str) -> list[str]:
    """List cached source-post slides for a template, served as API URLs."""
    if not slug:
        return []
    folder = CACHE_DIR / slug
    if not folder.exists():
        return []
    urls = []
    for f in sorted(folder.glob("slide_*.webp")):
        urls.append(f"/api/images/template-source/{slug}/{f.name}")
    for f in sorted(folder.glob("slide_*.jpg")):
        urls.append(f"/api/images/template-source/{slug}/{f.name}")
    return urls


def template_row_summary(row: CarouselTemplate) -> dict:
    return {
        "id": row.id,
        "slug": row.slug,
        "name": row.name,
        "user_id": row.user_id,
        "channel_id": row.channel_id,
        "created_by": row.created_by,
        "source_post_url": row.source_post_url,
        "source_slides": _source_slide_urls(row.slug),
        "layouts": list((row.layouts or {}).keys()),
        "share_code": getattr(row, "share_code", None),
        "is_public": bool(getattr(row, "is_public", False)),
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


async def list_templates_db(db: AsyncSession, user_id: int) -> list[dict]:
    """All templates visible to a user: own + system (user_id NULL)."""
    result = await db.execute(
        select(CarouselTemplate)
        .where((CarouselTemplate.user_id == user_id) | (CarouselTemplate.user_id.is_(None)))
        .order_by(CarouselTemplate.created_at.desc())
    )
    return [template_row_summary(r) for r in result.scalars().all()]


async def list_channel_templates(db: AsyncSession, channel_id: int) -> list[dict]:
    result = await db.execute(
        select(CarouselTemplate)
        .where(CarouselTemplate.channel_id == channel_id)
        .order_by(CarouselTemplate.created_at.desc())
    )
    return [template_row_summary(r) for r in result.scalars().all()]


async def get_template(db: AsyncSession, template_id: int, user_id: int) -> CarouselTemplate | None:
    """Fetch a single template if visible to the user (own + system)."""
    row = await db.get(CarouselTemplate, template_id)
    if not row:
        return None
    if row.user_id is not None and row.user_id != user_id:
        return None
    return row


async def update_template(
    db: AsyncSession,
    template_id: int,
    user_id: int,
    *,
    name: str | None = None,
    canvas: dict | None = None,
    brand: dict | None = None,
    layouts: dict | None = None,
) -> CarouselTemplate | None:
    """Apply a partial update to a template the user owns.

    System templates (user_id NULL) are read-only; this returns None for them.
    """
    row = await db.get(CarouselTemplate, template_id)
    if not row or row.user_id != user_id:
        return None

    if name is not None:
        row.name = name
    if canvas is not None:
        row.canvas = canvas
    if brand is not None:
        row.brand = brand
    if layouts is not None:
        # Run the same dedupe/clamp/grid-fix used at generate time so edits
        # via PATCH can't reintroduce duplicate-coord slots or off-canvas
        # decorations.
        merged = {
            "canvas": canvas if canvas is not None else (row.canvas or {}),
            "layouts": layouts,
        }
        fixed = validate_and_fix_template(merged)
        row.layouts = fixed["layouts"]
        if canvas is None:
            row.canvas = fixed["canvas"]

    await db.commit()
    await db.refresh(row)
    return row


async def clone_template(
    db: AsyncSession, template_id: int, user_id: int, new_name: str | None = None
) -> CarouselTemplate | None:
    """Copy a template (system, own, or publicly-shared) into a user-owned row."""
    src = await db.get(CarouselTemplate, template_id)
    if not src:
        return None
    # Allowed sources: system templates (user_id NULL), own templates, or
    # any template the owner has marked public via share.
    if (
        src.user_id is not None
        and src.user_id != user_id
        and not getattr(src, "is_public", False)
    ):
        return None

    base_slug = f"{src.slug}-copy"
    slug = base_slug
    n = 1
    while await db.scalar(
        select(CarouselTemplate.id).where(
            CarouselTemplate.user_id == user_id, CarouselTemplate.slug == slug
        )
    ):
        n += 1
        slug = f"{base_slug}-{n}"

    row = CarouselTemplate(
        user_id=user_id,
        channel_id=None,  # copy is not bound to source's channel
        slug=slug,
        name=new_name or f"{src.name} (복제)",
        canvas=dict(src.canvas or {}),
        brand=dict(src.brand or {}),
        layouts=dict(src.layouts or {}),
        source_post_url=src.source_post_url,
        created_by="manual",
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def delete_template(db: AsyncSession, template_id: int, user_id: int) -> bool:
    row = await db.get(CarouselTemplate, template_id)
    # Reject if missing, system-owned (user_id is None — seed/shared, must
    # not be removable via the user API), or owned by someone else.
    # Previously system templates were deletable by any user because the
    # check was `row.user_id is not None and row.user_id != user_id` — a
    # bulk delete from the UI could wipe seed templates for everyone.
    if not row or row.user_id is None or row.user_id != user_id:
        return False

    # Clear any channel that pointed to it as default
    if row.channel_id is not None:
        channel = await db.get(BenchmarkChannel, row.channel_id)
        if channel and channel.default_template_id == template_id:
            channel.default_template_id = None

    await db.delete(row)
    await db.commit()
    return True


# ─── Legacy file-based interface (kept for backward compatibility, used by old API) ───

async def list_templates() -> list[dict]:
    """File-based template summary (legacy). New code should use list_templates_db."""
    items: list[dict] = []
    if not TEMPLATES_DIR.exists():
        return items
    for f in sorted(TEMPLATES_DIR.glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            items.append({
                "id": data.get("id", f.stem),
                "name": data.get("name", f.stem),
                "created_by": data.get("created_by", "manual"),
                "source_post_url": data.get("source_post_url"),
                "layouts": list(data.get("layouts", {}).keys()),
            })
        except Exception as e:
            logger.warning(f"Skipping malformed template {f}: {e}")
    return items


async def generate_template_from_url(
    post_url: str,
    template_name: str,
    template_id: str | None = None,
    save: bool = True,
) -> Template:
    """Legacy file-based generation (kept so existing tests don't break)."""
    template_id = template_id or _slug(template_name)
    template = await _call_gemini_for_template(post_url, template_name, template_id)

    if save:
        out_path = TEMPLATES_DIR / f"{template_id}.json"
        out_path.write_text(
            json.dumps(template.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info(f"[TemplateStudio] saved template → {out_path}")

    return template
