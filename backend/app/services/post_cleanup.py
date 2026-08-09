"""Shared post-deletion helpers.

The user-facing DELETE /posts/{id} endpoint and the scheduled scrape's rolling
prune both need to drop a CollectedPost together with everything that
references it (PostImage, ExtractedElement → ElementImagePool, PostUsageJob).
We unlink GeneratedCarousel.source_post_id instead of cascading the delete so
the user's finished work survives the source going away.

Pulled into its own module so the cascade logic stays in one place — changing
the schema later only requires updating these two helpers.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Iterable

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.carousel import GeneratedCarousel
from app.models.element import ElementImagePool, ExtractedElement, PostUsageJob
from app.models.image import PostImage
from app.models.post import CollectedPost

logger = logging.getLogger(__name__)


async def delete_posts_cascade(db: AsyncSession, post_ids: Iterable[int]) -> int:
    """Delete one or more posts along with every row that FKs to them.

    Order matters: child rows first (PostImage, ExtractedElement /
    ElementImagePool, PostUsageJob), then the post itself. Carousels are
    unlinked, not deleted. Returns the number of CollectedPost rows removed.

    Bulk DELETE statements bypass the ORM, so the `cascade="all, delete-orphan"`
    relationship between ExtractedElement and ElementImagePool doesn't fire —
    we delete ElementImagePool explicitly first.
    """
    ids = list({int(i) for i in post_ids if i is not None})
    if not ids:
        return 0

    # Preserve generated carousels — just sever the back-reference.
    await db.execute(
        update(GeneratedCarousel)
        .where(GeneratedCarousel.source_post_id.in_(ids))
        .values(source_post_id=None)
    )

    el_ids = (
        await db.execute(select(ExtractedElement.id).where(ExtractedElement.post_id.in_(ids)))
    ).scalars().all()
    if el_ids:
        await db.execute(delete(ElementImagePool).where(ElementImagePool.element_id.in_(el_ids)))
        await db.execute(delete(ExtractedElement).where(ExtractedElement.id.in_(el_ids)))

    await db.execute(delete(PostUsageJob).where(PostUsageJob.post_id.in_(ids)))
    await db.execute(delete(PostImage).where(PostImage.post_id.in_(ids)))
    result = await db.execute(delete(CollectedPost).where(CollectedPost.id.in_(ids)))
    return int(getattr(result, "rowcount", 0) or 0)


async def expire_old_posts(db: AsyncSession, days: int = 5) -> int:
    """Soft-delete posts whose collected_at is older than `days`.

    Drops the heavy child data (PostImage, ExtractedElement → ElementImagePool,
    PostUsageJob) and unlinks GeneratedCarousel.source_post_id, but keeps the
    CollectedPost row itself with expired_at set. The row's instagram_post_id
    stays as the channel's permanent dedupe ledger — re-scrapes will skip it
    even after the body has been purged. Posts moved into "내 소재" (saved_at
    set) are TTL-immune. Returns the number of posts expired.
    """
    cutoff = datetime.now() - timedelta(days=days)
    stale_ids = (
        await db.execute(
            select(CollectedPost.id).where(
                CollectedPost.collected_at < cutoff,
                CollectedPost.expired_at.is_(None),
                CollectedPost.saved_at.is_(None),
            )
        )
    ).scalars().all()
    if not stale_ids:
        return 0

    await db.execute(
        update(GeneratedCarousel)
        .where(GeneratedCarousel.source_post_id.in_(stale_ids))
        .values(source_post_id=None)
    )
    el_ids = (
        await db.execute(select(ExtractedElement.id).where(ExtractedElement.post_id.in_(stale_ids)))
    ).scalars().all()
    if el_ids:
        await db.execute(delete(ElementImagePool).where(ElementImagePool.element_id.in_(el_ids)))
        await db.execute(delete(ExtractedElement).where(ExtractedElement.id.in_(el_ids)))
    await db.execute(delete(PostUsageJob).where(PostUsageJob.post_id.in_(stale_ids)))
    await db.execute(delete(PostImage).where(PostImage.post_id.in_(stale_ids)))

    now = datetime.now()
    await db.execute(
        update(CollectedPost)
        .where(CollectedPost.id.in_(stale_ids))
        .values(expired_at=now, caption="", hashtags=[])
    )
    await db.commit()
    logger.info("[expire] soft-deleted %d posts older than %d days", len(stale_ids), days)
    return len(stale_ids)


async def prune_channel_to_latest(db: AsyncSession, channel_id: int, keep: int) -> int:
    """Keep only the `keep` newest posts for a channel; cascade-delete the rest.

    Ordered by post_date desc with id desc as a tiebreaker so deletion is
    deterministic across runs. Returns the number of posts deleted.
    """
    if keep <= 0:
        return 0
    stale_ids = (
        await db.execute(
            select(CollectedPost.id)
            .where(CollectedPost.channel_id == channel_id)
            .order_by(
                CollectedPost.post_date.desc().nulls_last(),
                CollectedPost.id.desc(),
            )
            .offset(keep)
        )
    ).scalars().all()
    if not stale_ids:
        return 0
    removed = await delete_posts_cascade(db, stale_ids)
    logger.info(
        "[prune] channel_id=%s removed %d stale posts (kept newest %d)",
        channel_id, removed, keep,
    )
    return removed
