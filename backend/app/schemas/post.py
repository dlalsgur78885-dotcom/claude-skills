from pydantic import BaseModel
from datetime import datetime


class PostResponse(BaseModel):
    id: int
    channel_id: int
    instagram_post_id: str
    post_url: str
    caption: str
    hashtags: list[str]
    post_date: datetime | None
    like_count: int
    comment_count: int
    slide_count: int
    is_video: bool = False
    collected_at: datetime
    saved_at: datetime | None = None
    images: list["PostImageResponse"] = []

    model_config = {"from_attributes": True}


class PostImageResponse(BaseModel):
    id: int
    slide_index: int
    raw_path: str
    source_url: str = ""  # Original Instagram CDN URL; UI falls back here when raw_path 404s
    processed_path: str
    width: int
    height: int

    model_config = {"from_attributes": True}
