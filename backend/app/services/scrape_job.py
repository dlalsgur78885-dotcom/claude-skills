"""Core scraping job: fetch posts via GramSnap (incremental) and save to DB."""

import asyncio
import logging
import re
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# Seconds to pause between successive channel scrapes inside `run_all_channels`.
# Spreads load across the run window so GramSnap / Instagram don't see a burst
# (which was triggering 429 / timeout). For 10 channels: 10×60s = 10 min total.
INTER_CHANNEL_DELAY_S = 60

# Per-run cap on new posts saved. TTL-based cleanup (3-day soft delete) lives
# in app.services.post_cleanup.expire_old_posts, scheduled separately — we no
# longer prune by post count here.
MAX_NEW_POSTS_PER_SCRAPE = 50

from app.database import async_session
from app.models.channel import BenchmarkChannel
from app.models.post import CollectedPost
from app.models.image import PostImage
from app.services.gramsnap_scraper import scrape_profile

logger = logging.getLogger(__name__)

_SHORTCODE_RE = re.compile(r"/p/([^/?#]+)")


async def _last_known_shortcode(db: AsyncSession, channel_id: int) -> str | None:
    """Return shortcode of the channel's most recent post, or None on first scrape."""
    row = await db.execute(
        select(CollectedPost)
        .where(CollectedPost.channel_id == channel_id)
        .order_by(CollectedPost.post_date.desc().nulls_last())
        .limit(1)
    )
    last = row.scalar_one_or_none()
    if not last or not last.post_url:
        return None
    m = _SHORTCODE_RE.search(last.post_url)
    return m.group(1) if m else None


async def save_posts(db: AsyncSession, channel: BenchmarkChannel, posts: list[dict]) -> int:
    """Save scraped posts to DB, skip duplicates. Returns number of new posts.

    Caps the harvest at MAX_NEW_POSTS_PER_SCRAPE new rows per call — GramSnap
    paginates aggressively and we don't want one channel running through 500
    posts on first scrape just because the account is old. The rest get
    naturally caught on subsequent incremental scrapes (the user wants ~50
    fresh per run anyway).
    """
    new_count = 0
    for post in posts:
        if new_count >= MAX_NEW_POSTS_PER_SCRAPE:
            break
        ig_id = post.get("instagram_post_id", "")
        if not ig_id:
            continue

        # 슬라이드 1장짜리 중 단일 이미지만 버린다 — 캐러셀 소재로 못 쓴다.
        # (버린 건 dedupe ledger 에도 안 남는다.)
        # 릴스는 커버·캡션을 참고 소재로 쓰므로 남긴다. 다만 is_video 를 채우는 건
        # GramSnap 경로뿐이라, Hiker fallback 으로 들어온 릴스는 여기서 계속 버려진다.
        slides = int(post.get("slide_count") or len(post.get("image_urls", [])))
        if slides < 2 and not post.get("is_video"):
            continue

        # Deduplicate by instagram_post_id
        existing = await db.execute(
            select(CollectedPost).where(CollectedPost.instagram_post_id == ig_id)
        )
        if existing.scalar_one_or_none():
            continue

        post_date = None
        if post.get("post_date"):
            try:
                post_date = datetime.fromtimestamp(post["post_date"])
            except Exception:
                pass

        db_post = CollectedPost(
            channel_id=channel.id,
            instagram_post_id=ig_id,
            post_url=post.get("post_url", ""),
            caption=post.get("caption", ""),
            hashtags=post.get("hashtags", []),
            post_date=post_date,
            like_count=post.get("like_count", 0),
            comment_count=post.get("comment_count", 0),
            slide_count=post.get("slide_count", 1),
            is_video=bool(post.get("is_video")),
        )
        db.add(db_post)
        await db.flush()  # get db_post.id

        for i, img_url in enumerate(post.get("image_urls", [])):
            db.add(PostImage(
                post_id=db_post.id,
                slide_index=i,
                raw_path=img_url,
                # Preserve the original Instagram CDN URL — survives the
                # 3-hour cache cleanup of locally-downloaded raw_paths.
                source_url=img_url,
            ))

        new_count += 1

    await db.commit()
    return new_count


async def scrape_channel(channel: BenchmarkChannel) -> dict:
    """Scrape a single channel and save results.

    First scrape pulls the entire profile. Subsequent scrapes only pull posts
    newer than the channel's most recent stored post (incremental).
    """
    async with async_session() as db:
        since = await _last_known_shortcode(db, channel.id)

    mode = "incremental" if since else "full"
    logger.info(f"[Scrape] Starting: @{channel.instagram_handle} ({mode}, since={since})")
    result = await scrape_profile(channel.instagram_handle, since_shortcode=since)

    if result.get("error"):
        logger.warning(f"[Scrape] @{channel.instagram_handle} error: {result['error']}")
        return result

    async with async_session() as db:
        new_count = await save_posts(db, channel, result["posts"])
        channel_row = await db.get(BenchmarkChannel, channel.id)
        if channel_row:
            channel_row.last_scraped_at = datetime.now()
        await db.commit()

    logger.info(
        f"[Scrape] @{channel.instagram_handle}: "
        f"{result['post_count']} fetched, {new_count} new ({mode})"
    )
    result["new_count"] = new_count
    return result


# Channels are split across staggered sweeps by `id % SHARDS`, so no single
# session runs long. GramSnap failures clustered in the tail of every ~50-minute
# sweep (12:45–13:02, 00:53–01:07), i.e. the proxy degrades the longer a session
# is held open. Splitting by id needs no schema change and keeps a channel in
# the same shard as channels are added and removed.
SHARDS = 2

# One lock per shard, plus one for an unsharded (full) run. Sharing a single
# global lock would let one slow sweep silently swallow the *next* shard's
# entire run — which is the failure this guard exists to prevent. The guard
# itself is needed because the scheduler calls run_all_channels() directly and
# bypassed the API's own flag: on 8/3 a 23:35 manual run was still going when
# the 00:00 cron fired, and the second finished reporting 0 new posts.
_run_locks: dict[object, asyncio.Lock] = {}


def _lock_for(shard: int | None) -> asyncio.Lock:
    return _run_locks.setdefault(shard, asyncio.Lock())


def _overlapping(shard: int | None) -> list[asyncio.Lock]:
    """Locks covering channels this run would also touch."""
    if shard is None:
        return [_lock_for(None)] + [_lock_for(s) for s in range(SHARDS)]
    return [_lock_for(None), _lock_for(shard)]


def is_scrape_running(shard: int | None = None) -> bool:
    """True while a sweep is in flight — any sweep when `shard` is omitted."""
    if shard is None:
        return any(lock.locked() for lock in _run_locks.values())
    return _lock_for(shard).locked()


async def run_all_channels(shard: int | None = None, shards: int = SHARDS) -> dict:
    """Scrape active channels — all of them, or just one shard.

    Skips (rather than queues) when an overlapping run is already going: these
    sweeps are driven by a cron, so a late run is worth less than not doubling
    up on the proxy.
    """
    # No await between the check and the acquire, so this cannot interleave.
    if any(lock.locked() for lock in _overlapping(shard)):
        logger.warning(f"{_tag(shard)} an overlapping run is in progress — skipping this trigger")
        return {"channels": 0, "total_new": 0, "skipped": True}
    async with _lock_for(shard):
        return await _run_all_channels(shard, shards)


def _tag(shard: int | None) -> str:
    return "[Scrape]" if shard is None else f"[Scrape s{shard}]"


async def _run_all_channels(shard: int | None, shards: int) -> dict:
    async with async_session() as db:
        query = select(BenchmarkChannel).where(BenchmarkChannel.is_active == True)
        if shard is not None:
            query = query.where(BenchmarkChannel.id % shards == shard)
        rows = await db.execute(query)
        channels = rows.scalars().all()

    tag = _tag(shard)
    if not channels:
        logger.info(f"{tag} No active channels to scrape")
        return {"channels": 0, "total_new": 0}

    logger.info(
        f"{tag} Running for {len(channels)} channels "
        f"(spread over ~{len(channels) * INTER_CHANNEL_DELAY_S}s)"
    )
    total_new = 0
    for idx, ch in enumerate(channels):
        try:
            res = await scrape_channel(ch)
            total_new += res.get("new_count", 0)
        except Exception as e:
            logger.error(f"[Scrape] Failed @{ch.instagram_handle}: {e}")
        # Throttle between channels so GramSnap / Instagram see a steady drip
        # instead of a burst. Skip the sleep after the LAST channel.
        if idx < len(channels) - 1 and INTER_CHANNEL_DELAY_S > 0:
            await asyncio.sleep(INTER_CHANNEL_DELAY_S)

    logger.info(f"{tag} Done. Total new posts: {total_new}")
    return {"channels": len(channels), "total_new": total_new}
