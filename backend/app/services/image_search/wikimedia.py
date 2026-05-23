"""Wikimedia Commons image search — no API key, no quota.

MediaWiki's `action=query&generator=search&gsrnamespace=6` finds File: pages
matching a query, then `prop=imageinfo` resolves them to actual image URLs.
Returns high-quality, freely licensed images. Best for landmarks / famous
places / encyclopedia subjects; sparse for restaurant/product queries —
pair with Bing or Naver for broad coverage.

Filters out SVG / non-image MIME types and tiny thumbnails (Commons hosts a
lot of category icons that are useless for carousel cells).
"""

from __future__ import annotations

import httpx

from .base import ImageResult, ImageSearchProvider

_URL = "https://commons.wikimedia.org/w/api.php"
# A descriptive User-Agent is required by Wikimedia's robots policy.
_UA = "carousel-studio/1.0 (+https://3-35-18-166.sslip.io)"


class WikimediaProvider(ImageSearchProvider):
    name = "wikimedia"

    @property
    def enabled(self) -> bool:
        return True

    async def search(self, query: str, limit: int = 10, country: str | None = None) -> list[ImageResult]:
        params = {
            "action": "query",
            "format": "json",
            "generator": "search",
            "gsrsearch": query,
            "gsrlimit": min(50, max(limit, 10)),
            "gsrnamespace": 6,                  # File: namespace only
            "prop": "imageinfo",
            "iiprop": "url|size|mime",
            "iiurlwidth": 800,                  # request a ~800px thumbnail
            "origin": "*",
        }
        async with httpx.AsyncClient(timeout=15, headers={"User-Agent": _UA}) as client:
            r = await client.get(_URL, params=params)
            r.raise_for_status()
            data = r.json() if r.text else {}

        pages = (data.get("query") or {}).get("pages") or {}
        results: list[ImageResult] = []
        for _id, page in pages.items():
            infos = page.get("imageinfo") or []
            if not infos:
                continue
            info = infos[0]
            mime = (info.get("mime") or "").lower()
            # Commons hosts SVGs / PDFs / videos under namespace=6. Drop
            # anything that isn't a raster image — they break canvas render.
            if mime and (not mime.startswith("image/") or mime == "image/svg+xml"):
                continue
            url = info.get("url") or ""
            thumb = info.get("thumburl") or url
            try:
                w = int(info.get("width") or 0)
                h = int(info.get("height") or 0)
            except (TypeError, ValueError):
                w, h = 0, 0
            # Drop tiny images — category page icons, flags, etc.
            if w and h and (w < 300 or h < 300):
                continue
            results.append(ImageResult(
                source=self.name,
                source_url=url,
                thumbnail_url=thumb,
                width=w,
                height=h,
                title=(page.get("title") or "").replace("File:", ""),
            ))
            if len(results) >= limit:
                break
        return results
