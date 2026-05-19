"""Template specification - describes HOW a blueprint is rendered.

A template defines positions, colors, fonts, and decorations for each layout type.
The renderer consumes (blueprint + template) → Fabric.js canvas JSON.

This is also the output format Gemini Vision produces when analyzing a benchmark post.
"""

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.schemas.carousel_blueprint import LayoutType


class Position(BaseModel):
    x: int
    y: int
    anchor: Literal["top-left", "center", "top-center", "bottom-center"] = "top-left"


class Size(BaseModel):
    width: int
    height: int


class TextStyle(BaseModel):
    font_size: int = 24
    font_family: str = "Pretendard"
    font_weight: str = "normal"
    fill: str = "#000000"
    text_align: Literal["left", "center", "right"] = "left"
    line_height: float = 1.4


class Background(BaseModel):
    type: Literal["color", "image_keyword", "image_path", "gradient", "composite"]
    value: str = ""
    overlay_color: str | None = None
    overlay_opacity: float = 0.0
    # gradient OVERLAY on top of a photo bg (different from `type == gradient`,
    # which means the bg itself IS a gradient). When overlay_kind == "gradient"
    # the renderer draws a gradient rect over the photo instead of a solid one.
    overlay_kind: Literal["solid", "gradient"] | None = None
    overlay_gradient_direction: Literal["vertical", "horizontal", "diagonal"] | None = None
    # list of {offset: 0..1, color: "#RRGGBB", alpha: 0..1}
    overlay_gradient_stops: list[dict] | None = None
    # gradient bg extras (when type == "gradient")
    color_a: str | None = None
    color_b: str | None = None
    direction: Literal["vertical", "horizontal", "diagonal", "none"] | None = None
    # composite extras (photo on top of a solid strip, or vice versa)
    split_y: float | None = None
    top: dict | None = None      # {"type":"image_keyword"|"color","value":"..."}
    bottom: dict | None = None


_STANDARD_ROLES = {
    "headline", "subheadline", "tag", "footer", "body", "description",
    "label", "caption", "cta_button", "page_number",
}
# Per-cell roles used by freeform (non-grid) layouts. Pattern:
# cell_{title|subtitle|description}_r{row}c{col} where row/col are digits.
_CELL_ROLE_RE = re.compile(r"^cell_(title|subtitle|description)_r(\d+)c(\d+)$")


class TextSlot(BaseModel):
    """A slot for slide-level text (or per-cell text in freeform layouts).

    Role is either one of the fixed slide-level names or a `cell_*_r{R}c{C}`
    pattern that addresses an individual cell in a hand-drawn layout. The
    renderer treats those two cases differently (one is slide data, the other
    is a per-item field), but both are valid role identifiers.
    """

    role: str
    position: Position
    size: Size

    @field_validator("role")
    @classmethod
    def _check_role(cls, v: str) -> str:
        if v in _STANDARD_ROLES or _CELL_ROLE_RE.match(v):
            return v
        raise ValueError(
            f"role must be one of {sorted(_STANDARD_ROLES)} or match "
            f"cell_(title|subtitle|description)_r<row>c<col>; got {v!r}"
        )
    style: TextStyle


class Decoration(BaseModel):
    """A static visual element always rendered (logo, frame line, brand tag)."""

    kind: Literal["logo", "shape", "image"]
    position: Position
    size: Size
    src: str | None = None
    fill: str | None = None


class ItemBox(BaseModel):
    """How a single item is laid out inside a grid cell.

    All positions are relative to the item box origin (top-left of the cell).
    """

    image_area: dict = Field(
        default_factory=lambda: {"x": 0, "y": 0, "width": 240, "height": 240, "border_radius": 12}
    )
    title_style: TextStyle = Field(default_factory=TextStyle)
    title_offset_y: int = 260
    subtitle_style: TextStyle | None = None
    subtitle_offset_y: int | None = None
    description_style: TextStyle | None = None
    description_offset_y: int | None = None


class GridSpec(BaseModel):
    rows: int
    cols: int
    cell_size: Size
    gap_x: int = 20
    gap_y: int = 20
    origin: Position
    item_box: ItemBox


class LayoutSpec(BaseModel):
    """Rendering rules for one layout type."""

    background: Background
    decorations: list[Decoration] = Field(default_factory=list)
    text_slots: list[TextSlot] = Field(default_factory=list)
    grid: GridSpec | None = None


class BrandStyle(BaseModel):
    primary_color: str = "#000000"
    background_color: str = "#FFFFFF"
    font_family: str = "Pretendard"
    logo_path: str | None = None


class Template(BaseModel):
    """Full template definition."""

    id: str
    name: str
    canvas: Size = Field(default_factory=lambda: Size(width=1080, height=1350))
    brand: BrandStyle = Field(default_factory=BrandStyle)
    layouts: dict[LayoutType, LayoutSpec] = Field(default_factory=dict)
    source_post_url: str | None = None
    created_by: Literal["manual", "gemini_vision"] = "manual"
