"""Single-post ingest via GramSnap (no API key required).

GramSnap exposes posts by `username`, so the caller must supply it. We then
filter by the shortcode parsed from `post_url`. Two perf knobs:

- `until_shortcode`: GramSnap stops paginating as soon as the target shortcode
  appears (vendored fork — see backend/gramnsap/lib.py).
- In-process cache: keep the most recent fetch per username for 10 min so a
  second ingest of the same channel can hit cache.
"""

from __future__ import annotations

import logging
import re
import time
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.channel import BenchmarkChannel
from app.models.image import PostImage
from app.models.post import CollectedPost

logger = logging.getLogger(__name__)

_CACHE_TTL_SEC = 600
_PROFILE_CACHE: dict[str, tuple[float, list]] = {}


def _shortcode(post_url: str) -> str:
    from app.services.instagram import extract_shortcode

    return extract_shortcode(post_url)


async def _refresh_image_urls(db: AsyncSession, post: CollectedPost, image_urls: list[str]) -> None:
    """Re-point an existing post's images at the fresh CDN URLs from the scrape
    we just did. Instagram CDN URLs are signed and expire after a few days —
    the dedupe path used to return the stale row untouched, so re-analyzing a
    previously collected post showed every reference image broken (피드백 14-1)."""
    if not image_urls:
        return
    result = await db.execute(select(PostImage).where(PostImage.post_id == post.id))
    by_idx = {img.slide_index: img for img in result.scalars()}
    changed = False
    for i, url in enumerate(image_urls):
        if not url or not url.startswith("http"):
            continue
        img = by_idx.get(i)
        if img is None:
            db.add(PostImage(post_id=post.id, slide_index=i, raw_path=url, source_url=url))
            changed = True
        elif img.source_url != url:
            img.raw_path = url
            img.source_url = url
            changed = True
    if changed:
        await db.commit()
        logger.info(f"[ingest] refreshed {len(image_urls)} image URLs for existing post {post.id}")


def _cache_lookup(handle: str, short: str):
    entry = _PROFILE_CACHE.get(handle)
    if not entry:
        return None
    age, posts = entry
    if time.time() - age > _CACHE_TTL_SEC:
        _PROFILE_CACHE.pop(handle, None)
        return None
    return next((p for p in posts if p.shortcode == short), None)


def _cache_store(handle: str, posts: list) -> None:
    _PROFILE_CACHE[handle] = (time.time(), posts)


async def ingest_post_by_url_via_hiker(
    post_url: str,
    user_id: int,
    db: AsyncSession,
) -> CollectedPost:
    """Fetch a post by URL alone via HikerAPI (no username needed) and persist it.

    Returns the existing row if already ingested.
    """
    from app.services.instagram import InstagramAPI

    from app.services.instagram import is_instagram_url

    post_url = (post_url or "").strip()
    if not is_instagram_url(post_url):
        raise ValueError(f"인스타그램 게시물 URL이 아닙니다: {post_url}")

    api = InstagramAPI()
    try:
        data = await api.scrape_post(post_url)
    finally:
        await api.close()

    if data.get("error"):
        raise RuntimeError(f"HikerAPI 오류: {data['error']}")

    ig_id = str(data.get("instagram_post_id") or "").strip()
    if not ig_id:
        raise RuntimeError("HikerAPI 응답에 게시물 ID가 없습니다")

    existing = await db.execute(
        select(CollectedPost).where(CollectedPost.instagram_post_id == ig_id)
    )
    found = existing.scalar_one_or_none()
    if found:
        await _refresh_image_urls(db, found, data.get("image_urls") or [])
        return found

    handle = (data.get("username") or "").lstrip("@").strip() or "unknown"

    ch_result = await db.execute(
        select(BenchmarkChannel).where(
            BenchmarkChannel.user_id == user_id,
            BenchmarkChannel.instagram_handle == handle,
        )
    )
    channel = ch_result.scalar_one_or_none()
    if not channel:
        channel = BenchmarkChannel(
            user_id=user_id,
            instagram_handle=handle,
            display_name=handle,
            is_active=False,
        )
        db.add(channel)
        await db.flush()

    post_date = (
        datetime.fromtimestamp(data["post_date"]) if data.get("post_date") else None
    )
    image_urls = data.get("image_urls") or []

    post = CollectedPost(
        channel_id=channel.id,
        instagram_post_id=ig_id,
        post_url=data.get("post_url") or post_url,
        caption=data.get("caption") or "",
        hashtags=data.get("hashtags") or [],
        post_date=post_date,
        like_count=data.get("like_count") or 0,
        comment_count=data.get("comment_count") or 0,
        slide_count=data.get("slide_count") or max(len(image_urls), 1),
    )
    db.add(post)
    await db.flush()

    for i, img_url in enumerate(image_urls):
        # source_url preserves the original Instagram CDN URL even after
        # use_post downloads + cleanup later wipes the local copy.
        db.add(PostImage(post_id=post.id, slide_index=i, raw_path=img_url, source_url=img_url))

    await db.commit()
    await db.refresh(post)
    logger.info(
        f"[ingest/hiker] saved post {post.id} (@{handle}, ig_id={ig_id}, {len(image_urls)} slides)"
    )
    return post


async def ingest_single_post(
    post_url: str,
    username: str,
    user_id: int,
    db: AsyncSession,
    create_channel_if_missing: bool = True,
) -> CollectedPost:
    """Fetch one post by URL+username via GramSnap. Returns existing row if already ingested."""
    short = _shortcode(post_url)
    if not short:
        raise ValueError(f"인스타그램 게시물 URL이 아닙니다: {post_url}")

    handle = (username or "").lstrip("@").strip()
    if not handle:
        raise ValueError("username이 필요합니다 (예: trip.n.life_)")

    from gramnsap import GramSnap, ErrorWhenFetchingPosts

    matched = _cache_lookup(handle, short)
    if matched:
        logger.info(f"[ingest] cache hit @{handle} {short}")

    if matched is None:
        try:
            async with GramSnap() as gs:
                result = await gs.posts(handle, until_shortcode=short)
                posts_list = list(result)
        except ErrorWhenFetchingPosts as e:
            if not e.posts:
                raise RuntimeError("GramSnap 조회 실패 (재시도 한도 초과)") from e
            posts_list = e.posts
        except Exception as e:
            raise RuntimeError(f"GramSnap 오류: {e}") from e

        _cache_store(handle, posts_list)
        matched = next((p for p in posts_list if p.shortcode == short), None)
    if not matched:
        raise RuntimeError(
            f"@{handle}의 게시물 중 shortcode '{short}'를 찾지 못했습니다 "
            f"(검색한 게시물 {len(posts_list)}개)"
        )

    existing = await db.execute(
        select(CollectedPost).where(CollectedPost.instagram_post_id == str(matched.id))
    )
    found = existing.scalar_one_or_none()
    if found:
        fresh_urls = (
            [c.display_url for c in matched.children]
            if matched.children
            else [matched.display_url]
        )
        await _refresh_image_urls(db, found, fresh_urls)
        return found

    ch_result = await db.execute(
        select(BenchmarkChannel).where(
            BenchmarkChannel.user_id == user_id,
            BenchmarkChannel.instagram_handle == handle,
        )
    )
    channel = ch_result.scalar_one_or_none()
    if not channel:
        if not create_channel_if_missing:
            raise RuntimeError(f"채널 @{handle}이 없습니다")
        channel = BenchmarkChannel(
            user_id=user_id,
            instagram_handle=handle,
            display_name=handle,
            is_active=False,
        )
        db.add(channel)
        await db.flush()

    post_date = datetime.fromtimestamp(matched.timestamp) if matched.timestamp else None
    hashtags = re.findall(r"#(\w+)", matched.caption or "")

    image_urls = (
        [c.display_url for c in matched.children]
        if matched.children
        else [matched.display_url]
    )
    slide_count = max(len(image_urls), 1)

    post = CollectedPost(
        channel_id=channel.id,
        instagram_post_id=str(matched.id),
        post_url=matched.url,
        caption=matched.caption or "",
        hashtags=hashtags,
        post_date=post_date,
        like_count=matched.likes,
        comment_count=matched.comments,
        slide_count=slide_count,
    )
    db.add(post)
    await db.flush()

    for i, img_url in enumerate(image_urls):
        # source_url preserves the original Instagram CDN URL even after
        # use_post downloads + cleanup later wipes the local copy.
        db.add(PostImage(post_id=post.id, slide_index=i, raw_path=img_url, source_url=img_url))

    await db.commit()
    await db.refresh(post)
    logger.info(
        f"[ingest] saved post {post.id} via GramSnap (@{handle}, "
        f"ig_id={matched.id}, {slide_count} slides)"
    )
    return post
