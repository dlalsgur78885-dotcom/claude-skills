"""Bing image search via the `bing.com/images/async` endpoint (no API key,
no Playwright). The Bing Search API itself was retired on 2025-08-11, but the
async endpoint still returns HTML chunks with embedded JSON metadata for
each result card — and Microsoft is famously tolerant of scrapers.

Each result card is `<a class="iusc" ... m="{escaped JSON}">`. The JSON
carries `murl` (full image URL), `turl` (thumbnail), `mw`/`mh` (dimensions),
`purl` (host page), `t` (alt/title). httpx-only (≈300ms/query) — replaces
the older Playwright variant at backend/app/services/bing_scraper.py which
spun a headless Chromium per query (3~5s each, way too slow for fan-out)."""

from __future__ import annotations

import html
import json
import re
import urllib.parse

import httpx

from .base import ImageResult, ImageSearchProvider
from .proxy_pool import next_proxy

_URL = "https://www.bing.com/images/async"
_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)
# Each result anchor: `<a class="iusc" ... m="{...json...}">`. Attribute value
# is HTML-escaped JSON; we unescape then json.loads. Match the m="..." chunk
# tightly to avoid greedy capture across cards.
_M_RE = re.compile(r'class="iusc"[^>]*?\bm="([^"]+)"', re.S)


class BingImageProvider(ImageSearchProvider):
    name = "bing"

    @property
    def enabled(self) -> bool:
        return True

    async def search(self, query: str, limit: int = 10, country: str | None = None) -> list[ImageResult]:
        params = {
            "q": query,
            "first": 0,
            "count": min(50, max(limit * 2, 20)),
            "adlt": "off",
            "form": "IRFLTR",
        }
        proxy = next_proxy(country)
        client_kwargs: dict = {
            "timeout": 15,
            "headers": {
                "User-Agent": _UA,
                "Accept-Language": "ko,ja;q=0.9,en;q=0.8",
                # A Referer that looks like a real search session — Bing
                # occasionally returns empty results for naked requests.
                "Referer": "https://www.bing.com/images/search?q=" + urllib.parse.quote_plus(query),
            },
            "follow_redirects": True,
        }
        if proxy:
            client_kwargs["proxy"] = proxy
        async with httpx.AsyncClient(**client_kwargs) as client:
            r = await client.get(_URL, params=params)
            r.raise_for_status()

        results: list[ImageResult] = []
        for m_match in _M_RE.finditer(r.text):
            raw = m_match.group(1)
            try:
                meta = json.loads(html.unescape(raw))
            except json.JSONDecodeError:
                continue
            murl = meta.get("murl") or ""
            if not murl:
                continue
            try:
                mw = int(meta.get("mw") or 0)
                mh = int(meta.get("mh") or 0)
            except (TypeError, ValueError):
                mw, mh = 0, 0
            results.append(ImageResult(
                source=self.name,
                source_url=murl,
                thumbnail_url=meta.get("turl") or murl,
                width=mw,
                height=mh,
                title=meta.get("t") or "",
            ))
            if len(results) >= limit:
                break
        return results
