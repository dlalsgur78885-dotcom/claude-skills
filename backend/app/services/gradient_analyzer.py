"""Analyze a slide's background structure: solid / gradient / photo / composite.

A "composite" slide is one where the canvas is vertically split into two
distinct zones — typically a photo on top and a solid caption strip on the
bottom (the most common Instagram travel-card layout). The previous version
of this module only looked at the 4 edge bands and so always classified those
slides as "photo", missing the bottom solid strip entirely.

This rewrite samples ROW-BY-ROW across the full canvas, then clusters rows
by their (mean color, variance) signature. The clustering result tells us:

  - All rows uniform color → solid
  - Rows smoothly transition top→bottom in mean color → gradient
  - Some rows uniform + some chaotic, with a clean boundary → composite
  - All rows chaotic → photo

For composite, we also return `split_y` (the row index where the boundary
sits) and the solid color of the caption strip.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Literal

import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)


@dataclass
class BackgroundProfile:
    kind: Literal["solid", "gradient", "photo", "composite"]
    color_a: str | None = None          # solid: the color; gradient: top/left endpoint; composite: photo-side dominant
    color_b: str | None = None          # gradient bottom/right endpoint; composite: solid-strip color
    direction: Literal["vertical", "horizontal", "diagonal", "none"] = "none"
    # Composite-only: fractional y where the photo ends and the solid strip starts (0.0-1.0)
    split_y: float | None = None


def _rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    return f"#{rgb[0]:02X}{rgb[1]:02X}{rgb[2]:02X}"


def _strip_signature(strip: np.ndarray) -> tuple[tuple[int, int, int], float]:
    """Robust per-strip color signature.

    Returns (median_rgb, spread) where spread is the mean absolute deviation
    from the median. Median is robust against small overlaid text (5-15% of
    pixels) so a "white background with a few black text pixels" still reads
    as uniform white.
    """
    median = np.median(strip, axis=0)
    spread = float(np.mean(np.abs(strip.astype(np.int16) - median.astype(np.int16))))
    return ((int(median[0]), int(median[1]), int(median[2])), spread)


def _row_stats(arr: np.ndarray, rows: int = 24) -> list[tuple[tuple[int, int, int], float]]:
    """Sample `rows` horizontal strips top→bottom. Return (median_rgb, spread) per strip."""
    h, w = arr.shape[:2]
    out: list[tuple[tuple[int, int, int], float]] = []
    for i in range(rows):
        y0 = (h * i) // rows
        y1 = max(y0 + 1, (h * (i + 1)) // rows)
        strip = arr[y0:y1, :, :].reshape(-1, 3)
        out.append(_strip_signature(strip))
    return out


def _col_stats(arr: np.ndarray, cols: int = 24) -> list[tuple[tuple[int, int, int], float]]:
    h, w = arr.shape[:2]
    out: list[tuple[tuple[int, int, int], float]] = []
    for i in range(cols):
        x0 = (w * i) // cols
        x1 = max(x0 + 1, (w * (i + 1)) // cols)
        strip = arr[:, x0:x1, :].reshape(-1, 3)
        out.append(_strip_signature(strip))
    return out


def _color_dist(a: tuple[int, int, int], b: tuple[int, int, int]) -> float:
    return float(max(abs(a[0] - b[0]), abs(a[1] - b[1]), abs(a[2] - b[2])))


# Tuning constants in MAD (mean-absolute-deviation from median) units, 0-255 RGB scale.
# Uniform color strips (even with overlaid text on them) sit under ~14;
# photo strips with rich color variation sit above ~28.
UNIFORM_SPREAD = 14.0
PHOTO_SPREAD = 28.0


def analyze_background(image_path: str) -> BackgroundProfile:
    """Classify the background structure of a single slide."""
    pil = Image.open(image_path).convert("RGB")
    arr = np.array(pil)

    rows = _row_stats(arr, rows=24)
    cols = _col_stats(arr, cols=24)

    # ─── 1. Per-row signature: how many rows are uniform? ───
    uniform_flags = [v < UNIFORM_SPREAD for (_, v) in rows]
    photo_flags = [v > PHOTO_SPREAD for (_, v) in rows]
    u_count = sum(uniform_flags)
    p_count = sum(photo_flags)
    n = len(rows)

    # ─── 2. Solid: all rows uniform AND similar colors ───
    if u_count == n:
        mean_colors = [c for (c, _) in rows]
        first = mean_colors[0]
        if all(_color_dist(first, c) < 18 for c in mean_colors):
            avg = (
                sum(c[0] for c in mean_colors) // n,
                sum(c[1] for c in mean_colors) // n,
                sum(c[2] for c in mean_colors) // n,
            )
            return BackgroundProfile(kind="solid", color_a=_rgb_to_hex(avg))

    # ─── 3. Composite: bottom (or top) is a uniform color strip, the rest is photo ───
    # Find the longest run of consecutive uniform rows at the top or bottom.
    def longest_run(flags: list[bool], from_end: bool) -> int:
        seq = flags[::-1] if from_end else flags
        run = 0
        for f in seq:
            if f:
                run += 1
            else:
                break
        return run

    bot_uniform = longest_run(uniform_flags, from_end=True)
    top_uniform = longest_run(uniform_flags, from_end=False)
    # photos in the middle = at least half non-uniform AND the boundary contiguous
    if bot_uniform >= 3 and p_count >= 4:
        # confirm the strip color is consistent
        strip_rows = rows[-bot_uniform:]
        strip_colors = [c for (c, _) in strip_rows]
        if all(_color_dist(strip_colors[0], c) < 18 for c in strip_colors):
            avg = (
                sum(c[0] for c in strip_colors) // len(strip_colors),
                sum(c[1] for c in strip_colors) // len(strip_colors),
                sum(c[2] for c in strip_colors) // len(strip_colors),
            )
            # photo side: take the middle row's color as a rough hint
            photo_mid = rows[n // 4][0]
            split_y = (n - bot_uniform) / n
            return BackgroundProfile(
                kind="composite",
                color_a=_rgb_to_hex(photo_mid),
                color_b=_rgb_to_hex(avg),
                direction="vertical",
                split_y=round(split_y, 3),
            )
    if top_uniform >= 3 and p_count >= 4:
        strip_rows = rows[:top_uniform]
        strip_colors = [c for (c, _) in strip_rows]
        if all(_color_dist(strip_colors[0], c) < 18 for c in strip_colors):
            avg = (
                sum(c[0] for c in strip_colors) // len(strip_colors),
                sum(c[1] for c in strip_colors) // len(strip_colors),
                sum(c[2] for c in strip_colors) // len(strip_colors),
            )
            photo_mid = rows[-(n // 4)][0]
            # split_y is where the SOLID strip ends (top variant)
            split_y = top_uniform / n
            return BackgroundProfile(
                kind="composite",
                color_a=_rgb_to_hex(avg),
                color_b=_rgb_to_hex(photo_mid),
                direction="vertical",
                split_y=round(split_y, 3),
            )

    # ─── 4. Gradient: all rows low/mid variance + monotonic color change ───
    if p_count == 0 and u_count + sum(UNIFORM_SPREAD <= v <= PHOTO_SPREAD for (_, v) in rows) == n:
        first_row, last_row = rows[0][0], rows[-1][0]
        first_col, last_col = cols[0][0], cols[-1][0]
        d_vert = _color_dist(first_row, last_row)
        d_horiz = _color_dist(first_col, last_col)
        if d_vert >= 20 and d_horiz < 12:
            return BackgroundProfile(
                kind="gradient",
                color_a=_rgb_to_hex(first_row),
                color_b=_rgb_to_hex(last_row),
                direction="vertical",
            )
        if d_horiz >= 20 and d_vert < 12:
            return BackgroundProfile(
                kind="gradient",
                color_a=_rgb_to_hex(first_col),
                color_b=_rgb_to_hex(last_col),
                direction="horizontal",
            )
        if d_vert >= 20 and d_horiz >= 20:
            return BackgroundProfile(
                kind="gradient",
                color_a=_rgb_to_hex(rows[0][0]),
                color_b=_rgb_to_hex(rows[-1][0]),
                direction="diagonal",
            )

    # ─── 5. Fallback: photo ───
    return BackgroundProfile(kind="photo")


def to_background_dict(profile: BackgroundProfile) -> dict:
    """Convert a BackgroundProfile into the Template `background` JSON shape.

    For `composite`, we emit a structured dict the renderer understands —
    photo on top, solid strip on the bottom (or vice versa).
    """
    if profile.kind == "solid":
        return {
            "type": "color",
            "value": profile.color_a or "#FFFFFF",
            "overlay_color": None,
            "overlay_opacity": 0.0,
        }
    if profile.kind == "gradient":
        a = profile.color_a or "#FFFFFF"
        b = profile.color_b or "#000000"
        return {
            "type": "gradient",
            "value": f"{a}→{b} {profile.direction}",
            "color_a": a,
            "color_b": b,
            "direction": profile.direction,
            "overlay_color": None,
            "overlay_opacity": 0.0,
        }
    if profile.kind == "composite":
        return {
            "type": "composite",
            "value": "",
            "split_y": profile.split_y,
            "top": {"type": "image_keyword", "value": ""},  # filled in by Gemini style step
            "bottom": {"type": "color", "value": profile.color_b or "#FFFFFF"},
            "overlay_color": None,
            "overlay_opacity": 0.0,
        }
    # photo
    return {
        "type": "image_keyword",
        "value": "",
        "overlay_color": None,
        "overlay_opacity": 0.0,
    }
