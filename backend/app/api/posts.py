"""Collected posts endpoints."""

from datetime import date, datetime, time

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.user import User
from app.models.channel import BenchmarkChannel
from app.models.post import CollectedPost
from app.models.image import PostImage
from app.schemas.post import PostResponse
from app.api.auth import get_current_user

router = APIRouter(prefix="/posts", tags=["posts"])


class IngestRequest(BaseModel):
    post_url: str
    username: str


@router.post("/ingest", response_model=PostResponse, status_code=201)
async def ingest_post(
    payload: IngestRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Ingest a single Instagram post by URL + username (GramSnap). Auto-creates the channel if missing."""
    from app.services.post_ingest import ingest_single_post

    try:
        post = await ingest_single_post(payload.post_url, payload.username, user.id, db)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))

    result = await db.execute(
        select(CollectedPost)
        .where(CollectedPost.id == post.id)
        .options(selectinload(CollectedPost.images))
    )
    return result.scalar_one()


@router.get("/", response_model=list[PostResponse])
async def list_posts(
    channel_id: int | None = Query(None),
    min_likes: int | None = Query(None),
    max_likes: int | None = Query(None),
    min_comments: int | None = Query(None),
    max_comments: int | None = Query(None),
    min_slides: int | None = Query(None),
    max_slides: int | None = Query(None),
    is_video: bool | None = Query(None, description="true=릴스만, false=캐러셀만, 생략=전체"),
    category: str | None = Query(None, description="채널 그룹으로 필터 (benchmark_channels.category)"),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    q: str | None = Query(None, description="caption substring search"),
    limit: int = Query(20, le=200),
    offset: int = Query(0),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = (
        select(CollectedPost)
        .join(BenchmarkChannel)
        .where(
            BenchmarkChannel.user_id == user.id,
            CollectedPost.expired_at.is_(None),
            CollectedPost.saved_at.is_(None),
        )
        # List view only renders the first slide as a thumbnail — loading every
        # slide (avg ~7, up to 20) bloats the response ~7x for no UI gain.
        .options(selectinload(CollectedPost.images.and_(PostImage.slide_index == 0)))
        .order_by(CollectedPost.collected_at.desc())
        .limit(limit)
        .offset(offset)
    )

    if channel_id:
        query = query.where(CollectedPost.channel_id == channel_id)
    if min_likes is not None:
        query = query.where(CollectedPost.like_count >= min_likes)
    if max_likes is not None:
        query = query.where(CollectedPost.like_count <= max_likes)
    if min_comments is not None:
        query = query.where(CollectedPost.comment_count >= min_comments)
    if max_comments is not None:
        query = query.where(CollectedPost.comment_count <= max_comments)
    if min_slides is not None:
        query = query.where(CollectedPost.slide_count >= min_slides)
    if max_slides is not None:
        query = query.where(CollectedPost.slide_count <= max_slides)
    if is_video is not None:
        query = query.where(CollectedPost.is_video == is_video)
    if category:
        # The query already joins BenchmarkChannel for the ownership check, so
        # filtering by the channel's group needs no extra join.
        query = query.where(BenchmarkChannel.category == category)
    if date_from is not None:
        query = query.where(CollectedPost.post_date >= datetime.combine(date_from, time.min))
    if date_to is not None:
        query = query.where(CollectedPost.post_date <= datetime.combine(date_to, time.max))
    if q:
        # Caption substring search, case-insensitive. Trim to avoid stray-space
        # mismatches and skip empty queries that would no-op the filter anyway.
        needle = q.strip()
        if needle:
            query = query.where(CollectedPost.caption.ilike(f"%{needle}%"))

    result = await db.execute(query)
    return result.scalars().all()


@router.get("/saved", response_model=list[PostResponse])
async def list_saved_posts(
    limit: int = Query(50, le=200),
    offset: int = Query(0),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """'내 소재' 탭 — 유저가 보관한 post (TTL 면제)."""
    result = await db.execute(
        select(CollectedPost)
        .join(BenchmarkChannel)
        .where(
            BenchmarkChannel.user_id == user.id,
            CollectedPost.saved_at.is_not(None),
        )
        # Same as /posts — the list only renders the first slide as a thumbnail.
        .options(selectinload(CollectedPost.images.and_(PostImage.slide_index == 0)))
        .order_by(CollectedPost.saved_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return result.scalars().all()


async def _owned_post(db: AsyncSession, post_id: int, user_id: int) -> CollectedPost:
    result = await db.execute(
        select(CollectedPost)
        .join(BenchmarkChannel)
        .where(CollectedPost.id == post_id, BenchmarkChannel.user_id == user_id)
    )
    post = result.scalar_one_or_none()
    if not post:
        raise HTTPException(status_code=404, detail="포스트를 찾을 수 없습니다")
    return post


@router.post("/{post_id}/save", response_model=PostResponse)
async def save_post(
    post_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """post를 '내 소재'로 이동 — TTL 면제, /posts 탭에서 숨김."""
    post = await _owned_post(db, post_id, user.id)
    if post.saved_at is None:
        post.saved_at = datetime.now()
        # 혹시 expired 상태였다면 되살림
        post.expired_at = None
        await db.commit()
    await db.refresh(post)
    result = await db.execute(
        select(CollectedPost).where(CollectedPost.id == post_id).options(selectinload(CollectedPost.images))
    )
    return result.scalar_one()


@router.delete("/{post_id}/save", status_code=204)
async def unsave_post(
    post_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """'내 소재'에서 빼기 — TTL 대상으로 복귀."""
    post = await _owned_post(db, post_id, user.id)
    if post.saved_at is not None:
        post.saved_at = None
        await db.commit()


@router.get("/{post_id}", response_model=PostResponse)
async def get_post(
    post_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(CollectedPost)
        .join(BenchmarkChannel)
        .where(
            CollectedPost.id == post_id,
            BenchmarkChannel.user_id == user.id,
            CollectedPost.expired_at.is_(None),
        )
        .options(selectinload(CollectedPost.images))
    )
    post = result.scalar_one_or_none()
    if not post:
        raise HTTPException(status_code=404, detail="포스트를 찾을 수 없습니다")
    return post


@router.delete("/{post_id}", status_code=204)
async def delete_post(
    post_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a collected post and its derived data.

    Cascade logic lives in app.services.post_cleanup so the scheduled scrape
    prune can reuse the same routine. Ownership is enforced via channel.user_id
    — users can only delete posts from channels they own.
    """
    from app.services.post_cleanup import delete_posts_cascade

    owner_check = await db.execute(
        select(CollectedPost.id)
        .join(BenchmarkChannel)
        .where(CollectedPost.id == post_id, BenchmarkChannel.user_id == user.id)
    )
    if owner_check.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="포스트를 찾을 수 없습니다")

    await delete_posts_cascade(db, [post_id])
    await db.commit()
