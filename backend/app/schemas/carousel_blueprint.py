"""Carousel content blueprint - the canonical data shape passed between pipeline steps.

The blueprint describes WHAT goes into a carousel (text, items, image keywords).
A template describes HOW it is rendered (positions, colors, fonts).

Same blueprint + different template = different visual style for the same content.
"""

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class SlideType(str, Enum):
    cover = "cover"
    content = "content"
    cta = "cta"


class LayoutType(str, Enum):
    fullbg_overlay = "fullbg_overlay"
    grid_2x2 = "grid_2x2"
    grid_3x1 = "grid_3x1"
    grid_1x2 = "grid_1x2"
    # Every rows×cols combo the template-studio grid dropdown offers must exist
    # here — Template.layouts keys are validated against this enum, so a missing
    # member 400s the whole AI analysis (feedback slide: grid_3x3/grid_2x3).
    grid_2x1 = "grid_2x1"
    grid_2x3 = "grid_2x3"
    grid_3x2 = "grid_3x2"
    grid_3x3 = "grid_3x3"
    grid_1x3 = "grid_1x3"
    list_vertical = "list_vertical"
    single_image = "single_image"
    phone_mockup = "phone_mockup"
    text_only = "text_only"
    photo_with_caption = "photo_with_caption"


class Item(BaseModel):
    """A single content unit inside a slide (e.g., one yakiniku cut, one travel spot)."""

    title: str
    subtitle: str | None = None
    description: str = ""
    image_keyword: str = ""
    image_path: str | None = None
    extra: dict[str, str] = Field(default_factory=dict)


class Slide(BaseModel):
    type: SlideType
    layout: LayoutType
    headline: str = ""
    subheadline: str = ""
    tag: str = ""
    bg_keyword: str = ""
    bg_image_path: str | None = None
    items: list[Item] = Field(default_factory=list)
    extra: dict[str, Any] = Field(default_factory=dict)


class Brand(BaseModel):
    name: str = ""
    handle: str = ""
    logo_path: str | None = None
    primary_color: str | None = None


class CarouselBlueprint(BaseModel):
    """Canonical carousel content. Read/written by every pipeline step."""

    topic: str
    brand: Brand = Field(default_factory=Brand)
    slides: list[Slide] = Field(default_factory=list)
    source_post_url: str | None = None
    source_channel_id: int | None = None
