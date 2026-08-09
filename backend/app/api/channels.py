"""Benchmark channel management endpoints."""

import logging
import secrets
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel
from sqlalchemy import select, delete, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.user import User
from app.models.channel import BenchmarkChannel
from app.models.template import CarouselTemplate
from app.models.post import CollectedPost
from app.models.image import PostImage
from app.models.element import ExtractedElement, ElementImagePool, PostUsageJob
from app.models.carousel import GeneratedCarousel
from app.schemas.channel import ChannelCreate, ChannelUpdate, ChannelResponse
from app.api.auth import get_current_user
from app.services.template_studio import (
    generate_and_save_template,
    list_channel_templates,
    template_row_summary,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/channels", tags=["channels"])


class GenerateChannelTemplateRequest(BaseModel):
    post_url: str
    template_name: str
    layout_hints: list[dict] | None = None


@router.get("/", response_model=list[ChannelResponse])
async def list_channels(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(BenchmarkChannel)
        .where(BenchmarkChannel.user_id == user.id)
        .order_by(BenchmarkChannel.created_at.desc())
    )
    return result.scalars().all()


async def _first_scrape(channel_id: int) -> None:
    """Collect a newly added channel's posts right away.

    Without this the channel sits empty until the next 09:00/21:00 sweep — up to
    12 hours of an empty row the user just asked for. Runs off the request path
    because a first scrape has no since_shortcode, so the scraper paginates the
    whole profile and can take minutes.
    """
    from app.database import async_session
    from app.services.scrape_job import scrape_channel

    try:
        async with async_session() as db:
            channel = await db.get(BenchmarkChannel, channel_id)
        if channel:
            await scrape_channel(channel)
    except Exception as e:
        logger.warning(f"[Channel] first scrape failed for channel {channel_id}: {e}")


@router.post("/", response_model=ChannelResponse, status_code=201)
async def create_channel(
    data: ChannelCreate,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Check for duplicate
    result = await db.execute(
        select(BenchmarkChannel).where(
            BenchmarkChannel.user_id == user.id,
            BenchmarkChannel.instagram_handle == data.instagram_handle,
        )
    )
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="이미 추가된 채널입니다")

    channel = BenchmarkChannel(
        user_id=user.id,
        instagram_handle=data.instagram_handle,
        display_name=data.display_name or data.instagram_handle,
        category=data.category,
        style_tags=data.style_tags,
        is_active=True,
    )
    db.add(channel)
    await db.commit()
    await db.refresh(channel)

    background_tasks.add_task(_first_scrape, channel.id)
    return channel


@router.get("/{channel_id}", response_model=ChannelResponse)
async def get_channel(
    channel_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(BenchmarkChannel).where(
            BenchmarkChannel.id == channel_id,
            BenchmarkChannel.user_id == user.id,
        )
    )
    channel = result.scalar_one_or_none()
    if not channel:
        raise HTTPException(status_code=404, detail="채널을 찾을 수 없습니다")
    return channel


@router.patch("/{channel_id}", response_model=ChannelResponse)
async def update_channel(
    channel_id: int,
    data: ChannelUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(BenchmarkChannel).where(
            BenchmarkChannel.id == channel_id,
            BenchmarkChannel.user_id == user.id,
        )
    )
    channel = result.scalar_one_or_none()
    if not channel:
        raise HTTPException(status_code=404, detail="채널을 찾을 수 없습니다")

    updates = data.model_dump(exclude_unset=True)

    # Validate default_template_id: must exist, belong to this user, and be tied to this channel
    if "default_template_id" in updates and updates["default_template_id"] is not None:
        tpl = await db.get(CarouselTemplate, updates["default_template_id"])
        if (
            not tpl
            or (tpl.user_id is not None and tpl.user_id != user.id)
            or (tpl.channel_id is not None and tpl.channel_id != channel_id)
        ):
            raise HTTPException(status_code=400, detail="유효하지 않은 템플릿입니다")

    for field, value in updates.items():
        setattr(channel, field, value)

    await db.commit()
    await db.refresh(channel)
    return channel


# ─── Channel templates ───

@router.get("/{channel_id}/templates")
async def list_templates_for_channel(
    channel_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    channel = await db.get(BenchmarkChannel, channel_id)
    if not channel or channel.user_id != user.id:
        raise HTTPException(status_code=404, detail="채널을 찾을 수 없습니다")
    return {
        "channel_id": channel_id,
        "default_template_id": channel.default_template_id,
        "templates": await list_channel_templates(db, channel_id),
    }


@router.post("/{channel_id}/templates", status_code=201)
async def create_template_for_channel(
    channel_id: int,
    body: GenerateChannelTemplateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate a new template (via Gemini Vision) for a benchmark channel."""
    channel = await db.get(BenchmarkChannel, channel_id)
    if not channel or channel.user_id != user.id:
        raise HTTPException(status_code=404, detail="채널을 찾을 수 없습니다")

    try:
        row = await generate_and_save_template(
            db=db,
            post_url=body.post_url,
            template_name=body.template_name,
            user_id=user.id,
            channel_id=channel_id,
            layout_hints=body.layout_hints,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Template generation failed")
        raise HTTPException(status_code=500, detail=str(e))

    return template_row_summary(row)


@router.post("/{channel_id}/logo")
async def upload_channel_logo(
    channel_id: int,
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Upload a brand logo image for the channel. Saved to data/images/logos/."""
    channel = await db.get(BenchmarkChannel, channel_id)
    if not channel or channel.user_id != user.id:
        raise HTTPException(status_code=404, detail="채널을 찾을 수 없습니다")

    if not (file.content_type or "").startswith("image/"):
        raise HTTPException(status_code=415, detail="이미지 파일만 업로드 가능합니다")

    out_dir = settings.DATA_DIR / "images" / "logos"
    out_dir.mkdir(parents=True, exist_ok=True)

    ext = ".png"
    if file.content_type == "image/jpeg":
        ext = ".jpg"
    elif file.content_type == "image/webp":
        ext = ".webp"
    elif file.content_type == "image/svg+xml":
        ext = ".svg"

    fname = f"ch{channel_id}_{secrets.token_hex(6)}{ext}"
    out_path = out_dir / fname
    out_path.write_bytes(await file.read())

    public_url = f"/api/images/logos/{fname}"
    channel.brand_logo_path = public_url
    await db.commit()
    await db.refresh(channel)
    return {"brand_logo_path": public_url, "channel_id": channel_id}


async def _purge_channel_children(db: AsyncSession, channel_id: int) -> None:
    """Remove posts/images/elements/jobs tied to this channel and null out
    GeneratedCarousel.source_post_id + CarouselTemplate.channel_id.

    Templates are *preserved* — only their channel link is dropped, so saved
    user work survives channel deletion. Posts/images/elements get fully
    deleted because their CollectedPost.channel_id is NOT NULL.
    """
    post_ids = (
        await db.execute(
            select(CollectedPost.id).where(CollectedPost.channel_id == channel_id)
        )
    ).scalars().all()

    if post_ids:
        element_ids = (
            await db.execute(
                select(ExtractedElement.id).where(ExtractedElement.post_id.in_(post_ids))
            )
        ).scalars().all()
        if element_ids:
            await db.execute(
                delete(ElementImagePool).where(ElementImagePool.element_id.in_(element_ids))
            )
            await db.execute(
                delete(ExtractedElement).where(ExtractedElement.id.in_(element_ids))
            )
        await db.execute(delete(PostUsageJob).where(PostUsageJob.post_id.in_(post_ids)))
        await db.execute(delete(PostImage).where(PostImage.post_id.in_(post_ids)))
        await db.execute(
            update(GeneratedCarousel)
            .where(GeneratedCarousel.source_post_id.in_(post_ids))
            .values(source_post_id=None)
        )
        await db.execute(delete(CollectedPost).where(CollectedPost.id.in_(post_ids)))

    # Detach (don't delete) any templates that were tied to this channel.
    # Backup belt to the FK's ondelete=SET NULL — SQLite's PRAGMA foreign_keys
    # is OFF by default in this app's connections, so DB-level enforcement
    # may not fire. Explicit UPDATE guarantees the templates survive.
    await db.execute(
        update(CarouselTemplate)
        .where(CarouselTemplate.channel_id == channel_id)
        .values(channel_id=None)
    )


class BulkDeleteRequest(BaseModel):
    ids: list[int]


@router.delete("/{channel_id}", status_code=204)
async def delete_channel(
    channel_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(BenchmarkChannel).where(
            BenchmarkChannel.id == channel_id,
            BenchmarkChannel.user_id == user.id,
        )
    )
    channel = result.scalar_one_or_none()
    if not channel:
        raise HTTPException(status_code=404, detail="채널을 찾을 수 없습니다")

    await _purge_channel_children(db, channel_id)
    await db.delete(channel)
    await db.commit()


@router.post("/bulk-delete")
async def bulk_delete_channels(
    body: BulkDeleteRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not body.ids:
        return {"deleted": 0}

    owned = (
        await db.execute(
            select(BenchmarkChannel).where(
                BenchmarkChannel.id.in_(body.ids),
                BenchmarkChannel.user_id == user.id,
            )
        )
    ).scalars().all()

    for ch in owned:
        await _purge_channel_children(db, ch.id)
        await db.delete(ch)
    await db.commit()
    return {"deleted": len(owned)}
