"""Tier-1 (metadata-only) relevance scoring for image search results.

Cheap signals only — no download, no vision. Goal: push obvious noise
(logos, banners, blog thumbnails, off-topic) to the bottom of the list
before the user ever sees it.

Applied uniformly by /api/images/search, so the three buttons that share
that endpoint — Step-2 검색 / 🔄 재검색 / 🔄 재검색2 — all benefit
without their own wiring.

Conservative on purpose: re-orders, never drops. A wrong drop loses the
one image the user actually wanted; a wrong reorder is invisible because
top-N display still shows it.
"""

from __future__ import annotations

import re

from .base import ImageResult


# Per-provider trust baseline. Stock providers rarely match a specific
# place/dish — we keep them but start them behind real-web sources.
_SOURCE_WEIGHT = {
    "wikimedia": 15,
    "bing":       5,
    "naver":      0,
    "pexels":    -5,
    "pixabay":   -5,
    "unsplash":  -5,
}

# Words that strongly suggest the asset is a logo / icon / map / coupon /
# menu / thumbnail rather than a real photo of the subject. Matched against
# (title + source_url) lowercased.
_NOISE_TOKENS: tuple[str, ...] = (
    "logo", "icon", "favicon",
    "banner", "coupon", "쿠폰",
    "로고", "아이콘",
    "메뉴판",
    "map", "지도", "map_",
    "썸네일", "thumb_", "/thumb/",
)

# Tokenize Hangul / Kana / Han / Latin alphanumerics together, drop noise.
_TOKEN_RE = re.compile(r"[A-Za-z0-9぀-ヿ一-鿿가-힣]+")


def _tokenize(s: str) -> list[str]:
    return [t for t in _TOKEN_RE.findall(s.lower()) if len(t) >= 2]


def _noise_penalty(title: str, source_url: str) -> int:
    hay = (title + " " + source_url).lower()
    return sum(-10 for w in _NOISE_TOKENS if w in hay)


def _title_match_score(query: str, title: str) -> int:
    """Title-vs-query match. Empty title = 0 (no signal, no penalty)."""
    if not title:
        return 0
    q = query.lower().strip()
    t = title.lower()
    if q and q in t:
        return 35                            # full-phrase hit — strongest signal
    q_tokens = _tokenize(query)
    if not q_tokens:
        return 0
    hits = sum(1 for tok in q_tokens if tok in t)
    if hits == 0:
        return -5
    return min(hits * 12, 30)


def is_bad_format(r: ImageResult) -> bool:
    """Hard exclude — formats that are never a real photo for carousel use.

    Scoring penalizes; this drops. SVG is vector (icon/logo by definition),
    GIF is almost always animation/sticker/emoji at search-result quality,
    and a transparent PNG arriving via photo search is overwhelmingly a logo
    or product cutout that doesn't belong on a content slide.
    """
    if r.has_transparency:
        return True
    url = r.source_url.lower().split("?", 1)[0].split("#", 1)[0]
    return url.endswith(".svg") or url.endswith(".gif")


def filter_bad_formats(results: list[ImageResult]) -> list[ImageResult]:
    return [r for r in results if not is_bad_format(r)]


def _dimension_score(w: int, h: int) -> int:
    """Penalize sizes / aspect ratios that scream logo/banner/thumb."""
    if not w or not h:
        return 0                             # provider didn't report (naver) — neutral
    if w < 200 or h < 200:
        return -20                           # tiny — thumbnail or logo
    ar = w / h
    if ar > 3.5 or ar < 0.3:
        return -15                           # wide banner or vertical menu strip
    if 0.85 <= ar <= 1.15 and max(w, h) < 400:
        return -10                           # small square — logo suspect
    if w >= 600 and h >= 400:
        return +5                            # healthy size
    return 0


def score_one(r: ImageResult, query: str) -> int:
    return (
        _SOURCE_WEIGHT.get(r.source, 0)
        + _title_match_score(query, r.title)
        + _noise_penalty(r.title, r.source_url)
        + _dimension_score(r.width, r.height)
    )


def rerank(results: list[ImageResult], query: str) -> list[tuple[ImageResult, int]]:
    """Return [(result, score), ...] sorted by score desc (stable)."""
    scored = [(r, score_one(r, query)) for r in results]
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored
