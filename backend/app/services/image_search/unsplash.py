"""Unsplash photo search.

Free tier: 50 calls/hour. Docs: https://unsplash.com/documentation
"""

from __future__ import annotations

import httpx

from app.config import settings

from .base import ImageResult, ImageSearchProvider


class UnsplashProvider(ImageSearchProvider):
    name = "unsplash"

    @property
    def enabled(self) -> bool:
        return bool(settings.UNSPLASH_ACCESS_KEY)

    async def search(self, query: str, limit: int = 10, country: str | None = None) -> list[ImageResult]:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                "https://api.unsplash.com/search/photos",
                headers={"Authorization": f"Client-ID {settings.UNSPLASH_ACCESS_KEY}"},
                params={"query": query, "per_page": min(limit, 30)},
            )
            resp.raise_for_status()
            data = resp.json()

        return [
            ImageResult(
                source=self.name,
                source_url=r["urls"]["regular"],
                thumbnail_url=r["urls"]["small"],
                width=r.get("width", 0),
                height=r.get("height", 0),
                title=r.get("alt_description") or r.get("description") or "",
            )
            for r in data.get("results", [])
        ]
