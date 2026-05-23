"""Image search providers + unified fallback search.

Carousel studio feedback #15-16 (2026-05): stock photo providers
(Pexels/Pixabay/Unsplash) dropped — they rarely carry the specific places,
items, or brands that carousels are actually about. Naver covers Korean
blog content, Bing covers the broader (incl. Japanese/Chinese) web, and
Wikimedia covers landmarks / famous subjects with high-quality curation.

Default priority: bing → naver → wikimedia.

Bing-via-scrape replaces the retired Bing Search API (2025-08-11) — the
`images/async` endpoint still serves HTML chunks without auth. See bing.py.
"""

from __future__ import annotations

from .base import ImageResult, ImageSearchProvider
from .bing import BingImageProvider
from .naver import NaverImageProvider
from .wikimedia import WikimediaProvider

PROVIDERS: dict[str, ImageSearchProvider] = {
    "bing": BingImageProvider(),
    "naver": NaverImageProvider(),
    "wikimedia": WikimediaProvider(),
}

# Bing first — jacks-of-all-trades: catches local-language web content for any
# country. Naver second for Korean blog reviews. Wikimedia last as a curated
# landmark/encyclopedia fallback.
DEFAULT_ORDER = ["bing", "naver", "wikimedia"]


async def search_all(
    query: str,
    limit: int = 10,
    order: list[str] | None = None,
    country: str | None = None,
) -> list[ImageResult]:
    """Run providers sequentially, stopping when `limit` reached."""
    results: list[ImageResult] = []
    for name in (order or DEFAULT_ORDER):
        if len(results) >= limit:
            break
        prov = PROVIDERS.get(name)
        if prov is None:
            continue
        results.extend(await prov.safe_search(query, limit - len(results), country=country))
    return results[:limit]


__all__ = [
    "ImageResult",
    "ImageSearchProvider",
    "PROVIDERS",
    "DEFAULT_ORDER",
    "search_all",
]
