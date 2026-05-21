"""Post-process Gemini Vision template output to enforce structural invariants.

Gemini occasionally hallucinates coordinates that fall outside the canvas or
place grid text on top of the cell image. Rather than retry the (expensive)
Vision call, we apply deterministic corrections here so the saved template is
always renderable.

All functions mutate the dict in place AND return it for chaining.
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


INSTAGRAM_ASPECT_PRESETS: list[tuple[float, int, int, str]] = [
    # (target ratio = w/h, canonical W, canonical H, label)
    (1.0,          1080, 1080, "1:1 square"),
    (1080 / 1350,  1080, 1350, "4:5 portrait"),
    (1080 / 1920,  1080, 1920, "9:16 story/reel"),
    (1.91,         2160, 1130, "1.91:1 landscape"),
]


def snap_canvas_to_instagram_preset(
    img_width: int, img_height: int, *, fallback: tuple[int, int] = (1080, 1350)
) -> tuple[int, int, str]:
    """Snap a measured image size to the nearest Instagram-canonical canvas.

    Returns (W, H, preset_label). If width/height are missing or non-positive,
    returns the fallback (default: 4:5 portrait, currently the most common IG
    carousel format).
    """
    if not img_width or not img_height or img_width <= 0 or img_height <= 0:
        return (*fallback, "fallback")

    ratio = img_width / img_height
    best = min(INSTAGRAM_ASPECT_PRESETS, key=lambda p: abs(ratio - p[0]))
    return best[1], best[2], best[3]


def _clamp(v: int | float, lo: int | float, hi: int | float) -> int:
    return int(max(lo, min(hi, v)))


def validate_and_fix_template(template: dict[str, Any]) -> dict[str, Any]:
    """Apply all structural corrections to a Gemini-generated template dict.

    Order matters: canvas first (everything else clamps to canvas), then per-layout
    fixes. Returns the same dict for fluent use.
    """
    canvas = template.get("canvas") or {}
    W = int(canvas.get("width") or 1080)
    H = int(canvas.get("height") or 1350)
    template["canvas"] = {"width": W, "height": H}

    layouts = template.get("layouts") or {}
    for layout_name, layout in layouts.items():
        if not isinstance(layout, dict):
            continue
        _normalize_background_type(layout, layout_name)
        _dedupe_decorations(layout, layout_name)
        _dedupe_text_slots(layout, layout_name)
        _fix_decorations(layout, W, H, layout_name)
        _fix_text_slots(layout, W, H, layout_name)
        _fix_grid(layout, W, H, layout_name)

    return template


def _normalize_background_type(layout: dict, layout_name: str) -> None:
    """If the background has split_y + top/bottom but its type isn't `composite`,
    fix it. This guards against PATCHes that came in before the editor knew
    about the "composite" option (and clones that inherited the wrong type)."""
    bg = layout.get("background") or {}
    if not isinstance(bg, dict):
        return
    has_split = isinstance(bg.get("split_y"), (int, float))
    has_top_bottom = isinstance(bg.get("top"), dict) and isinstance(bg.get("bottom"), dict)
    if (has_split or has_top_bottom) and bg.get("type") != "composite":
        logger.info(
            "[validator/%s] background type %r → composite (had split_y/top/bottom)",
            layout_name, bg.get("type"),
        )
        bg["type"] = "composite"
        layout["background"] = bg


def _dedupe_decorations(layout: dict, layout_name: str) -> None:
    """Drop decorations that share kind + position + size — Gemini sometimes
    emits the same placeholder shape/logo many times at identical coords."""
    seen: set[tuple] = set()
    out: list[dict] = []
    for d in layout.get("decorations") or []:
        pos = d.get("position") or {}
        size = d.get("size") or {}
        # `fill` may be a gradient object (dict) — dicts are unhashable and
        # would crash `key in seen`. Normalize a dict fill to a stable JSON
        # string so two identical gradients still dedupe to the same key.
        fill = d.get("fill")
        fill_key = json.dumps(fill, sort_keys=True) if isinstance(fill, dict) else fill
        key = (
            d.get("kind"),
            int(pos.get("x", 0) or 0),
            int(pos.get("y", 0) or 0),
            int(size.get("width", 0) or 0),
            int(size.get("height", 0) or 0),
            fill_key,
            d.get("src"),
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(d)
    dropped = len(layout.get("decorations") or []) - len(out)
    if dropped:
        logger.info("[validator/%s] dropped %d duplicate decoration(s)", layout_name, dropped)
    layout["decorations"] = out


def _dedupe_text_slots(layout: dict, layout_name: str) -> None:
    """Drop text_slots that share role + position + size. Gemini sometimes
    emits the same placeholder slot multiple times — keep only the first."""
    seen: set[tuple] = set()
    out: list[dict] = []
    for s in layout.get("text_slots") or []:
        pos = s.get("position") or {}
        size = s.get("size") or {}
        key = (
            s.get("role"),
            int(pos.get("x", 0) or 0),
            int(pos.get("y", 0) or 0),
            int(size.get("width", 0) or 0),
            int(size.get("height", 0) or 0),
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(s)
    dropped = len(layout.get("text_slots") or []) - len(out)
    if dropped:
        logger.info("[validator/%s] dropped %d duplicate text_slot(s)", layout_name, dropped)
    layout["text_slots"] = out


def _fix_decorations(layout: dict, W: int, H: int, layout_name: str) -> None:
    for d in layout.get("decorations") or []:
        _normalize_anchor(d)
        pos = d.get("position") or {}
        size = d.get("size") or {}
        x = _clamp(pos.get("x", 0) or 0, 0, W)
        y = _clamp(pos.get("y", 0) or 0, 0, H)
        w = _clamp(size.get("width", 0) or 0, 0, W - x)
        h = _clamp(size.get("height", 0) or 0, 0, H - y)
        d["position"] = {**pos, "x": x, "y": y}
        d["size"] = {**size, "width": w, "height": h}


def _normalize_anchor(item: dict) -> None:
    """Convert anchored coords ("center"/"top-center"/"bottom-center") to
    canonical top-left so every renderer treats `(x, y)` as the top-left corner
    of the slot's box. Mutates `item` in place.

    Gemini frequently outputs `anchor: "center"` with `x = canvas_w / 2` to
    mean "horizontally centered" — without this shift, the slot would render
    starting at the canvas midpoint and spill off the right edge.
    """
    pos = item.get("position") or {}
    size = item.get("size") or {}
    anchor = pos.get("anchor")
    if anchor in (None, "top-left"):
        return
    x = pos.get("x", 0) or 0
    y = pos.get("y", 0) or 0
    w = size.get("width", 0) or 0
    h = size.get("height", 0) or 0
    if anchor == "center":
        x, y = x - w // 2, y - h // 2
    elif anchor == "top-center":
        x = x - w // 2
    elif anchor == "bottom-center":
        x, y = x - w // 2, y - h
    else:
        return
    pos["x"] = int(x)
    pos["y"] = int(y)
    pos["anchor"] = "top-left"


def _fix_text_slots(layout: dict, W: int, H: int, layout_name: str) -> None:
    """Clamp text slot positions to canvas. Then de-overlap stacked slots."""
    slots = layout.get("text_slots") or []
    cleaned: list[dict] = []
    for s in slots:
        _normalize_anchor(s)
        pos = s.get("position") or {}
        size = s.get("size") or {}
        x = _clamp(pos.get("x", 0) or 0, 0, W - 1)
        y = _clamp(pos.get("y", 0) or 0, 0, H - 1)
        w = _clamp(size.get("width", 100) or 100, 50, W - x)
        h = _clamp(size.get("height", 60) or 60, 20, max(20, H - y))
        s["position"] = {**pos, "x": x, "y": y}
        s["size"] = {**size, "width": w, "height": h}
        cleaned.append(s)

    # Detect roughly-stacked headlines/body that overlap and push them down.
    # Two slots "overlap vertically" if their x-ranges share >50% AND their
    # y-ranges share >0px.
    cleaned.sort(key=lambda s: s["position"]["y"])
    for i in range(1, len(cleaned)):
        prev = cleaned[i - 1]
        cur = cleaned[i]
        if _x_overlap_ratio(prev, cur) > 0.5:
            prev_bottom = prev["position"]["y"] + prev["size"]["height"]
            if cur["position"]["y"] < prev_bottom + 4:
                shift = prev_bottom + 8 - cur["position"]["y"]
                new_y = _clamp(cur["position"]["y"] + shift, 0, H - cur["size"]["height"])
                cur["position"]["y"] = new_y
                logger.debug(
                    "[validator/%s] shifted text_slot %s by %dpx to avoid overlap",
                    layout_name, cur.get("role"), shift,
                )


def _x_overlap_ratio(a: dict, b: dict) -> float:
    ax1 = a["position"]["x"]
    ax2 = ax1 + a["size"]["width"]
    bx1 = b["position"]["x"]
    bx2 = bx1 + b["size"]["width"]
    overlap = max(0, min(ax2, bx2) - max(ax1, bx1))
    span = min(a["size"]["width"], b["size"]["width"]) or 1
    return overlap / span


def _fix_grid(layout: dict, W: int, H: int, layout_name: str) -> None:
    """Clamp grid to canvas and ensure cell text sits below the image area.

    Coordinates inside `item_box` are LOCAL to the cell (top-left of cell = 0,0).
    So `title_offset_y >= image_area.y + image_area.height + padding`.
    """
    g = layout.get("grid")
    if not isinstance(g, dict):
        return

    cell = g.get("cell_size") or {}
    cw = max(1, int(cell.get("width") or 1))
    ch = max(1, int(cell.get("height") or 1))
    g["cell_size"] = {"width": cw, "height": ch}

    origin = g.get("origin") or {}
    g["origin"] = {
        **origin,
        "x": _clamp(origin.get("x", 0) or 0, 0, W),
        "y": _clamp(origin.get("y", 0) or 0, 0, H),
    }

    box = g.get("item_box") or {}
    img_area = box.get("image_area") or {}
    iax = _clamp(img_area.get("x", 0) or 0, 0, cw)
    iay = _clamp(img_area.get("y", 0) or 0, 0, ch)
    iaw = _clamp(img_area.get("width", cw) or cw, 1, cw - iax)
    iah = _clamp(img_area.get("height", ch) or ch, 1, ch - iay)
    img_area.update({"x": iax, "y": iay, "width": iaw, "height": iah})
    box["image_area"] = img_area

    # Text inside the cell MUST sit below the image area (or above, but the
    # current schema only supports below via offset_y).
    PADDING = 12
    min_y = iay + iah + PADDING

    title_y = box.get("title_offset_y")
    if title_y is None or title_y < min_y:
        if title_y is not None and title_y < min_y:
            logger.info(
                "[validator/%s] grid title_offset_y %s → %d (was overlapping image_area)",
                layout_name, title_y, min_y,
            )
        box["title_offset_y"] = min_y
        title_y = min_y

    # Stack subtitle/description below title using their font sizes as approximate row height.
    next_y = title_y + _row_h(box.get("title_style"))
    sub_y = box.get("subtitle_offset_y")
    if box.get("subtitle_style") is not None:
        if sub_y is None or sub_y < next_y:
            box["subtitle_offset_y"] = next_y
            sub_y = next_y
        next_y = sub_y + _row_h(box.get("subtitle_style"))

    desc_y = box.get("description_offset_y")
    if box.get("description_style") is not None:
        if desc_y is None or desc_y < next_y:
            box["description_offset_y"] = next_y

    # Ensure cell is tall enough for image_area + all text rows.
    # If Gemini set cell.height == image_area.height the text spills into the
    # gap between cells and visually attaches to the NEXT cell's image, which
    # breaks the "text directly under its image" requirement.
    text_bottom = box["title_offset_y"] + _row_h(box.get("title_style"))
    if box.get("subtitle_offset_y") is not None:
        text_bottom = max(
            text_bottom,
            box["subtitle_offset_y"] + _row_h(box.get("subtitle_style")),
        )
    if box.get("description_offset_y") is not None:
        text_bottom = max(
            text_bottom,
            box["description_offset_y"] + _row_h(box.get("description_style")),
        )
    needed_ch = text_bottom + PADDING
    if ch < needed_ch:
        logger.info(
            "[validator/%s] grid cell.height %d → %d so text fits under image",
            layout_name, ch, needed_ch,
        )
        ch = needed_ch
        g["cell_size"]["height"] = ch

    # Fit grid to canvas 4 edges: extend cell.height so grid bottom reaches
    # canvas bottom with symmetric top/bottom margin (= origin.y). Keep the
    # image_area scaling proportional so the photo grows with the cell.
    rows = max(1, int(g.get("rows") or 1))
    gap_y = int(g.get("gap_y") or 0)
    origin_y = g["origin"]["y"]
    # If Gemini set a huge top margin, the grid can never reach the bottom edge
    # symmetrically. Cap origin.y at MAX_MARGIN so we have room to extend cells.
    MAX_MARGIN = 80
    if origin_y > MAX_MARGIN:
        logger.info(
            "[validator/%s] grid origin.y %d → %d (cap top margin)",
            layout_name, origin_y, MAX_MARGIN,
        )
        origin_y = MAX_MARGIN
        g["origin"]["y"] = MAX_MARGIN
    target_grid_h = H - 2 * origin_y
    if target_grid_h > 0 and rows > 0:
        target_ch = (target_grid_h - (rows - 1) * gap_y) // rows
        if target_ch > ch:
            scale = target_ch / ch if ch else 1
            new_iah = max(1, int(iah * scale))
            shift = new_iah - iah
            logger.info(
                "[validator/%s] grid fit-to-canvas: cell.h %d → %d, image_area.h %d → %d",
                layout_name, ch, target_ch, iah, new_iah,
            )
            img_area["height"] = new_iah
            box["title_offset_y"] += shift
            if box.get("subtitle_offset_y") is not None:
                box["subtitle_offset_y"] += shift
            if box.get("description_offset_y") is not None:
                box["description_offset_y"] += shift
            ch = target_ch
            g["cell_size"]["height"] = ch
            iah = new_iah

    layout["grid"] = {**g, "item_box": box}


def _row_h(style: dict | None) -> int:
    if not isinstance(style, dict):
        return 28
    fs = int(style.get("font_size") or 18)
    lh = float(style.get("line_height") or 1.4)
    return int(fs * lh) + 4
