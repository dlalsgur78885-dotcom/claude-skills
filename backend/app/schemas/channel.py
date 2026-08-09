from pydantic import BaseModel
from datetime import datetime


class ChannelCreate(BaseModel):
    instagram_handle: str
    display_name: str = ""
    category: str = ""
    style_tags: list[str] = []


class ChannelUpdate(BaseModel):
    display_name: str | None = None
    category: str | None = None
    style_tags: list[str] | None = None
    is_active: bool | None = None
    brand_primary_color: str | None = None
    brand_logo_path: str | None = None
    default_template_id: int | None = None


class ChannelResponse(BaseModel):
    id: int
    instagram_handle: str
    display_name: str
    category: str
    style_tags: list[str]
    last_scraped_at: datetime | None
    is_active: bool
    created_at: datetime
    brand_primary_color: str | None = None
    brand_logo_path: str | None = None
    default_template_id: int | None = None

    model_config = {"from_attributes": True}
