from pydantic import BaseModel
from datetime import datetime
from typing import Any


class CarouselCreate(BaseModel):
    title: str = ""
    source_post_id: int | None = None
    template_id: str = "minimal"
    canvas_data: dict[str, Any] = {}


class CarouselUpdate(BaseModel):
    title: str | None = None
    canvas_data: dict[str, Any] | None = None
    template_id: str | None = None
    status: str | None = None


class CarouselResponse(BaseModel):
    id: int
    user_id: int
    source_post_id: int | None
    # Instagram URL of the benchmark post this carousel was generated from,
    # populated via the source_post FK. Surfaced in the editor's "원본 링크
    # 보기" button so users can jump back to the reference without leaving
    # the canvas. Null when the carousel was created from scratch (no source).
    source_post_url: str | None = None
    title: str
    canvas_data: dict[str, Any]
    template_id: str
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class OrchestratorRequest(BaseModel):
    """Request to the agent orchestrator."""
    request: str
    context: dict[str, Any] = {}


class OrchestratorResponse(BaseModel):
    """Response from the agent orchestrator."""
    plan_id: str
    goal: str
    status: str
    steps: list[dict[str, Any]]
    evaluation: dict[str, Any] | None
