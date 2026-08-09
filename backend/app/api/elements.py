"""'쓸게요' pipeline triggers and result endpoints."""

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.auth import get_current_user
from app.database import get_db
from app.models.channel import BenchmarkChannel
from app.models.element import ExtractedElement, PostUsageJob
from app.models.post import CollectedPost
from app.models.user import User
from app.schemas.element import (
    ElementImageResponse,
    ElementsEditRequest,
    ExtractedElementResponse,
    PostElementsResponse,
    PostUsageJobResponse,
)
from app.services.use_post import run_analyze, run_collect


def _pool_url(local_path: str) -> str:
    """Convert a local_path like '.../data/images/pool/{post}/{element_dir}/{file}' → API URL."""
    if not local_path:
        return ""
    parts = local_path.replace("\\", "/").split("/")
    try:
        idx = len(parts) - 1 - parts[::-1].index("pool")
    except ValueError:
        return ""
    tail = parts[idx + 1: idx + 4]
    if len(tail) != 3:
        return ""
    return f"/api/images/pool/{tail[0]}/{tail[1]}/{tail[2]}"

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/posts", tags=["elements"])


async def _post_belongs_to_user(db: AsyncSession, post_id: int, user_id: int) -> CollectedPost | None:
    result = await db.execute(
        select(CollectedPost)
        .join(BenchmarkChannel)
        .where(CollectedPost.id == post_id, BenchmarkChannel.user_id == user_id)
    )
    return result.scalar_one_or_none()


@router.post("/{post_id}/use", response_model=PostUsageJobResponse, status_code=202)
async def trigger_use_post(
    post_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Kick off the '쓸게요' pipeline for a post (async, fire-and-forget)."""
    post = await _post_belongs_to_user(db, post_id, user.id)
    if not post:
        raise HTTPException(status_code=404, detail="포스트를 찾을 수 없습니다")

    result = await db.execute(
        select(PostUsageJob).where(PostUsageJob.post_id == post_id)
    )
    job = result.scalar_one_or_none()
    if job and job.status == "running":
        return job

    if not job:
        job = PostUsageJob(post_id=post_id, status="pending", stage="queued")
        db.add(job)
    else:
        job.status = "pending"
        job.stage = "queued"
        job.error = ""
        job.finished_at = None
    await db.commit()
    await db.refresh(job)

    asyncio.create_task(run_analyze(post_id))
    return job


@router.get("/{post_id}/elements", response_model=PostElementsResponse)
async def get_post_elements(
    post_id: int,
    sort: str = Query("quality", pattern="^(rank|quality)$"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    post = await _post_belongs_to_user(db, post_id, user.id)
    if not post:
        raise HTTPException(status_code=404, detail="포스트를 찾을 수 없습니다")

    job_result = await db.execute(
        select(PostUsageJob).where(PostUsageJob.post_id == post_id)
    )
    job = job_result.scalar_one_or_none()

    el_result = await db.execute(
        select(ExtractedElement)
        .where(ExtractedElement.post_id == post_id)
        .options(selectinload(ExtractedElement.images))
        .order_by(ExtractedElement.id)
    )
    elements = el_result.scalars().all()

    img_key = (
        (lambda im: (-im.quality_score, im.rank))
        if sort == "quality"
        else (lambda im: im.rank)
    )

    element_responses = []
    for e in elements:
        e.images.sort(key=img_key)
        resp = ExtractedElementResponse.model_validate(e)
        resp.images = [
            ElementImageResponse(
                **{**img.model_dump(), "url": _pool_url(img.local_path) or img.thumbnail_url}
            )
            for img in resp.images
        ]
        element_responses.append(resp)

    return PostElementsResponse(
        job=PostUsageJobResponse.model_validate(job) if job else None,
        elements=element_responses,
    )


@router.put("/{post_id}/elements")
async def edit_elements(
    post_id: int,
    payload: ElementsEditRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Replace the post's element list. Items with id update; without id insert; missing ids delete."""
    post = await _post_belongs_to_user(db, post_id, user.id)
    if not post:
        raise HTTPException(status_code=404, detail="포스트를 찾을 수 없습니다")

    existing_result = await db.execute(
        select(ExtractedElement).where(ExtractedElement.post_id == post_id)
    )
    existing = {e.id: e for e in existing_result.scalars().all()}
    incoming_ids = {item.id for item in payload.elements if item.id is not None}

    for old_id, old in list(existing.items()):
        if old_id not in incoming_ids:
            await db.delete(old)

    updated, inserted = 0, 0
    for item in payload.elements:
        name = item.name.strip()[:255]
        if not name:
            continue
        sq = (item.search_query or item.name).strip()[:500]
        if item.id and item.id in existing:
            row = existing[item.id]
            row.name = name
            row.search_query = sq
            row.selected = item.selected
            updated += 1
        else:
            db.add(ExtractedElement(
                post_id=post_id,
                name=name,
                search_query=sq,
                source_text="",
                selected=item.selected,
            ))
            inserted += 1
    await db.commit()
    return {
        "post_id": post_id,
        "updated": updated,
        "inserted": inserted,
        "deleted": len(existing) - updated,
    }


@router.post("/{post_id}/elements/collect", response_model=PostUsageJobResponse, status_code=202)
async def trigger_collect(
    post_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Stage 2 trigger: start image collection for elements with selected=True."""
    post = await _post_belongs_to_user(db, post_id, user.id)
    if not post:
        raise HTTPException(status_code=404, detail="포스트를 찾을 수 없습니다")

    job_result = await db.execute(select(PostUsageJob).where(PostUsageJob.post_id == post_id))
    job = job_result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=400, detail="먼저 분석(/use)을 실행해주세요")
    if job.status == "running":
        return job

    job.status = "pending"
    job.stage = "queued"
    job.error = ""
    job.finished_at = None
    await db.commit()
    await db.refresh(job)

    asyncio.create_task(run_collect(post_id))
    return job


@router.get("/{post_id}/use", response_model=PostUsageJobResponse)
async def get_use_status(
    post_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    post = await _post_belongs_to_user(db, post_id, user.id)
    if not post:
        raise HTTPException(status_code=404, detail="포스트를 찾을 수 없습니다")

    result = await db.execute(
        select(PostUsageJob).where(PostUsageJob.post_id == post_id)
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="아직 시작된 작업이 없습니다")
    return job
