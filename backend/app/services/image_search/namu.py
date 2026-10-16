"""나무위키 문서 사진 — 검색 페이지 → 문서 → 문서에 실린 사진.

2026-10-16 트립앤라이프 지시 「bing·네이버·위키미디어 외에 나무위키도 붙여줘」.
bing 이 **굿즈·블로그 썸네일만** 주는 소재(캐릭터·IP·제품·방송)에서 나무위키 문서에는
그 대상 자체를 찍은 사진이 실려 있다 — 치이카와(문서 이름은 「먼작귀」)에서 단체 그림·
치이카와샵 사진이 나왔다(2026-10-16 실측).

API 는 없다. 검색 페이지에서 문서 주소를 줍고(`/w/...`), 그 문서 HTML 의 `i.namu.wiki`
사진을 꺼낸다. 문서 하나에 아이콘이 100개씩 박혀 있어 **골라내는 것이 일**이다 —

- `data-filesize` 가 작은 것은 전부 아이콘·로고다(「상세 내용 아이콘」 1.2KB,
  「X Corp 아이콘」). 이 칸이 실제 바이트와 거의 같아 **크기로 자른다**.
- 같은 CDN 으로 **광고 그림**도 나온다(「강아지분양」). 광고는 4.7KB 라 같은 크기 자(尺)에
  함께 걸러진다 — 파일명 길이로는 못 가른다(문서 사진도 150자가 넘는다).
- svg·data: 는 버린다 — 아이콘이거나 자리만 잡아 둔 빈 그림이다(실제 주소는 `data-src`).
"""

from __future__ import annotations

import re
import urllib.parse

import httpx

from .base import ImageResult, ImageSearchProvider

_BASE = "https://namu.wiki"
_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)
# 검색 결과의 문서 주소. 「나무위키:」 로 시작하는 관리 문서는 사진이 없어 건너뛴다.
_DOC_RE = re.compile(r'href="(/w/[^"#?]+)"')
_IMG_RE = re.compile(r"<img[^>]*i\.namu\.wiki[^>]*>")
_SRC_RE = re.compile(r"""(?:data-)?src=['"](//i\.namu\.wiki/i/[^'"]+)['"]""")
_SIZE_RE = re.compile(r"""data-filesize=['"](\d+)['"]""")
_ALT_RE = re.compile(r"""alt=['"]([^'"]*)['"]""")

MIN_BYTES = 40_000      # 이보다 작은 것은 아이콘·로고·광고다(실측 — 문서 사진은 49KB~150KB)
_RASTER = (".png", ".jpg", ".jpeg", ".webp", ".gif")
DOCS_READ = 2           # 검색 결과에서 열어 볼 문서 수. 많이 열수록 느리다.


class NamuImageProvider(ImageSearchProvider):
    name = "namu"

    @property
    def enabled(self) -> bool:
        return True

    async def search(self, query: str, limit: int = 10, country: str | None = None) -> list[ImageResult]:
        # ⚠ **Referer 를 붙이지 않는다.** `Referer: https://namu.wiki/` 로 물으면 나무위키가
        #   2.6KB 짜리 빈 껍데기를 준다(2026-10-16 실측 — 안 붙이면 44KB 가 온다).
        headers = {"User-Agent": _UA, "Accept-Language": "ko,en;q=0.8"}
        results: list[ImageResult] = []
        async with httpx.AsyncClient(timeout=20, headers=headers, follow_redirects=True) as client:
            r = await client.get(f"{_BASE}/Search", params={"q": query})
            r.raise_for_status()

            seen: list[str] = []
            for path in _DOC_RE.findall(r.text):
                doc = urllib.parse.unquote(path[3:])
                if doc.startswith("나무위키:") or path in seen:
                    continue
                seen.append(path)
                if len(seen) >= DOCS_READ:
                    break

            for path in seen:
                page = await client.get(_BASE + path)
                if page.status_code != 200:
                    continue
                results.extend(_images(page.text))
                if len(results) >= limit:
                    break
        return results[:limit]


def _images(html: str) -> list[ImageResult]:
    """문서 HTML 에서 **아이콘·광고를 뺀 사진**만 큰 것부터 꺼낸다."""
    rows: list[tuple[int, ImageResult]] = []
    for tag in _IMG_RE.findall(html):
        src = _SRC_RE.search(tag)
        size = _SIZE_RE.search(tag)
        if not src or not size:
            continue
        url = "https:" + src.group(1)
        if not url.lower().endswith(_RASTER):
            continue
        nbytes = int(size.group(1))
        if nbytes < MIN_BYTES:
            continue
        if any(url == got.source_url for _, got in rows):
            continue
        alt = _ALT_RE.search(tag)
        rows.append((nbytes, ImageResult(
            source="namu",
            source_url=url,
            thumbnail_url=url,
            title=(alt.group(1) if alt else "")[:60],
        )))
    # 큰 사진이 문서의 대표 사진일 때가 많다 — 큰 것부터 올린다(크기는 모르니 바이트로 센다).
    return [res for _, res in sorted(rows, key=lambda x: -x[0])]
