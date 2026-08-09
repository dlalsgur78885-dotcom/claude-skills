"""Instagram data service using HikerAPI.

Replaces Playwright-based scraping with a stable REST API.
Docs: https://api.hikerapi.com/docs
"""

import logging
import re
from typing import Any
from urllib.parse import urlparse

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_INSTAGRAM_HOST_RE = re.compile(r"(^|\.)instagram\.com$", re.IGNORECASE)
_POST_PATH_RE = re.compile(r"^/(?:p|reel|reels|tv)/([^/?#]+)/?", re.IGNORECASE)


def is_instagram_url(url: str) -> bool:
    """Return true for Instagram URLs, including m.instagram.com."""
    try:
        parsed = urlparse((url or "").strip())
    except Exception:
        return False
    return parsed.scheme in {"http", "https"} and bool(_INSTAGRAM_HOST_RE.search(parsed.netloc.split("@")[-1].split(":")[0]))


def extract_shortcode(post_url: str) -> str:
    """Extract shortcode from canonical post/reel/tv URLs.

    App-copied links often carry query strings like `?igsh=...`; urlparse
    strips those before matching. Newer `/share/...` links do not expose a
    shortcode, so callers should fall back to Hiker's by-url endpoint.
    """
    try:
        parsed = urlparse((post_url or "").strip())
    except Exception:
        return ""
    m = _POST_PATH_RE.match(parsed.path)
    return m.group(1) if m else ""


def _unwrap_media_response(data: dict) -> dict:
    """Normalize HikerAPI media response wrappers across v1/v2 endpoints."""
    if not isinstance(data, dict):
        return {}
    for key in ("media_or_ad", "media", "item"):
        if isinstance(data.get(key), dict):
            return data[key]
    response = data.get("response")
    if isinstance(response, dict):
        for key in ("media_or_ad", "media", "item"):
            if isinstance(response.get(key), dict):
                return response[key]
        if response.get("pk") or response.get("id"):
            return response
    return data


class InstagramAPI:
    """HikerAPI-based Instagram data fetcher."""

    def __init__(self):
        self.base_url = settings.HIKER_API_BASE_URL
        self.api_key = settings.HIKER_API_KEY
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers={"x-access-key": self.api_key},
                timeout=30.0,
            )
        return self._client

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def _request(self, method: str, path: str, **kwargs) -> dict:
        """Make an authenticated request to HikerAPI."""
        client = await self._get_client()
        response = await client.request(method, path, **kwargs)
        response.raise_for_status()
        return response.json()

    # ─── Channel/User endpoints ───

    async def get_user_by_username(self, username: str) -> dict:
        """Get user profile by Instagram handle."""
        data = await self._request(
            "GET", "/v1/user/by/username", params={"username": username}
        )
        return {
            "user_id": data.get("pk"),
            "username": data.get("username"),
            "full_name": data.get("full_name", ""),
            "biography": data.get("biography", ""),
            "follower_count": data.get("follower_count", 0),
            "following_count": data.get("following_count", 0),
            "media_count": data.get("media_count", 0),
            "profile_pic_url": data.get("profile_pic_url_hd", ""),
            "is_business": data.get("is_business_account", False),
            "category": data.get("category_name", ""),
        }

    async def get_user_medias(
        self, user_id: int | str, limit: int = 12, end_cursor: str | None = None
    ) -> dict:
        """Get user's media posts (paginated)."""
        params: dict[str, Any] = {"user_id": user_id, "amount": min(limit, 50)}
        if end_cursor:
            params["page_id"] = end_cursor

        data = await self._request("GET", "/v2/user/medias", params=params)

        # v2 wraps under {"response": {"items": [...]}, "next_page_id": ...}
        response = data.get("response") if "response" in data else data
        items = response.get("items", []) if isinstance(response, dict) else []

        posts = [self._parse_media(item) for item in items]

        return {
            "posts": posts,
            "post_count": len(posts),
            "end_cursor": data.get("next_page_id") or data.get("next_max_id"),
            "has_more": bool(data.get("next_page_id") or data.get("more_available")),
        }

    # ──��� Post/Media endpoints ───

    async def get_media_by_shortcode(self, shortcode: str) -> dict:
        """Get detailed media info by shortcode (from URL like /p/ABC123/)."""
        data = await self._request(
            "GET", "/v2/media/info/by/code", params={"code": shortcode}
        )
        return self._parse_media(_unwrap_media_response(data))

    async def get_media_by_url(self, post_url: str) -> dict:
        """Get detailed media info by URL.

        This covers app share links whose path does not contain a public
        shortcode, plus future Instagram URL shapes Hiker can resolve.
        """
        data = await self._request(
            "GET", "/v2/media/info/by/url", params={"url": post_url}
        )
        return self._parse_media(_unwrap_media_response(data))

    async def get_media_comments(
        self, media_id: int | str, limit: int = 20
    ) -> list[dict]:
        """Get comments on a media post."""
        data = await self._request(
            "GET", f"/media/{media_id}/comments", params={"amount": limit}
        )
        return [
            {
                "user": c.get("user", {}).get("username", ""),
                "text": c.get("text", ""),
                "created_at": c.get("created_at"),
                "like_count": c.get("comment_like_count", 0),
            }
            for c in data.get("comments", [])
        ]

    # ─── Discovery endpoints ───

    async def search(self, query: str) -> dict:
        """Search for users, hashtags, places."""
        data = await self._request("GET", "/search", params={"query": query})
        users = [
            {
                "username": u.get("username"),
                "full_name": u.get("full_name", ""),
                "follower_count": u.get("follower_count", 0),
                "profile_pic_url": u.get("profile_pic_url", ""),
            }
            for u in data.get("users", [])
        ]
        hashtags = [
            {
                "name": h.get("name"),
                "media_count": h.get("media_count", 0),
            }
            for h in data.get("hashtags", [])
        ]
        return {"users": users, "hashtags": hashtags}

    async def get_hashtag_medias(self, hashtag: str, limit: int = 20) -> dict:
        """Get top posts for a hashtag."""
        data = await self._request(
            "GET", f"/hashtag/{hashtag}/medias", params={"amount": limit}
        )
        posts = [self._parse_media(item) for item in data.get("items", [])]
        return {"hashtag": hashtag, "posts": posts, "post_count": len(posts)}

    # ─── Scraper-compatible interface ───
    # These methods match the interface expected by the Scraper Worker agent

    async def scrape_channel(
        self, handle: str, limit: int = 50, since: str | None = None
    ) -> dict:
        """Scrape channel posts - HikerAPI version."""
        try:
            # Get user info
            user = await self.get_user_by_username(handle)
            if not user.get("user_id"):
                return {"post_count": 0, "error": f"유저 '{handle}'를 찾을 수 없습니다"}

            # Get posts. Hiker returns newest first; for incremental scrapes,
            # trim anything at/after the previously-known shortcode.
            result = await self.get_user_medias(user["user_id"], limit=limit)
            posts = result["posts"]
            if since:
                fresh: list[dict] = []
                for post in posts:
                    if post.get("shortcode") == since:
                        break
                    fresh.append(post)
                posts = fresh

            # Count images
            images_found = sum(len(p.get("image_urls", [])) for p in posts)
            captions_found = sum(1 for p in posts if p.get("caption"))

            return {
                "handle": handle,
                "user": user,
                "post_count": len(posts),
                "posts": posts,
                "images_found": images_found,
                "captions_found": captions_found,
                "has_more": result["has_more"],
            }
        except httpx.HTTPStatusError as e:
            logger.error(f"HikerAPI error for {handle}: {e.response.status_code}")
            return {"post_count": 0, "error": f"API 오류: {e.response.status_code}"}
        except Exception as e:
            logger.error(f"Scrape error for {handle}: {e}")
            return {"post_count": 0, "error": str(e)}

    async def scrape_post(self, post_url: str) -> dict:
        """Scrape a single post by URL.

        Handles URLs with query strings (utm_source, igsh, etc.) and
        any of /p/, /reel/, /reels/, /tv/ path prefixes.
        """
        post_url = (post_url or "").strip()
        if not is_instagram_url(post_url):
            return {"error": f"인스타그램 게시물 URL이 아닙니다: {post_url}"}
        shortcode = extract_shortcode(post_url)
        try:
            if shortcode:
                try:
                    return await self.get_media_by_shortcode(shortcode)
                except Exception as e:
                    logger.warning(f"Hiker shortcode lookup failed for {shortcode}: {e}")
            return await self.get_media_by_url(post_url)
        except Exception as e:
            return {"error": str(e)}

    async def discover_channels(
        self, keywords: list[str], style: str = ""
    ) -> dict:
        """Discover channels via hashtag search."""
        channels = []
        seen_handles = set()

        for keyword in keywords[:5]:
            try:
                # Search by hashtag
                hashtag_result = await self.get_hashtag_medias(keyword, limit=9)

                for post in hashtag_result.get("posts", []):
                    username = post.get("username", "")
                    if username and username not in seen_handles:
                        seen_handles.add(username)
                        channels.append({
                            "handle": username,
                            "source_keyword": keyword,
                            "sample_post": post,
                        })

                # Also do a user search
                search_result = await self.search(keyword)
                for user in search_result.get("users", [])[:3]:
                    username = user.get("username", "")
                    if username and username not in seen_handles:
                        seen_handles.add(username)
                        channels.append({
                            "handle": username,
                            "full_name": user.get("full_name", ""),
                            "follower_count": user.get("follower_count", 0),
                            "source_keyword": keyword,
                        })

            except Exception as e:
                logger.error(f"Discovery error for keyword '{keyword}': {e}")

        return {"channels": channels, "count": len(channels)}

    async def check_session(self) -> dict:
        """Check if API key is valid."""
        try:
            await self._request("GET", "/user/by/username/instagram")
            return {"valid": True}
        except Exception as e:
            return {"valid": False, "error": str(e)}

    # ─── Internal helpers ───

    def _parse_media(self, item: dict) -> dict:
        """Parse a media item into our standard format."""
        media_type = item.get("media_type", 1)
        # media_type: 1=photo, 2=video, 8=carousel

        image_urls = []
        slide_count = 1

        if media_type == 8:
            # Carousel - extract all slides
            carousel_media = item.get("carousel_media", [])
            slide_count = len(carousel_media)
            for slide in carousel_media:
                url = self._best_image_url(slide)
                if url:
                    image_urls.append(url)
        else:
            url = self._best_image_url(item)
            if url:
                image_urls.append(url)

        # Extract caption
        caption_data = item.get("caption") or {}
        caption = caption_data.get("text", "") if isinstance(caption_data, dict) else ""

        # Extract hashtags
        import re
        hashtags = re.findall(r"#(\w+)", caption)

        code = item.get("code") or item.get("shortcode") or ""
        return {
            "instagram_post_id": str(item.get("pk", item.get("id", ""))),
            "shortcode": code,
            "post_url": f"https://www.instagram.com/p/{code}/" if code else "",
            "username": item.get("user", {}).get("username", ""),
            "caption": caption,
            "hashtags": hashtags,
            "image_urls": image_urls,
            "slide_count": max(slide_count, 1),
            "like_count": item.get("like_count", 0),
            "comment_count": item.get("comment_count", 0),
            "post_date": item.get("taken_at"),
            "media_type": "carousel" if media_type == 8 else "photo" if media_type == 1 else "video",
        }

    def _best_image_url(self, item: dict) -> str | None:
        """Extract the highest resolution image URL from a media item."""
        # Try image_versions2 (highest quality)
        versions = item.get("image_versions2", {})
        candidates = versions.get("candidates", [])
        if candidates:
            # Sort by width descending, pick largest
            best = max(candidates, key=lambda c: c.get("width", 0))
            return best.get("url")

        # Fallback to thumbnail_url
        return item.get("thumbnail_url") or item.get("display_url")


# Backward-compatible alias
InstagramScraper = InstagramAPI
