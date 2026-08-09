"""Channel scraper.

GramSnap is the primary path for scheduled channel scrapes — it is free, so the
twice-daily sweep over every channel costs nothing. HikerAPI is the paid
fallback, used only when GramSnap errors out or a first scrape finds no profile
at all. GramSnap captcha-gates datacenter IPs, so the primary path depends on
SCRAPING_PROXY_URLS being alive; Hiker is what keeps collection running when it
is not.
"""

from __future__ import annotations

import logging
import re

from gramnsap import GramSnap, ErrorWhenFetchingPosts

from app.config import settings

logger = logging.getLogger(__name__)


def _parse_post(p) -> dict:
    """GramSnap Output → standard post dict (matches playwright_scraper format)."""
    image_urls = (
        [c.display_url for c in p.children]
        if p.children
        else [p.display_url]
    )
    hashtags = re.findall(r"#(\w+)", p.caption or "")
    return {
        "instagram_post_id": str(p.id),
        "shortcode": p.shortcode,
        "post_url": p.url,
        "caption": p.caption or "",
        "hashtags": hashtags,
        "image_urls": image_urls,
        "slide_count": max(len(image_urls), 1),
        "like_count": p.likes,
        "comment_count": p.comments,
        "post_date": p.timestamp,
        "media_type": p.typename.name.lower(),
        "is_video": p.is_video,
    }


async def _via_gramsnap(handle: str, since_shortcode: str | None) -> dict:
    """Fetch channel posts via GramSnap (free, proxied)."""
    posts: list = []
    error: str | None = None

    try:
        # GramSnap captcha-gates datacenter IPs (AWS/Lightsail); route through
        # the residential proxy when one is configured. Field allows ;-rotation
        # — take the first entry.
        proxy = settings.SCRAPING_PROXY_URLS.split(";")[0].strip() or None
        async with GramSnap(proxy=proxy) as gs:
            result = await gs.posts(handle, until_shortcode=since_shortcode)
            posts = list(result)
    except ErrorWhenFetchingPosts as e:
        if e.posts:
            posts = e.posts
        else:
            error = "GramSnap 502 (재시도 한도 초과)"
    except Exception as e:
        error = f"GramSnap 오류: {e}"
        logger.exception(f"[gramsnap] @{handle} fetch failed")

    if since_shortcode:
        new_posts = []
        for p in posts:
            if p.shortcode == since_shortcode:
                break
            new_posts.append(p)
        posts = new_posts

    return {
        "handle": handle,
        "posts": [_parse_post(p) for p in posts],
        "post_count": len(posts),
        "follower_count": 0,
        "error": error,
    }


async def _via_hiker(handle: str, since_shortcode: str | None) -> dict:
    """Fetch channel posts via HikerAPI (paid, metered per request)."""
    from app.services.instagram import InstagramAPI

    api = InstagramAPI()
    try:
        return await api.scrape_channel(handle, limit=50, since=since_shortcode)
    finally:
        await api.close()


async def scrape_profile(handle: str, since_shortcode: str | None = None) -> dict:
    """Fetch channel posts — GramSnap first, HikerAPI as fallback.

    `since_shortcode`: if provided, pagination stops once that shortcode is
    seen, and it + anything older is dropped, so only newer posts come back.

    An empty *incremental* result means "no new posts since last run" and is
    returned as-is — most channels hit this on most runs, and falling back on it
    would send every one of them to the paid API twice a day. An empty *full*
    result means GramSnap found no profile at all, which is worth a second
    opinion from Hiker before we record the channel as empty.
    """
    handle = handle.lstrip("@").strip()

    result = await _via_gramsnap(handle, since_shortcode)
    if not result["error"] and (result["post_count"] or since_shortcode):
        return result

    reason = result["error"] or "빈 결과 (프로필 없음)"
    logger.warning(f"[gramsnap] @{handle}: {reason} — falling back to HikerAPI")

    try:
        hiker = await _via_hiker(handle, since_shortcode)
    except Exception as e:
        logger.exception(f"[hiker] @{handle} fallback crashed: {e}")
        return result

    if hiker.get("error"):
        logger.warning(f"[hiker] @{handle} fallback error: {hiker['error']}")
    return hiker
