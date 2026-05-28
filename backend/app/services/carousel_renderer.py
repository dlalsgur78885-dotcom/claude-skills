"""Render a content blueprint through a template into Fabric.js canvas JSON.

Inputs:
  - blueprint slides: list of {type, headline, body, subtext, items[], extra} from
    content_extractor / content_gen / user input.
  - template (CarouselTemplate row): canvas, brand, layouts dict.
  - brand overrides (channel-level color/logo) take precedence over template's brand.

Output:
  - list[dict]: each one is a Fabric.js canvas JSON (background + objects[]) suitable
    for storage in GeneratedCarousel.canvas_data.canvas_slides and rendering by the
    CanvasEditor.
"""

import logging
import re
from typing import Any

from app.services.image_search import search_all

# text_slots in user-built templates encode per-cell role + position via the
# pattern `cell_{title|subtitle|description}_r{row}c{col}`. The visual editor
# emits these instead of a `grid` block whenever the layout is hand-drawn
# (e.g. zig-zag) and a regular rows×cols grid can't describe it.
_CELL_ROLE_RE = re.compile(r"^cell_(title|subtitle|description)_r(\d+)c(\d+)$")

logger = logging.getLogger(__name__)


# Order of layouts to try when looking for a matching layout. The first key found
# in the template's `layouts` dict wins.
_LAYOUT_PREFERENCE = {
    # cover slides: prefer photo-on-top + caption-strip layouts, else full-bleed
    "cover": ["photo_with_caption", "fullbg_overlay", "single_image", "text_only"],
    "cta":   ["phone_mockup", "fullbg_overlay", "photo_with_caption", "single_image", "text_only"],
    # grid/list/solo body slides: try grids first, then photo+caption, else fallbacks
    "content_grid":  ["grid_2x2", "grid_3x1", "grid_1x2", "list_vertical", "photo_with_caption", "single_image"],
    # 2-item slides: prefer a paired layout (1×2 or 2×1) over a generic list,
    # otherwise items=2 falls through to fullbg_overlay and no cells render.
    "content_list":  ["grid_1x2", "grid_2x1", "list_vertical", "grid_3x1", "grid_2x2", "photo_with_caption", "single_image"],
    "content_solo":  ["photo_with_caption", "single_image", "fullbg_overlay", "text_only"],
}


def _as_list(value: Any) -> list:
    """Accept legacy single-object layout fields as one-item lists."""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        return [value]
    return []


def _pick_layout(slide: dict, layouts: dict) -> tuple[str, dict] | None:
    """Choose a layout name+spec from the template that fits this slide."""
    items = slide.get("items") or []
    stype = slide.get("type", "content")

    if stype == "cover":
        prefs = _LAYOUT_PREFERENCE["cover"]
    elif stype == "cta":
        prefs = _LAYOUT_PREFERENCE["cta"]
    elif len(items) >= 4:
        prefs = _LAYOUT_PREFERENCE["content_grid"]
    elif 1 <= len(items) <= 3:
        prefs = _LAYOUT_PREFERENCE["content_list"]
    else:
        prefs = _LAYOUT_PREFERENCE["content_solo"]

    for name in prefs:
        if name in layouts:
            return name, layouts[name]
    # last resort: any layout we have
    if layouts:
        first = next(iter(layouts.items()))
        return first
    return None


async def _resolve_background_image(value: str) -> str | None:
    """Search image providers for a single result URL — used when layout.background.type == image_keyword."""
    if not value:
        return None
    try:
        results = await search_all(value, limit=1)
        if results:
            return results[0].source_url or results[0].thumbnail_url or None
    except Exception as e:
        logger.warning(f"[renderer] background search failed for {value!r}: {e}")
    return None


def _hex_to_rgba(hex_color: str, alpha: float) -> str:
    h = (hex_color or "").lstrip("#")
    if len(h) != 6:
        return f"rgba(0,0,0,{alpha})"
    try:
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    except ValueError:
        return f"rgba(0,0,0,{alpha})"
    return f"rgba({r},{g},{b},{alpha})"


def _text_for_slot(role: str, slide: dict) -> str:
    """Map a template text-slot role to a string from the slide content."""
    role = role.lower()
    if role == "tag":
        # Use the badge/pill label specifically; fall back to subtext
        return slide.get("tag") or slide.get("subtext") or ""
    if role in ("headline", "title", "label"):
        return slide.get("headline") or ""
    if role in ("subheadline", "subtitle"):
        return slide.get("subtext") or ""
    if role in ("body", "description", "caption"):
        return slide.get("body") or ""
    if role == "cta_button":
        return slide.get("cta_text") or "팔로우"
    if role == "footer":
        return slide.get("footer") or ""
    if role == "page_number":
        idx = slide.get("index")
        return str(idx + 1) if isinstance(idx, int) else ""
    return ""


def _make_textbox(
    text: str,
    *,
    pos: dict,
    size: dict,
    style: dict,
    canvas_w: int,
    default_font: str,
    over_image: bool = False,
) -> dict:
    """Convert template text slot → Fabric textbox dict."""
    anchor = (pos or {}).get("anchor", "top-left")
    x = float((pos or {}).get("x", 0))
    y = float((pos or {}).get("y", 0))
    w = float((size or {}).get("width", canvas_w))
    if anchor == "top-center" or anchor == "center":
        # x is the center; convert to top-left for Fabric (origin defaults to top-left)
        x = x - w / 2

    fill = (style or {}).get("fill") or "#FFFFFF"
    font_weight = str((style or {}).get("font_weight") or "normal")
    box: dict = {
        "type": "textbox",
        "text": text,
        "left": int(x),
        "top": int(y),
        "width": int(w),
        "fontSize": int((style or {}).get("font_size") or 24),
        "fontFamily": (style or {}).get("font_family") or default_font,
        "fontWeight": font_weight,
        "fill": fill,
        "textAlign": (style or {}).get("text_align") or "left",
        "lineHeight": float((style or {}).get("line_height") or 1.4),
        "originX": "left",
        "originY": "top",
    }
    # Drop shadow when text sits over a photo — readable against any backdrop.
    if over_image:
        is_light = fill.upper() in ("#FFFFFF", "#FFF") or _looks_light(fill)
        shadow_color = "rgba(0,0,0,0.7)" if is_light else "rgba(255,255,255,0.6)"
        box["shadow"] = f"{shadow_color} 0px 2px 6px"
    return box


def _looks_light(hex_color: str) -> bool:
    h = (hex_color or "").lstrip("#")
    if len(h) != 6:
        return True
    try:
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    except ValueError:
        return True
    # Perceived luminance
    return (0.299 * r + 0.587 * g + 0.114 * b) > 160


def _make_rect(left: int, top: int, width: int, height: int, fill: str, opacity: float = 1.0) -> dict:
    return {
        "type": "rect",
        "left": int(left),
        "top": int(top),
        "width": int(width),
        "height": int(height),
        "fill": fill,
        "opacity": float(opacity),
    }


def _make_image(
    src: str,
    *,
    left: int,
    top: int,
    width: int,
    height: int,
    opacity: float = 1.0,
    data: dict | None = None,
) -> dict:
    # `data` round-trips through Fabric as `obj.data` so the editor can recognize
    # user-picked photos and exempt them from the "lock backdrop objects" rule.
    #
    # `_slotL/T/W/H` is the canonical design-space slot box. fabric's image load
    # rewrites left/top/width based on the photo's natural pixel dims + cover-fit
    # math; if the editor's auto-save round-trips those fitted values back into
    # the DB they accumulate drift and cells end up off-canvas after a single
    # mount. The editor uses these to detect "no user move/scale yet" and
    # restore the slot box on save. Set here (not only on grid cells) so the
    # invariant holds for every image the renderer emits.
    merged_data = dict(data or {})
    merged_data.setdefault("_slotL", int(left))
    merged_data.setdefault("_slotT", int(top))
    merged_data.setdefault("_slotW", int(width))
    merged_data.setdefault("_slotH", int(height))
    return {
        "type": "image",
        "src": src,
        "left": int(left),
        "top": int(top),
        "width": int(width),
        "height": int(height),
        "opacity": float(opacity),
        "data": merged_data,
    }


async def render_slide_to_canvas(
    slide: dict,
    layout_name: str,
    layout: dict,
    *,
    canvas_w: int,
    canvas_h: int,
    brand: dict,
    user_image_url: str | None = None,
    skip_background_images: bool = False,
) -> dict:
    """Build the Fabric.js JSON for one slide using the chosen layout."""
    objects: list[dict] = []
    background_color = (layout.get("background") or {}).get("value") if (layout.get("background") or {}).get("type") == "color" else None
    if not background_color:
        background_color = brand.get("background_color") or "#FFFFFF"

    # 1. Background — full-canvas image, composite split, or solid color.
    #    user pick wins for the photo zone. skip_background_images forces text-only.
    bg_spec = layout.get("background") or {}
    bg_type = bg_spec.get("type")
    bg_url = None
    has_photo_bg = False

    if bg_type == "composite" and not skip_background_images:
        # Photo on one zone, solid color strip on the other, split at `split_y`.
        split = bg_spec.get("split_y")
        if not isinstance(split, (int, float)):
            split = 0.75
        split_px = max(0, min(canvas_h, int(canvas_h * float(split))))
        top_spec = bg_spec.get("top") or {}
        bottom_spec = bg_spec.get("bottom") or {}
        # Determine which side holds the photo (default: top)
        top_is_photo = (top_spec.get("type") or "").lower() != "color"

        # Photo zone gets either the user's picked image or the keyword search
        photo_url = user_image_url
        photo_spec = top_spec if top_is_photo else bottom_spec
        if not photo_url:
            if photo_spec.get("type") == "image_keyword":
                photo_url = await _resolve_background_image(
                    photo_spec.get("value") or bg_spec.get("value") or ""
                )
            elif photo_spec.get("type") == "image_path":
                photo_url = photo_spec.get("value")

        photo_marker = {"kind": "user_image", "slide_index": slide.get("index", -1)} if user_image_url else None
        if top_is_photo:
            if photo_url:
                objects.append(_make_image(photo_url, left=0, top=0, width=canvas_w, height=split_px, opacity=1.0, data=photo_marker))
                has_photo_bg = True
            strip_color = (bottom_spec.get("value") or "#FFFFFF")
            objects.append(_make_rect(0, split_px, canvas_w, canvas_h - split_px, strip_color, opacity=1.0))
        else:
            strip_color = (top_spec.get("value") or "#FFFFFF")
            objects.append(_make_rect(0, 0, canvas_w, split_px, strip_color, opacity=1.0))
            if photo_url:
                objects.append(_make_image(photo_url, left=0, top=split_px, width=canvas_w, height=canvas_h - split_px, opacity=1.0, data=photo_marker))
                has_photo_bg = True
    else:
        if not skip_background_images:
            if user_image_url:
                bg_url = user_image_url  # user explicitly picked this in Step 2 — respect it
            elif bg_type == "image_keyword":
                bg_url = await _resolve_background_image(bg_spec.get("value") or "")
            elif bg_type == "image_path":
                bg_url = bg_spec.get("value")

        if bg_url:
            bg_marker = {"kind": "user_image", "slide_index": slide.get("index", -1)} if user_image_url else None
            objects.append(_make_image(bg_url, left=0, top=0, width=canvas_w, height=canvas_h, opacity=1.0, data=bg_marker))
            has_photo_bg = True

    # 2. Background overlay — only meaningful when a photo background is present.
    #    Two flavors:
    #     - solid: a flat tint (overlay_color + overlay_opacity)
    #     - gradient: vertical/horizontal/diagonal fade (overlay_gradient_stops)
    overlay_kind = bg_spec.get("overlay_kind")
    if has_photo_bg and overlay_kind == "gradient":
        stops = bg_spec.get("overlay_gradient_stops") or []
        if stops:
            direction = bg_spec.get("overlay_gradient_direction") or "vertical"
            color_stops = []
            for s in stops:
                c = s.get("color") or "#000000"
                a = float(s.get("alpha") or 0.0)
                color_stops.append({"offset": float(s.get("offset") or 0.0), "color": _hex_to_rgba(c, a)})
            objects.append({
                "type": "rect",
                "left": 0, "top": 0,
                "width": canvas_w, "height": canvas_h,
                "fill": {
                    "type": "linear",
                    "coords": (
                        {"x1": 0, "y1": 0, "x2": canvas_w, "y2": 0} if direction == "horizontal"
                        else {"x1": 0, "y1": 0, "x2": canvas_w, "y2": canvas_h} if direction == "diagonal"
                        else {"x1": 0, "y1": 0, "x2": 0, "y2": canvas_h}
                    ),
                    "colorStops": color_stops,
                },
                "opacity": 1.0,
                "selectable": False,
            })
    else:
        overlay_color = bg_spec.get("overlay_color")
        overlay_opacity = bg_spec.get("overlay_opacity") or 0.0
        if has_photo_bg:
            # Bump too-weak overlays to keep headlines readable
            if not overlay_color or overlay_opacity < 0.35:
                overlay_color = overlay_color or "#000000"
                overlay_opacity = max(overlay_opacity, 0.35)
            if overlay_color and overlay_opacity > 0.001:
                objects.append(_make_rect(0, 0, canvas_w, canvas_h, _hex_to_rgba(overlay_color, overlay_opacity), opacity=1.0))

    # When there's no photo background, flip default text colors that were
    # designed for over-image readability so text stays visible on the brand bg.
    text_on_solid = not has_photo_bg
    bg_is_light = _looks_light(background_color)

    # 3. Decorations (logos / shapes / accent boxes)
    for dec in _as_list(layout.get("decorations")):
        kind = dec.get("kind")
        pos = dec.get("position") or {}
        size = dec.get("size") or {}
        if kind == "logo" and brand.get("logo_path"):
            objects.append(_make_image(
                brand["logo_path"],
                left=int(pos.get("x", 0)), top=int(pos.get("y", 0)),
                width=int(size.get("width", 200)), height=int(size.get("height", 60)),
            ))
        elif kind in ("shape",):
            fill = dec.get("fill") or brand.get("primary_color") or "#FFFFFF"
            objects.append(_make_rect(
                int(pos.get("x", 0)), int(pos.get("y", 0)),
                int(size.get("width", 100)), int(size.get("height", 50)),
                fill, opacity=1.0,
            ))
        elif kind == "image" and dec.get("src"):
            objects.append(_make_image(
                dec["src"],
                left=int(pos.get("x", 0)), top=int(pos.get("y", 0)),
                width=int(size.get("width", 100)), height=int(size.get("height", 100)),
            ))

    # 4. Text slots (slide-level headline/subheadline/...)
    default_font = brand.get("font_family") or "Pretendard"
    for slot in _as_list(layout.get("text_slots")):
        role = slot.get("role", "headline")
        # Per-cell roles (cell_title_r0c1 etc.) are rendered by the freeform
        # cell pass below — skip here so we don't try to read a slide-level
        # field for them.
        if _CELL_ROLE_RE.match(role):
            continue
        text = _text_for_slot(role, slide)
        if not text:
            continue
        style = dict(slot.get("style") or {})
        # Brand color override for accent text slots
        if role in ("tag", "cta_button") and brand.get("primary_color"):
            style["fill"] = brand["primary_color"]
        # Auto-contrast: if no photo bg and the template's fill would be invisible
        # on the solid brand background, flip it to a readable color.
        if text_on_solid:
            cur_fill = (style.get("fill") or "#000000").upper()
            fill_is_light = _looks_light(cur_fill)
            if bg_is_light and fill_is_light:
                style["fill"] = "#1A1A1A"
            elif not bg_is_light and not fill_is_light:
                style["fill"] = "#FFFFFF"
        objects.append(_make_textbox(
            text,
            pos=slot.get("position") or {},
            size=slot.get("size") or {},
            style=style,
            canvas_w=canvas_w,
            default_font=default_font,
            over_image=has_photo_bg,
        ))

    # 5. Grid (per-item cards: image area + title + subtitle + description)
    grid = layout.get("grid")
    items = slide.get("items") or []
    if grid and items:
        rows = int(grid.get("rows", 2))
        cols = int(grid.get("cols", 2))
        cell_size = grid.get("cell_size") or {}
        cell_w = int(cell_size.get("width", 460))
        cell_h = int(cell_size.get("height", 420))
        gap_x = int(grid.get("gap_x", 20))
        gap_y = int(grid.get("gap_y", 20))
        origin = grid.get("origin") or {}
        ox = int(origin.get("x", 60))
        oy = int(origin.get("y", 150))
        item_box = grid.get("item_box") or {}
        ia = item_box.get("image_area") or {}

        for idx, item in enumerate(items[: rows * cols]):
            r = idx // cols
            c = idx % cols
            cell_x = ox + c * (cell_w + gap_x)
            cell_y = oy + r * (cell_h + gap_y)

            # Image area placeholder (real per-item image goes through generation later)
            img_src = item.get("image_path") or item.get("image_url")
            ia_x = cell_x + int(ia.get("x", 0))
            ia_y = cell_y + int(ia.get("y", 0))
            ia_w = int(ia.get("width", cell_w - 40))
            ia_h = int(ia.get("height", 200))
            if img_src:
                # Mark grid-cell photos so the editor lets users move/replace
                # them — same exemption as full-canvas user images.
                objects.append(_make_image(
                    img_src, left=ia_x, top=ia_y, width=ia_w, height=ia_h,
                    data={"kind": "user_item_image", "slide_index": slide.get("index", -1), "item_index": idx},
                ))
            else:
                objects.append(_make_rect(ia_x, ia_y, ia_w, ia_h, "rgba(120,120,120,0.45)"))

            # Title
            title_style = item_box.get("title_style") or {}
            title_off = int(item_box.get("title_offset_y", 220))
            objects.append(_make_textbox(
                item.get("title") or "",
                pos={"x": cell_x, "y": cell_y + title_off, "anchor": "top-left"},
                size={"width": cell_w, "height": 40},
                style=title_style,
                canvas_w=canvas_w,
                default_font=default_font,
                over_image=has_photo_bg,
            ))

            # Subtitle / description rendering with fallback.
            #
            # Vision extraction often populates only one of (subtitle, description)
            # — usually the longer descriptive line ends up in `description` while
            # `subtitle` stays empty. Templates, on the other hand, may define
            # just one of (subtitle_style, description_style). Without a fallback
            # the secondary text per cell silently disappears.
            #
            # Rule: if only one slot exists in the template, route whichever
            # text the item has into that slot. If both slots exist, fill them
            # independently (subtitle ← subtitle, description ← description),
            # falling back to the other field when the matching one is empty.
            sub_style = item_box.get("subtitle_style")
            sub_off = item_box.get("subtitle_offset_y")
            desc_style = item_box.get("description_style")
            desc_off = item_box.get("description_offset_y")
            item_sub = (item.get("subtitle") or "").strip()
            item_desc = (item.get("description") or "").strip()
            has_sub_slot = bool(sub_style and sub_off is not None)
            has_desc_slot = bool(desc_style and desc_off is not None)

            sub_text = item_sub or (item_desc if not has_desc_slot else "")
            desc_text = item_desc or (item_sub if not has_sub_slot else "")

            if has_sub_slot and sub_text:
                objects.append(_make_textbox(
                    sub_text,
                    pos={"x": cell_x, "y": cell_y + int(sub_off), "anchor": "top-left"},
                    size={"width": cell_w, "height": 30},
                    style=sub_style,
                    canvas_w=canvas_w,
                    default_font=default_font,
                    over_image=has_photo_bg,
                ))

            if has_desc_slot and desc_text:
                objects.append(_make_textbox(
                    desc_text,
                    pos={"x": cell_x, "y": cell_y + int(desc_off), "anchor": "top-left"},
                    size={"width": cell_w, "height": 80},
                    style=desc_style,
                    canvas_w=canvas_w,
                    default_font=default_font,
                    over_image=has_photo_bg,
                ))

    # 5b. Freeform cells (hand-drawn layouts without a regular grid block).
    # Used by templates the visual editor builds when the desired cell layout
    # isn't a uniform rows×cols grid (e.g. zig-zag: cell 0 image top-left +
    # text top-right, cell 1 image bottom-right + text bottom-left). Pairs
    # items[i] with the i-th (row, col) entry in text_slots cell roles, and
    # uses the i-th `kind: image` decoration as that cell's image area.
    if not grid and items:
        cell_slots: dict[tuple[int, int], dict] = {}
        for slot in _as_list(layout.get("text_slots")):
            m = _CELL_ROLE_RE.match(slot.get("role") or "")
            if not m:
                continue
            kind = m.group(1)
            r = int(m.group(2))
            c = int(m.group(3))
            cell_slots.setdefault((r, c), {})[kind] = slot
        if cell_slots:
            sorted_cells = [cell_slots[k] for k in sorted(cell_slots.keys())]
            # `kind: image` decorations in array order — one per cell, in the
            # same order the editor placed them. src is usually empty (the
            # decoration just reserves the box); the user-picked photo from
            # step 2 replaces it via item.image_url, just like a grid cell.
            image_decos = [d for d in _as_list(layout.get("decorations")) if d.get("kind") == "image"]
            for idx, item in enumerate(items[: len(sorted_cells)]):
                cell = sorted_cells[idx]
                img_src = item.get("image_path") or item.get("image_url")
                if idx < len(image_decos):
                    dpos = image_decos[idx].get("position") or {}
                    dsize = image_decos[idx].get("size") or {}
                    ia_x = int(dpos.get("x", 0))
                    ia_y = int(dpos.get("y", 0))
                    ia_w = int(dsize.get("width", 300))
                    ia_h = int(dsize.get("height", 300))
                    if img_src:
                        objects.append(_make_image(
                            img_src, left=ia_x, top=ia_y, width=ia_w, height=ia_h,
                            data={"kind": "user_item_image", "slide_index": slide.get("index", -1), "item_index": idx},
                        ))
                    else:
                        objects.append(_make_rect(ia_x, ia_y, ia_w, ia_h, "rgba(120,120,120,0.45)"))
                # Title / subtitle / description — each cell's slot position is
                # already absolute (no offset math needed).
                for cell_kind, item_field, fallback in (
                    ("title", "title", None),
                    ("subtitle", "subtitle", "description"),
                    ("description", "description", "subtitle"),
                ):
                    slot = cell.get(cell_kind)
                    if not slot:
                        continue
                    txt = (item.get(item_field) or "").strip()
                    if not txt and fallback:
                        txt = (item.get(fallback) or "").strip()
                    if not txt:
                        continue
                    objects.append(_make_textbox(
                        txt,
                        pos=slot.get("position") or {},
                        size=slot.get("size") or {},
                        style=slot.get("style") or {},
                        canvas_w=canvas_w,
                        default_font=default_font,
                        over_image=has_photo_bg,
                    ))

    return {
        "version": "6.0.0",
        "width": canvas_w,
        "height": canvas_h,
        "background": background_color,
        "objects": objects,
        "_layout": layout_name,
    }


async def render_carousel(
    *,
    template_canvas: dict,
    template_brand: dict,
    template_layouts: dict,
    slides: list[dict],
    brand_overrides: dict | None = None,
    user_image_urls: dict[int, str] | None = None,
    user_item_image_urls: dict[int, dict[int, str]] | None = None,
    layout_overrides: dict[int, str] | None = None,
    skip_background_images: bool = False,
) -> list[dict]:
    """Top-level entry: render a list of blueprint slides through a template.

    `user_image_urls` maps slide_index → the URL the user picked in Step 2 (or
    None to skip). The renderer uses these as the slide background when the
    template doesn't specify its own background image.

    `user_item_image_urls` maps slide_index → {item_index → url} for grid
    slides where the user picked one image per cell.
    """
    canvas_w = int((template_canvas or {}).get("width", 1080))
    canvas_h = int((template_canvas or {}).get("height", 1080))
    brand = {**(template_brand or {}), **{k: v for k, v in (brand_overrides or {}).items() if v}}
    user_image_urls = user_image_urls or {}
    user_item_image_urls = user_item_image_urls or {}
    layout_overrides = layout_overrides or {}

    # Inject per-cell user images into slide.items so the grid renderer picks
    # them up via the existing `item.image_url` path — no renderer change needed.
    for slide in slides:
        sidx = slide.get("index", -1)
        per_item = user_item_image_urls.get(sidx) or {}
        if not per_item:
            continue
        items = slide.get("items") or []
        for j, it in enumerate(items):
            if not isinstance(it, dict):
                continue
            url = per_item.get(j)
            if url:
                it["image_url"] = url

    out: list[dict] = []
    for slide in slides:
        sidx = slide.get("index", -1)
        # User override beats auto-pick when it points at a real layout the
        # template defines. Unknown names fall through to the auto-picker.
        override = layout_overrides.get(sidx)
        if override and override in (template_layouts or {}):
            picked = (override, template_layouts[override])
        else:
            picked = _pick_layout(slide, template_layouts)
        if not picked:
            logger.warning(f"[renderer] no layout for slide {sidx}")
            continue
        layout_name, layout = picked
        canvas_json = await render_slide_to_canvas(
            slide,
            layout_name,
            layout,
            canvas_w=canvas_w,
            canvas_h=canvas_h,
            brand=brand,
            user_image_url=user_image_urls.get(slide.get("index", -1)),
            skip_background_images=skip_background_images,
        )
        out.append(canvas_json)
    return out
