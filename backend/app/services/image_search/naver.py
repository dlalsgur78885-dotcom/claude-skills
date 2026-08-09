"""Naver image search via desktop search page (no API key, no SerpAPI).

Naver doesn't expose a stable public JSON endpoint without auth, but the
desktop image search HTML embeds image records inline. We extract
`originalUrl` + `lensThumb` with regex. Width/height are unknown until
download (Naver doesn't include size metadata in the embedded records).

Fragile by nature — Naver may change the embedded JSON keys at any time.
"""

from __future__ import annotations

import re

import httpx

from .base import ImageResult, ImageSearchProvider
from .proxy_pool import next_proxy

_URL = "https://search.naver.com/search.naver"
_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
_RECORD_RE = re.compile(
    r'"lensThumb":"(?P<thumb>[^"]+)"[^{}]*?"originalUrl":"(?P<orig>[^"]+)"'
)


def _unescape(s: str) -> str:
    return s.replace("\\u0026", "&").replace("\\/", "/")


class NaverImageProvider(ImageSearchProvider):
    name = "naver"

    @property
    def enabled(self) -> bool:
        return True

    async def search(self, query: str, limit: int = 10, country: str | None = None) -> list[ImageResult]:
        params = {"where": "image", "query": query, "sm": "tab_jum"}
        proxy = next_proxy(country)
        client_kwargs = {
            "timeout": 15,
            "headers": {"User-Agent": _UA, "Accept-Language": "ko-KR"},
            "follow_redirects": True,
        }
        if proxy:
            # httpx 0.28+ uses `proxy` (singular); older versions used `proxies` (mapping)
            client_kwargs["proxy"] = proxy
        async with httpx.AsyncClient(**client_kwargs) as client:
            r = await client.get(_URL, params=params)
            r.raise_for_status()

        results: list[ImageResult] = []
        for m in _RECORD_RE.finditer(r.text):
            results.append(ImageResult(
                source=self.name,
                source_url=_unescape(m.group("orig")),
                thumbnail_url=_unescape(m.group("thumb")),
            ))
            if len(results) >= limit:
                break
        return results
