from datetime import datetime

from pydantic import BaseModel


class ElementImageResponse(BaseModel):
    id: int
    source_url: str
    local_path: str
    thumbnail_url: str
    width: int
    height: int
    rank: int
    source: str
    quality_score: float = 0.0
    url: str = ""

    model_config = {"from_attributes": True}


class ExtractedElementResponse(BaseModel):
    id: int
    post_id: int
    name: str
    search_query: str
    source_text: str
    selected: bool = True
    created_at: datetime
    images: list[ElementImageResponse] = []

    model_config = {"from_attributes": True}


class ElementEditItem(BaseModel):
    id: int | None = None
    name: str
    search_query: str = ""
    selected: bool = True


class ElementsEditRequest(BaseModel):
    elements: list[ElementEditItem]


class PostUsageJobResponse(BaseModel):
    id: int
    post_id: int
    status: str
    stage: str
    error: str
    slide_texts: list[str] = []
    started_at: datetime
    finished_at: datetime | None = None

    model_config = {"from_attributes": True}


class PostElementsResponse(BaseModel):
    job: PostUsageJobResponse | None = None
    elements: list[ExtractedElementResponse] = []
