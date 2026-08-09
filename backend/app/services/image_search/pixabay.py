"""Pixabay image search. `transparent=True` switches to PNG illustrations.

Free tier: 100 calls/min, no daily cap. Docs: https://pixabay.com/api/docs/
"""

from __future__ import annotations

import httpx

from app.config import settings

from .base import ImageResult, ImageSearchProvider


class PixabayProvider(ImageSearchProvider):
    name = "pixabay"

    @property
    def enabled(self) -> bool:
        return bool(settings.PIXABAY_API_KEY)

    async def search(
        self, query: str, limit: int = 10, country: str | None = None, transparent: bool = False
    ) -> list[ImageResult]:
        params: dict[str, str | int] = {
            "key": settings.PIXABAY_API_KEY,
            "q": query,
            "per_page": min(limit, 200),
            "safesearch": "true",
        }
        if transparent:
            params["image_type"] = "illustration"
            params["colors"] = "transparent"
        else:
            params["image_type"] = "photo"

        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get("https://pixabay.com/api/", params=params)
            resp.raise_for_status()
            data = resp.json()

        return [
            ImageResult(
                source=self.name,
                source_url=h["largeImageURL"],
                thumbnail_url=h.get("previewURL", ""),
                width=h.get("imageWidth", 0),
                height=h.get("imageHeight", 0),
                title=h.get("tags", ""),
                has_transparency=transparent,
            )
            for h in data.get("hits", [])
        ]
