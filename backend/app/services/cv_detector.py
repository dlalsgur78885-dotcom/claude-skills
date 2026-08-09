"""OpenCV-based template layout detector.

Replaces "let Gemini guess pixel coordinates" with deterministic measurement:

1. Load slide image, snap to canonical canvas (Pillow already does this).
2. Estimate background color from image edges.
3. Threshold image vs background → find large foreground contours.
4. Filter to "image_area-shaped" rectangles (aspect, min size).
5. Group rectangles into rows / columns → grid spec.
6. Map all coordinates back into the canonical canvas coordinate space.

The result is a set of `DetectedRegion` records that the orchestrator hands
to Gemini (for style analysis) and to the assembler (as ground-truth coords).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Literal

import cv2
import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)


@dataclass
class DetectedRegion:
    """A detected rectangular region in canvas coordinates."""

    kind: Literal["image_area", "decoration"]
    x: int
    y: int
    width: int
    height: int


@dataclass
class DetectedGrid:
    """Grid layout inferred from regularly spaced image_area regions."""

    rows: int
    cols: int
    cell_width: int
    cell_height: int
    gap_x: int
    gap_y: int
    origin_x: int
    origin_y: int
    image_area_width: int
    image_area_height: int
    image_area_offset_x: int  # offset of image_area inside the cell (top-left)
    image_area_offset_y: int


@dataclass
class SlideAnalysis:
    canvas_w: int
    canvas_h: int
    background_hex: str
    background_is_uniform: bool   # if False, background is likely a photo or gradient
    regions: list[DetectedRegion]
    grid: DetectedGrid | None


# ─── Background ───

def _estimate_background_color(img_bgr: np.ndarray, edge_band: int = 16) -> tuple[int, int, int]:
    """Estimate background BGR by averaging pixels along the image border."""
    h, w = img_bgr.shape[:2]
    eb = max(2, min(edge_band, h // 6, w // 6))
    top = img_bgr[:eb, :, :].reshape(-1, 3)
    bot = img_bgr[-eb:, :, :].reshape(-1, 3)
    left = img_bgr[:, :eb, :].reshape(-1, 3)
    right = img_bgr[:, -eb:, :].reshape(-1, 3)
    border = np.concatenate([top, bot, left, right], axis=0)
    # Use median (robust to a logo or text at the very edge)
    med = np.median(border, axis=0).astype(int)
    return int(med[0]), int(med[1]), int(med[2])


def _is_uniform_background(img_bgr: np.ndarray, bg_bgr: tuple[int, int, int], tol: int = 20) -> bool:
    """Check how much of the border band is within `tol` of `bg_bgr`."""
    h, w = img_bgr.shape[:2]
    eb = max(2, min(16, h // 6, w // 6))
    bands = [img_bgr[:eb, :, :], img_bgr[-eb:, :, :], img_bgr[:, :eb, :], img_bgr[:, -eb:, :]]
    diffs = []
    for b in bands:
        d = np.abs(b.astype(int) - np.array(bg_bgr)).max(axis=2)
        diffs.append((d < tol).mean())
    return float(np.mean(diffs)) > 0.85


def _bgr_to_hex(b: int, g: int, r: int) -> str:
    return f"#{r:02X}{g:02X}{b:02X}"


# ─── Foreground regions ───

def _foreground_mask(img_bgr: np.ndarray, bg_bgr: tuple[int, int, int], tol: int = 22) -> np.ndarray:
    """Pixels whose color differs from background by more than `tol`."""
    diff = np.abs(img_bgr.astype(int) - np.array(bg_bgr)).max(axis=2)
    return (diff > tol).astype(np.uint8) * 255


def _find_rect_contours(
    mask: np.ndarray, min_area_ratio: float = 0.015
) -> list[tuple[int, int, int, int]]:
    """Find large rectangular contours. Returns list of (x, y, w, h) in image px."""
    h, w = mask.shape[:2]
    total = w * h
    # Close gaps so adjacent boxes don't merge but small noise vanishes.
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    cleaned = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)
    cleaned = cv2.morphologyEx(cleaned, cv2.MORPH_CLOSE, kernel, iterations=1)

    contours, _ = cv2.findContours(cleaned, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    rects: list[tuple[int, int, int, int]] = []
    for c in contours:
        area = cv2.contourArea(c)
        if area < total * min_area_ratio:
            continue
        x, y, rw, rh = cv2.boundingRect(c)
        # Reject extremely thin slivers (text strips, lines).
        if rw < 60 or rh < 60:
            continue
        rects.append((x, y, rw, rh))
    return rects


def _scale_rects(
    rects: list[tuple[int, int, int, int]],
    src_w: int,
    src_h: int,
    dst_w: int,
    dst_h: int,
) -> list[tuple[int, int, int, int]]:
    sx = dst_w / src_w
    sy = dst_h / src_h
    return [
        (int(round(x * sx)), int(round(y * sy)), int(round(w * sx)), int(round(h * sy)))
        for (x, y, w, h) in rects
    ]


# ─── Grid inference ───

def _infer_grid(rects: list[tuple[int, int, int, int]]) -> DetectedGrid | None:
    """If the rects form a regular MxN grid, return its spec — else None.

    Strategy: cluster x-centers into columns and y-centers into rows.
    """
    if len(rects) < 2:
        return None

    centers = [(x + w / 2, y + h / 2, x, y, w, h) for (x, y, w, h) in rects]

    xs = sorted({round(c[0]) for c in centers})
    ys = sorted({round(c[1]) for c in centers})

    # Cluster centers: any two within this many px = same row/col.
    def cluster(values: list[int], tol: int) -> list[int]:
        if not values:
            return []
        clusters: list[list[int]] = [[values[0]]]
        for v in values[1:]:
            if v - clusters[-1][-1] <= tol:
                clusters[-1].append(v)
            else:
                clusters.append([v])
        return [int(round(np.mean(c))) for c in clusters]

    # Use the average rect size as a tolerance.
    avg_w = int(np.mean([r[2] for r in rects]))
    avg_h = int(np.mean([r[3] for r in rects]))
    col_centers = cluster(xs, max(20, avg_w // 3))
    row_centers = cluster(ys, max(20, avg_h // 3))

    cols, rows = len(col_centers), len(row_centers)
    if rows < 1 or cols < 1:
        return None
    # Need at least cols * rows >= len(rects) (each rect maps to a cell).
    if cols * rows < len(rects):
        return None
    # Reject degenerate "single column" runs — those are usually a single big
    # image_area + scattered decorations, not a grid.
    if cols == 1 and rows == 1:
        return None
    if cols * rows == 1:
        return None

    # The detected rects are the IMAGE areas inside each cell — the cell
    # itself usually extends below the rect to hold the per-item caption text.
    # Estimate cell height from the row center spacing minus a small "real" gap.
    image_area_w = avg_w
    image_area_h = avg_h

    SMALL_GAP = 24  # plausible visual gap between cells
    if rows >= 2:
        row_spacing = int(np.mean(np.diff(row_centers)))  # center-to-center
        # cell_h fills almost everything between two rows; reserve SMALL_GAP for gap
        cell_h = max(image_area_h, row_spacing - SMALL_GAP)
        gap_y = max(0, row_spacing - cell_h)
    else:
        cell_h = image_area_h
        gap_y = 0

    if cols >= 2:
        col_spacing = int(np.mean(np.diff(col_centers)))
        cell_w = max(image_area_w, col_spacing - SMALL_GAP)
        gap_x = max(0, col_spacing - cell_w)
    else:
        cell_w = image_area_w
        gap_x = 0

    # Origin: top-left of the top-left rect.
    origin_x = max(0, col_centers[0] - image_area_w // 2)
    origin_y = max(0, row_centers[0] - image_area_h // 2)

    return DetectedGrid(
        rows=rows,
        cols=cols,
        cell_width=cell_w,
        cell_height=cell_h,
        gap_x=gap_x,
        gap_y=gap_y,
        origin_x=origin_x,
        origin_y=origin_y,
        image_area_width=image_area_w,
        image_area_height=image_area_h,
        image_area_offset_x=0,
        image_area_offset_y=0,
    )


# ─── Top-level entry ───

def analyze_slide(image_path: str, canvas_w: int, canvas_h: int) -> SlideAnalysis:
    """Run the full CV pipeline on a single slide and return measured layout."""
    pil = Image.open(image_path).convert("RGB")
    src_w, src_h = pil.size
    img_rgb = np.array(pil)
    img_bgr = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2BGR)

    bg = _estimate_background_color(img_bgr)
    uniform = _is_uniform_background(img_bgr, bg)
    bg_hex = _bgr_to_hex(*bg)

    regions: list[DetectedRegion] = []
    grid: DetectedGrid | None = None

    if uniform:
        mask = _foreground_mask(img_bgr, bg)
        rects = _find_rect_contours(mask)
        scaled = _scale_rects(rects, src_w, src_h, canvas_w, canvas_h)
        # Try to read it as a grid first.
        grid = _infer_grid(scaled)
        if grid is None:
            # No grid — surface the rects as standalone regions
            for (x, y, w, h) in scaled:
                regions.append(DetectedRegion("image_area", x, y, w, h))
        else:
            # Expose the grid cells too (handy for debugging / fallback)
            for r in range(grid.rows):
                for c in range(grid.cols):
                    x = grid.origin_x + c * (grid.cell_width + grid.gap_x)
                    y = grid.origin_y + r * (grid.cell_height + grid.gap_y)
                    regions.append(DetectedRegion("image_area", x, y, grid.cell_width, grid.cell_height))

    return SlideAnalysis(
        canvas_w=canvas_w,
        canvas_h=canvas_h,
        background_hex=bg_hex,
        background_is_uniform=uniform,
        regions=regions,
        grid=grid,
    )


def analyze_slides(image_paths: list[str], canvas_w: int, canvas_h: int) -> list[SlideAnalysis]:
    out: list[SlideAnalysis] = []
    for p in image_paths:
        try:
            out.append(analyze_slide(p, canvas_w, canvas_h))
        except Exception as e:
            logger.warning("[cv_detector] failed on %s: %s", p, e)
    return out
