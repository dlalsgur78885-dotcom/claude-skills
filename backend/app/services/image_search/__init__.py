"""Image search providers + unified fallback search.

Two routing profiles coexist (carousel studio feedback #15-16):

- **default** (legacy): naver → pexels → pixabay → unsplash. The original
  routing that the existing "🔄 재검색" button and Step-2 auto-search rely on.

- **v2** (재검색2): bing → naver → wikimedia. Drops stock providers because
  carousels target specific places/items they rarely cover; Bing's image
  scrape catches the broader (incl. Japanese/Chinese) web, Naver carries
  Korean blog reviews, Wikimedia curates landmarks/encyclopedia subjects.

Frontend calls `/images/search?profile=v2` from the new per-cell options
("재검색2") so the two paths stay isolated — break v2 and the old path is
unaffected.
"""

from __future__ import annotations

from .base import ImageResult, ImageSearchProvider
from .bing import BingImageProvider
from .naver import NaverImageProvider
from .pexels import PexelsProvider
from .pixabay import PixabayProvider
from .unsplash import UnsplashProvider
from .wikimedia import WikimediaProvider

PROVIDERS: dict[str, ImageSearchProvider] = {
    "bing":      BingImageProvider(),
    "naver":     NaverImageProvider(),
    "wikimedia": WikimediaProvider(),
    "unsplash":  UnsplashProvider(),
    "pexels":    PexelsProvider(),
    "pixabay":   PixabayProvider(),
}

# Legacy default — preserved so the original Step-2 search keeps working.
DEFAULT_ORDER = ["naver", "pexels", "pixabay", "unsplash"]

# Profile-driven orderings. Pick via /images/search?profile=v2 (feedback
# #15-16). Add new profiles here; callers without a profile= get the legacy.
ORDER_PROFILES: dict[str, list[str]] = {
    "default": DEFAULT_ORDER,
    "v2":      ["bing", "naver", "wikimedia"],
}


async def search_all(
    query: str,
    limit: int = 10,
    order: list[str] | None = None,
    country: str | None = None,
    profile: str | None = None,
) -> list[ImageResult]:
    """Run providers sequentially, stopping when `limit` reached.

    `profile` (default | v2) selects a built-in ordering; `order=` overrides
    when explicit. Unknown profile falls back to DEFAULT_ORDER.
    """
    if order is None:
        order = ORDER_PROFILES.get(profile or "default", DEFAULT_ORDER)
    results: list[ImageResult] = []
    for name in order:
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
    "ORDER_PROFILES",
    "search_all",
]
