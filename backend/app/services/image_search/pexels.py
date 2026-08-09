"""Pexels photo search.

Free tier: 200 calls/hour. Docs: https://www.pexels.com/api/documentation/
"""

from __future__ import annotations

import httpx

from app.config import settings

from .base import ImageResult, ImageSearchProvider


class PexelsProvider(ImageSearchProvider):
    name = "pexels"

    @property
    def enabled(self) -> bool:
        return bool(settings.PEXELS_API_KEY)

    async def search(self, query: str, limit: int = 10, country: str | None = None) -> list[ImageResult]:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                "https://api.pexels.com/v1/search",
                headers={"Authorization": settings.PEXELS_API_KEY},
                params={
                    "query": query,
                    "per_page": min(limit, 80),
                    "locale": "ko-KR",
                },
            )
            resp.raise_for_status()
            data = resp.json()

        return [
            ImageResult(
                source=self.name,
                source_url=p["src"]["large2x"],
                thumbnail_url=p["src"]["medium"],
                width=p.get("width", 0),
                height=p.get("height", 0),
                title=p.get("alt") or p.get("photographer") or "",
            )
            for p in data.get("photos", [])
        ]
