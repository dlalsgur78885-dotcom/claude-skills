"""Instagram non-authenticated scraper using Playwright.

Navigates to a public profile page and intercepts the web_profile_info API call
that Instagram's own frontend makes. Returns up to 12 posts per request.
"""

import asyncio
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

_PROFILE_API = "web_profile_info"


def _extract_handle(raw: str) -> str:
    """Normalize URL or handle → bare username."""
    raw = raw.strip().lstrip("@")
    raw = re.sub(r"^https?://(www\.)?instagram\.com/", "", raw, flags=re.I)
    return raw.strip("/")


def _parse_post(node: dict) -> dict:
    """Convert a GraphQL edge node → our standard post dict."""
    typename = node.get("__typename", "")
    shortcode = node.get("shortcode", "")

    # Images
    image_urls: list[str] = []
    if typename == "GraphSidecar":
        for child in node.get("edge_sidecar_to_children", {}).get("edges", []):
            url = child.get("node", {}).get("display_url", "")
            if url:
                image_urls.append(url)
    else:
        url = node.get("display_url", "")
        if url:
            image_urls.append(url)

    slide_count = max(len(image_urls), 1)

    # Caption
    caption_edges = node.get("edge_media_to_caption", {}).get("edges", [])
    caption = caption_edges[0]["node"]["text"] if caption_edges else ""

    # Hashtags
    hashtags = re.findall(r"#(\w+)", caption)

    return {
        "instagram_post_id": str(node.get("id", "")),
        "shortcode": shortcode,
        "post_url": f"https://www.instagram.com/p/{shortcode}/",
        "caption": caption,
        "hashtags": hashtags,
        "image_urls": image_urls,
        "slide_count": slide_count,
        "like_count": node.get("edge_liked_by", {}).get("count", 0),
        "comment_count": node.get("edge_media_to_comment", {}).get("count", 0),
        "post_date": node.get("taken_at_timestamp"),
        "media_type": (
            "carousel" if typename == "GraphSidecar"
            else "video" if node.get("is_video")
            else "photo"
        ),
        "is_video": node.get("is_video", False),
    }


async def scrape_profile(handle: str, timeout: int = 30) -> dict:
    """
    Scrape a public Instagram profile using Playwright.

    Returns:
        {
            "handle": str,
            "posts": list[dict],
            "post_count": int,
            "follower_count": int,
            "error": str | None,
        }
    """
    from playwright.async_api import async_playwright, TimeoutError as PWTimeout

    handle = _extract_handle(handle)
    url = f"https://www.instagram.com/{handle}/"
    result: dict[str, Any] = {"handle": handle, "posts": [], "post_count": 0,
                               "follower_count": 0, "error": None}
    api_data: dict = {}
    event = asyncio.Event()

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="ko-KR",
            viewport={"width": 1280, "height": 800},
        )
        page = await ctx.new_page()

        async def handle_response(response):
            if _PROFILE_API in response.url and response.status == 200:
                try:
                    api_data.update(await response.json())
                    event.set()
                except Exception:
                    pass

        page.on("response", handle_response)

        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=timeout * 1000)
            try:
                await asyncio.wait_for(event.wait(), timeout=timeout)
            except asyncio.TimeoutError:
                result["error"] = "API 응답 없음 (비공개 계정이거나 차단됨)"
                return result
        except PWTimeout:
            result["error"] = f"페이지 로드 타임아웃: {url}"
            return result
        except Exception as e:
            result["error"] = str(e)
            return result
        finally:
            await browser.close()

    # Parse response
    try:
        user = api_data.get("data", {}).get("user", {})
        timeline = user.get("edge_owner_to_timeline_media", {})
        edges = timeline.get("edges", [])

        posts = [_parse_post(e["node"]) for e in edges if e.get("node")]
        # Only carousel and photo posts (skip videos if not needed)
        result["posts"] = posts
        result["post_count"] = len(posts)
        result["follower_count"] = (
            user.get("edge_followed_by", {}).get("count", 0)
        )
    except Exception as e:
        result["error"] = f"파싱 실패: {e}"

    return result
