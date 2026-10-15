"""링크 하나로 캐러셀 재료를 받아 온다 — X · 인스타그램 · 그 밖의 웹.

## 왜 이런 모양인가

X인용 축은 소재를 grok 검색으로만 찾는다. 2026-10-13 트립앤라이프 지시 — 「X 뿐 아니라
커뮤니티·인스타그램 등 다양한 곳에서 가져오고, **링크를 넣으면 바로 결과물이 생성**되게」.
그래서 1단계(검색)를 건드리지 않고 **입구를 하나 더** 둔다.

돌려주는 모양은 `x_search.verify` 가 주는 후보 레코드와 **같다**. 그래야 뒤 단계
(훅·본문·사진·캡션·캐러셀 생성)를 하나도 고치지 않고 그대로 쓸 수 있다.

| 링크 | 받는 길 | 쓰는 것 |
|---|---|---|
| x.com · twitter.com | 원문 | `x_search.verify` (FxTwitter) |
| instagram.com | HikerAPI | `InstagramAPI.scrape_post` |
| 루리웹 · 디시인사이드 · 에펨코리아 | 그 글의 **본문 칸만** 잘라 글·사진을 긁는다 | 이 파일 |
| 그 밖(커뮤니티·뉴스·블로그) | og 태그 + `<p>` 글 (본문 칸을 모르니 거칠다) | 이 파일 |

## 함정

- 웹은 생김새가 다 달라서 **본문을 완벽히 뽑을 수 없다.** og 태그와 `<p>` 글만 믿고,
  모자라면 사람이 고친다 — **지어내지 않는다.**
- 수치(조회·좋아요·댓글)는 **주는 곳만** 채운다. 웹은 0 이다. 0 은 「모른다」는 뜻이고,
  1단계의 조회 5만·댓글 50 기준은 **링크 입구에 걸지 않는다** — 사람이 직접 고른 글이다.
- 글 칸을 모르는 사이트는 **메뉴·배너 글자가 섞인다**(2026-10-13 실측 — 디시 글에서
  「야간 모드를 이용해 보세요」, 루리웹 글에서 게임 목록이 따라 들어왔다). 그래서 아는
  사이트는 `_SITE_BODY` 로 본문 칸을 먼저 잘라낸다.
- 글자 코드가 헤더에 없으면 `<meta charset>` 을 보고 디코딩한다(일본 커뮤니티는 아직
  Shift_JIS 로 내려오는 곳이 있다). 그냥 utf-8 로 읽으면 글자가 깨진다.
- 에펨코리아는 서버에서 바로 받으면 **430 으로 막는다**(2026-10-13 실측). 브라우저로
  열어야 한다 — 봇의 playwright 캡처를 쓰는 길은 아직 붙이지 않았다.
"""

import asyncio
import logging
import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urljoin, urlsplit

import httpx

logger = logging.getLogger(__name__)

SOURCE_X = "x"
SOURCE_INSTAGRAM = "instagram"
SOURCE_WEB = "web"

# 웹에서 긁어 올 최대 사진 수. 본문 장수는 이야기가 정하므로(3-3단계) 넉넉히만 준다.
WEB_MAX_PHOTOS = 10
# 본문 글은 훅·요약 재료다. 페이지 전체를 실으면 codex 토큰만 먹는다.
WEB_MAX_TEXT = 2000
# 사진 한 장 상한. 이보다 큰 것은 본문 사진이 아니라 내려받기 파일일 가능성이 크다.
MAX_PHOTO_BYTES = 20 * 1024 * 1024

_X_STATUS_RE = re.compile(r"(?:x|twitter)\.com/[A-Za-z0-9_]{1,20}/status/(\d+)")
_META_RE = re.compile(
    r"<meta\s+[^>]*?(?:property|name)\s*=\s*[\"']([^\"']+)[\"'][^>]*?content\s*=\s*[\"']([^\"']*)[\"']",
    re.IGNORECASE | re.DOTALL,
)
_META_REV_RE = re.compile(
    r"<meta\s+[^>]*?content\s*=\s*[\"']([^\"']*)[\"'][^>]*?(?:property|name)\s*=\s*[\"']([^\"']+)[\"']",
    re.IGNORECASE | re.DOTALL,
)
_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_CHARSET_RE = re.compile(rb"""charset\s*=\s*["']?\s*([A-Za-z0-9_\-]+)""", re.IGNORECASE)
_DROP_TAGS_RE = re.compile(
    r"<(script|style|noscript|template|svg)\b.*?</\1>", re.IGNORECASE | re.DOTALL)
_BLOCK_END_RE = re.compile(r"<br\s*/?>|</(?:p|div|li|h[1-6]|tr|blockquote)>", re.IGNORECASE)
_P_RE = re.compile(r"<(?:p|h[1-3]|dd|li)\b[^>]*>(.*?)</(?:p|h[1-3]|dd|li)>", re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")
_IMG_SRC_RE = re.compile(
    r"<img\b[^>]*?\ssrc\s*=\s*[\"']([^\"']+)[\"']", re.IGNORECASE)
# 아이콘·배너·버튼은 본문 사진이 아니다. 주소에 이런 말이 들어간 것은 뺀다.
_JUNK_IMG_RE = re.compile(
    r"(icon|logo|avatar|sprite|banner|button|badge|blank|spacer|pixel|ads?[-_/]|emoji"
    # 사이트가 꾸미기로 쓰는 호스트·폴더 — 본문 사진은 여기 없다(2026-10-13 실측).
    r"|nstatic\.dcinside\.com|img\.ruliweb\.com|\$\{)",
    re.IGNORECASE)
# 본문 아래 **버튼·수치 줄**. 이 줄이 나오면 글은 거기서 끝이다(2026-10-13 실측 —
# 루리웹 「분리수거·글쓰기·스크랩」, 디시 「추천검색·개념 추천·원본 첨부파일」).
_STOP_LINES = frozenset((
    "추천검색", "추천 비추천", "개념 추천", "개념 비추천", "공유", "스크랩", "신고", "차단",
    "원본 첨부파일 1", "분리수거", "글쓰기", "글꼴", "URL 복사", "목록", "이전글", "다음글",
    "펌 0", "댓글", "답글",
))
_NUMBER_ONLY_RE = re.compile(r"^[\d,.\s|/-]+$")
_FILENAME_RE = re.compile(r"^[\w.\-]+\.(?:jpe?g|png|gif|webp)$", re.IGNORECASE)
# 페이지 제목 뒤에 붙는 사이트 이름. 「… - 실시간 베스트 갤러리」·「… | 루리웹」 같은 꼬리다.
_SITE_SUFFIX_RE = re.compile(
    r"\s*[-|]\s*[^-|]{0,40}(?:갤러리|게시판|커뮤니티|채널|루리웹|디시인사이드|에펨코리아)\s*$")
_IMG_EXT_RE = re.compile(r"\.(jpe?g|png|webp)(\?|$)", re.IGNORECASE)

# 아는 커뮤니티의 **본문 칸** — (사이트, 본문 시작, 본문 끝). 시작부터 끝 사이만 쓴다.
# ⚠ `</div>` 짝으로 자르려 했더니 두 사이트 모두 **댓글·사이드 메뉴까지 먹었다**
#   (2026-10-13 실측 — 루리웹에 「(IP보기클릭)」 댓글 줄, 디시에 「한줄 알림」 설정 글).
#   페이지 HTML 이 짝이 안 맞아서다. 그래서 **끝 표시**를 사이트마다 안다.
_SITE_BODY = (
    (re.compile(r"(^|\.)ruliweb\.com$", re.IGNORECASE),
     re.compile(r"<div[^>]*class=[\"'][^\"']*view_content[^\"']*[\"'][^>]*>", re.IGNORECASE),
     re.compile(r"class=[\"'][^\"']*comment_count", re.IGNORECASE)),
    (re.compile(r"(^|\.)dcinside\.com$", re.IGNORECASE),
     re.compile(r"<div[^>]*class=[\"'][^\"']*write_div[^\"']*[\"'][^>]*>", re.IGNORECASE),
     re.compile(r"id=[\"']focus_cmt[\"']|class=[\"'][^\"']*(?:cmt_write|append_file)", re.IGNORECASE)),
    (re.compile(r"(^|\.)fmkorea\.com$", re.IGNORECASE),
     re.compile(r"<(?:div|article)[^>]*class=[\"'][^\"']*(?:xe_content|rd_body)[^\"']*[\"'][^>]*>", re.IGNORECASE),
     re.compile(r"id=[\"']comment[\"']|class=[\"'][^\"']*fdb_lst_ul", re.IGNORECASE)),
)
# 끝 표시를 못 찾았을 때 자를 길이. 본문만 보려는 것이라 넉넉하되 페이지 전체는 안 된다.
BODY_SLICE_CAP = 30_000

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")


async def download_photos(urls: list[str], limit: int = 0) -> list[bytes]:
    """원문 사진을 **이 PC 에서** 받아 온다.

    서버(AWS)에서 받으면 안 되는 이유 — 루리웹 이미지 호스트는 AWS 에서 아예 응답하지
    않는다(2026-10-13 실측: 서버 `000`, 이 PC `200`). 그래서 일꾼이 받아 서버로 올린다.
    디시는 레퍼러가 없으면 403 이라 `images._referer_for` 와 같은 값을 붙인다.
    """
    from app.api.images import _referer_for

    async def one(client: httpx.AsyncClient, url: str) -> bytes | None:
        host = (urlsplit(url).hostname or "")
        try:
            r = await client.get(url, headers={"Referer": _referer_for(host)})
            r.raise_for_status()
        except Exception as e:
            logger.warning(f"[link] 사진을 못 받았습니다 — {url[:110]} ({type(e).__name__})")
            return None
        if not r.content or len(r.content) > MAX_PHOTO_BYTES:
            logger.warning(f"[link] 사진 크기가 맞지 않습니다({len(r.content)}) — {url[:110]}")
            return None
        return r.content

    picked = [u for u in urls if u][:limit or len(urls)]
    if not picked:
        return []
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True,
                                 headers={"User-Agent": _UA}) as client:
        got = await asyncio.gather(*(one(client, u) for u in picked))
    return [g for g in got if g]


def classify(url: str) -> str:
    """링크가 어디 것인지 가린다."""
    host = (urlsplit((url or "").strip()).hostname or "").lower()
    if host.endswith("x.com") or host.endswith("twitter.com"):
        return SOURCE_X
    if host.endswith("instagram.com"):
        return SOURCE_INSTAGRAM
    return SOURCE_WEB


async def fetch(url: str) -> dict[str, Any]:
    """링크 하나를 **1단계 후보 레코드 한 건**으로 바꾼다.

    못 받으면 `RuntimeError` 를 올린다 — 빈 레코드를 돌려주면 뒤 단계가 엉뚱한 것을
    만든다(X인용은 후보가 곧 캐러셀 한 편이다).
    """
    url = (url or "").strip()
    if not urlsplit(url).scheme in ("http", "https"):
        raise RuntimeError(f"http/https 링크가 아닙니다: {url[:120]}")

    kind = classify(url)
    if kind == SOURCE_X:
        return await _from_x(url)
    if kind == SOURCE_INSTAGRAM:
        return await _from_instagram(url)
    return await _from_web(url)


async def _from_x(url: str) -> dict[str, Any]:
    from app.services import x_search

    m = _X_STATUS_RE.search(url)
    if not m:
        raise RuntimeError(f"X 게시물 주소가 아닙니다(…/status/숫자): {url[:120]}")
    post_id = m.group(1)
    # 1단계와 **같은 길**로 읽는다 — 수치·사진·영상 판정이 달라지면 안 된다.
    # 영상이 붙어도 버리지 않는다(사람이 직접 고른 글이다). 본문 단계가 사진만 쓴다.
    alive = await x_search.verify([{"post_id": post_id, "url": url, "topic": ""}])
    if not alive:
        raise RuntimeError("X 원문을 열지 못했습니다 — 삭제·비공개일 수 있습니다")
    got = alive[0]
    return {
        **got,
        "source": SOURCE_X,
        "topic": str(got.get("topic") or "").strip() or _first_line(got.get("text")),
    }


async def _from_instagram(url: str) -> dict[str, Any]:
    from app.services.instagram import InstagramAPI

    api = InstagramAPI()
    try:
        data = await api.scrape_post(url)
    finally:
        await api.close()
    if not isinstance(data, dict) or data.get("error"):
        raise RuntimeError(f"HikerAPI 오류: {(data or {}).get('error') or '빈 응답'}")

    caption = str(data.get("caption") or "")
    taken = data.get("post_date")
    made = ""
    if isinstance(taken, (int, float)) and taken:
        made = datetime.fromtimestamp(int(taken), tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    photo_urls = [u for u in (data.get("image_urls") or []) if u]
    return {
        "source": SOURCE_INSTAGRAM,
        "url": str(data.get("post_url") or url),
        "post_id": str(data.get("instagram_post_id") or ""),
        "topic": _first_line(caption),
        "text": caption,
        "account": str(data.get("username") or ""),
        "author": str(data.get("username") or ""),
        "created_at": made,
        "photos": len(photo_urls),
        "photo_urls": photo_urls,
        "views": 0,
        "likes": int(data.get("like_count") or 0),
        "replies": int(data.get("comment_count") or 0),
    }


async def _from_web(url: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=25.0, follow_redirects=True,
                                 headers={"User-Agent": _UA}) as client:
        r = await client.get(url)
        r.raise_for_status()
        html = _decode(r)

    final = str(r.url)
    host = (urlsplit(final).hostname or "").lower()
    meta = _metas(html)
    title = (meta.get("og:title") or meta.get("twitter:title")
             or _text_of(_TITLE_RE.search(html)) or "")
    # 본문 칸을 아는 사이트는 그 안만 본다. 모르면 페이지 전체에서 거칠게 긁는다.
    article = _article_html(html, host)
    desc = "" if article else (meta.get("og:description") or meta.get("twitter:description")
                               or meta.get("description") or "")
    body = _body_text(article or html, article=bool(article))
    text = "\n".join(t for t in (desc.strip(), body) if t)[:WEB_MAX_TEXT]
    if not title and not text:
        raise RuntimeError("페이지에서 글을 찾지 못했습니다 — 주소를 확인해 주세요")

    photo_urls = _web_photos(article or html, final, meta, inside_article=bool(article))
    return {
        "source": SOURCE_WEB,
        "url": final,
        "post_id": "",
        # 페이지 제목에는 사이트 이름이 붙어 온다(「… - 실시간 베스트 갤러리」) — 떼고 쓴다.
        "topic": _SITE_SUFFIX_RE.sub("", _clean(title)) or _first_line(text),
        "text": text,
        "account": host,
        "author": _clean(meta.get("og:site_name") or "") or host,
        "created_at": str(meta.get("article:published_time") or ""),
        "photos": len(photo_urls),
        "photo_urls": photo_urls,
        "views": 0,
        "likes": 0,
        "replies": 0,
    }


def _decode(r: httpx.Response) -> str:
    """헤더에 charset 이 없으면 `<meta charset>` 을 보고 디코딩한다."""
    if "charset=" in (r.headers.get("content-type") or "").lower():
        return r.text
    m = _CHARSET_RE.search(r.content[:4096])
    if m:
        try:
            return r.content.decode(m.group(1).decode("ascii"), errors="replace")
        except (LookupError, UnicodeDecodeError):
            pass
    return r.text


def _metas(html: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in _META_RE.findall(html):
        out.setdefault(key.strip().lower(), _clean(value))
    # 속성 순서가 거꾸로(content 가 먼저) 적힌 페이지도 있다.
    for value, key in _META_REV_RE.findall(html):
        out.setdefault(key.strip().lower(), _clean(value))
    return out


def _body_text(html: str, article: bool = False) -> str:
    """본문 글을 줄 단위로 모은다.

    본문 칸을 잘라 온 경우(`article`)는 **태그를 전부 떼어** 읽는다 — 커뮤니티 글은
    `<p>` 가 아니라 `<div>` 안에 그냥 적혀 있다(2026-10-13 실측 — `<p>` 만 보면 글이
    통째로 빈다). 모르는 사이트는 그렇게 하면 메뉴까지 섞이므로 `<p>` 만 본다.
    """
    stripped = _DROP_TAGS_RE.sub(" ", html)
    if article:
        return _lines_of(_BLOCK_END_RE.sub("\n", stripped))
    lines: list[str] = []
    seen: set[str] = set()
    for chunk in _P_RE.findall(stripped):
        line = _clean(_TAG_RE.sub(" ", chunk))
        # 메뉴·꼬리말에 섞인 한두 글자 조각은 버린다. 사진 파일명 줄도 글이 아니다.
        if len(line) < 10 or line in seen or _FILENAME_RE.match(line):
            continue
        seen.add(line)
        lines.append(line)
        if sum(len(x) for x in lines) > WEB_MAX_TEXT:
            break
    return "\n".join(lines)


def _lines_of(html: str) -> str:
    out: list[str] = []
    seen: set[str] = set()
    for raw in _TAG_RE.sub("", html).splitlines():
        line = _clean(raw)
        if line in _STOP_LINES:
            break
        # 잘린 태그 조각·수치만 있는 줄·사진 파일명은 글이 아니다.
        if (not line or line in seen or line.startswith("<")
                or _FILENAME_RE.match(line) or _NUMBER_ONLY_RE.match(line)):
            continue
        seen.add(line)
        out.append(line)
        if sum(len(x) for x in out) > WEB_MAX_TEXT:
            break
    return "\n".join(out)


def _web_photos(html: str, base: str, meta: dict[str, str],
                inside_article: bool = False) -> list[str]:
    """본문 칸을 잘라 왔으면 그 안의 `<img>` 를 **순서대로** 쓴다.

    ⚠ 본문 칸을 모를 때만 og:image 를 앞에 세운다. 디시 본문 사진은 `viewimage.php` 처럼
      확장자가 없어서(2026-10-13 실측) 확장자 조건은 본문 칸 밖에서만 본다.
    """
    out: list[str] = []
    heads = [] if inside_article else [meta.get("og:image") or "", meta.get("twitter:image") or ""]
    for cand in [*heads, *_IMG_SRC_RE.findall(html)]:
        if not cand:
            continue
        full = urljoin(base, _clean(cand))
        if not full.startswith(("http://", "https://")):
            continue
        if _JUNK_IMG_RE.search(full):
            continue
        if not inside_article and not _IMG_EXT_RE.search(full):
            continue
        if full not in out:
            out.append(full)
        if len(out) >= WEB_MAX_PHOTOS:
            break
    return out


def _article_html(html: str, host: str) -> str:
    """아는 커뮤니티면 **본문 칸만** 잘라 돌려준다. 모르는 곳이면 빈 문자열."""
    for host_re, start_re, end_re in _SITE_BODY:
        if not host_re.search(host):
            continue
        start = start_re.search(html)
        if not start:
            continue
        rest = html[start.start():]
        end = end_re.search(rest)
        return rest[:min(end.start() if end else BODY_SLICE_CAP, BODY_SLICE_CAP)]
    return ""


def _clean(text: str) -> str:
    out = (text or "").replace("&nbsp;", " ")
    for a, b in (("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"), ("&quot;", '"'), ("&#39;", "'")):
        out = out.replace(a, b)
    return re.sub(r"\s+", " ", out).strip()


def _text_of(m: re.Match[str] | None) -> str:
    return _clean(_TAG_RE.sub(" ", m.group(1))) if m else ""


def _first_line(text: Any) -> str:
    """제목이 없을 때 쓰는 임시 제목 — 첫 줄을 자른다(뒤에서 codex 가 다듬는다)."""
    first = next((line.strip() for line in str(text or "").splitlines() if line.strip()), "")
    return first[:60]
