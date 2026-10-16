"""X(트위터) 게시물을 찾아온다 — X인용 축의 1단계 재료.

## 왜 grok 인가

X 는 밖에서 긁으면 수치가 부정확하고 대부분 막힌다(`X인용_1단계_주제후보.md`
「X 는 웹 검색으로 찾지 않는다」). Premium+ 로 로그인된 grok 세션만 X 안쪽 검색에 닿는다.
봇의 `scripts/grok-x-search.js` 가 이미 그 일을 하고 있어 **그대로 자식 프로세스로 부른다**
— `map_capture` 가 봇의 playwright 캡처를 부르는 것과 같은 이유다. 옮겨 적으면 로그인
세션·타임아웃·출력 형식을 처음부터 다시 배우게 된다.

## 함정

- **한 번에 최대 8분.** 넉넉히 기다린다. 중간에 끊으면 결과가 통째로 버려진다.
- 결과는 **사람이 읽는 글**이라 형식이 흔들린다. 여기서는 URL 을 기준선으로 잡고
  그 앞뒤 줄에서 계정·수치·요약을 줍는다. 못 건진 값은 비워 둔다 — **지어내지 않는다.**
- grok 이 수치를 붙여 오는 일이 있다(2026-09-16 빽다방 회차에서 원문에 없는 「250엔」).
  그래서 **원문 확인은 따로** 한다(`verify_posts`). 후보에 올리기 전 삭제·비공개도 여기서 걸린다.
"""

import asyncio
import os
import io
import json
import logging
import re
import secrets
import shutil
import tempfile
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

NODE = shutil.which("node")
BOT_ROOT = Path.home() / "Desktop" / "클코" / "캐러셀 봇"
HELPER = BOT_ROOT / "scripts" / "grok-x-search.js"

# 헬퍼가 한 번에 8분까지 쓴다. 넘겨받는 쪽은 그보다 넉넉해야 한다.
TIMEOUT_SECONDS = 600

_URL_RE = re.compile(r"https?://(?:x|twitter)\.com/([A-Za-z0-9_]{1,20})/status/(\d+)")
# ⚠ 줄에서 숫자를 아무거나 주우면 **계정 이름의 숫자와 날짜가 조회수로 들어간다**
#   (`@b55fq · 2026-09-15 … 조회 689,746` → 55 와 2026 을 집었다). 라벨을 보고 줍는다.
_VIEWS_RE = re.compile(r"조회\s*(?:수)?\s*[:·]?\s*([\d,]+)")
_LIKES_RE = re.compile(r"좋아요\s*[:·]?\s*([\d,]+)")
_PHOTOS_RE = re.compile(r"사진\s*(\d+)\s*장")
# 댓글 수 — 1단계 지침서의 조건(「50개 이상」, 2026-10-07 — 종전 100개).
_REPLIES_RE = re.compile(r"댓글\s*(?:수)?\s*[:·]?\s*([\d,]+)")
# 「답글1: <일본어> / <한국어> · 좋아요 123」 — 「일본 반응」 장 재료(3-3단계).
# grok 이 번호를 빼거나 기호를 바꿔도 줍도록 느슨하게 본다.
_REPLY_RE = re.compile(r"^[*#>\-\s]*답글\s*\d*\s*[:：]\s*(.+)$")
_REPLY_LIKES_RE = re.compile(r"좋아요\s*[:·]?\s*([\d,]+)\s*$")
# 목록 번호(`**1.**`, `3)` )만 떼고 **본문 숫자는 남긴다** — 「5천원」의 5 가 잘리면 뜻이 바뀐다.
_BULLET_RE = re.compile(r"^[*#>\-\s]*\d+[.)]\s*\**\s*|^[*#>\-\s]+")


def is_available() -> bool:
    return bool(NODE) and HELPER.exists()


# grok 은 **한 번에 하나만** 부른다. 로그인 세션 폴더(GROK_HOME)가 하나뿐이고 그 안에
# auth.json.lock · active_sessions.lock 으로 잠기기 때문이다 — 두 회차가 동시에 부르면
# 하나가 조용히 죽는다. 2026-09-23 실측: 09:00 자동 회차가 4번째 묶음을 도는 중에 사람이
# 09:27 새 회차를 열자 **자동 회차가 후보 0건으로 죽고 일꾼 루프까지 멈췄다**(에러도 안 남았다).
# ⚠ 이 자물쇠는 **이 프로세스 안에서만** 듣는다. 조사원 봇은 다른 프로세스라 여전히
#   부딪힐 수 있다 — 그쪽까지 막으려면 GROK_HOME 을 나눠야 한다.
_GROK_LOCK = asyncio.Lock()


async def search(request: str, max_searches: int | None = None) -> str:
    """grok 헬퍼에 조사 요청을 넘기고 **원문 그대로** 돌려받는다.

    ⚠ 자물쇠 때문에 **앞사람이 끝날 때까지 기다린다.** 묶음 하나가 최대 8분이라 뒤에
      선 회차는 그만큼 늦게 시작한다 — 죽는 것보다는 낫다.
    """
    if not is_available():
        raise RuntimeError(
            f"grok 헬퍼를 찾지 못했습니다 ({HELPER}). 캐러셀 봇 폴더와 node 를 확인하세요."
        )
    if _GROK_LOCK.locked():
        logger.info("[x] grok 이 이미 돌고 있어 차례를 기다립니다")
    async with _GROK_LOCK:
        return await _search_once(request, max_searches)


async def _search_once(request: str, max_searches: int | None = None) -> str:
    # X 검색 횟수 상한은 헬퍼가 GROK_X_MAX_SEARCHES 로 받는다(기본 6). 1단계 후보 찾기는 10(2026-10-01 대표 확정).
    env = {**os.environ, **({"GROK_X_MAX_SEARCHES": str(max_searches)} if max_searches else {})}
    proc = await asyncio.create_subprocess_exec(
        NODE, str(HELPER), request,
        cwd=str(BOT_ROOT),
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        proc.kill()
        raise RuntimeError(f"grok 조사가 {TIMEOUT_SECONDS}초를 넘겼습니다. 주제를 좁혀 다시 부르세요.")
    text = out.decode("utf-8", errors="replace").strip()
    detail = err.decode("utf-8", errors="replace").strip()[-400:]
    # 헬퍼가 0 이 아닌 코드로 끝나면 stdout 에 남은 건 답이 아니다.
    # 특히 시간 초과(2)일 때는 grok 의 진행 상황 내레이션이 남는데, 종전에는
    # returncode 를 보지 않아 그 내레이션을 정상 응답으로 받았다. 그러면 parse 가
    # 게시물 URL 을 0개 집어 "grok 이 한 건도 돌려주지 않았습니다" 502 로 둔갑했다.
    if proc.returncode == 2:
        raise RuntimeError(
            f"grok 이 제한 시간 안에 답을 쓰지 못했습니다. 주제를 좁혀 다시 시도해 주세요. {detail}"
        )
    if proc.returncode != 0:
        raise RuntimeError(f"grok 조사가 실패했습니다 (exit {proc.returncode}). {detail}")
    if not text:
        raise RuntimeError(f"grok 이 빈 응답을 돌려줬습니다. {detail}")
    return text


def _parse_replies(lines: list[str]) -> list[dict[str, Any]]:
    """`답글1: <일본어> / <한국어> · 좋아요 123` 줄들을 항목으로 바꾼다.

    1단계 지침서(2026-09-21) — 「좋아요가 많은 답글 3개를 원문·한국어 번역·좋아요 수와
    함께」. 캐러셀의 「일본 반응」 장 재료다(3-3단계).

    grok 이 형식을 흘릴 때가 있다. 나누는 기호(`/`)가 없으면 **통째로 원문 자리에** 두고
    번역은 비운다 — 뒤에서 채우거나 그 답글을 빼면 된다. 지어내지 않는다.
    """
    out: list[dict[str, Any]] = []
    for line in lines:
        m = _REPLY_RE.match(line)
        if not m:
            continue
        rest = m.group(1).strip().strip("*_` ").strip()
        likes = 0
        lm = _REPLY_LIKES_RE.search(rest)
        if lm:
            likes = int(lm.group(1).replace(",", ""))
            rest = rest[:lm.start()].rstrip(" ·-—").strip()
        jp, sep, ko = rest.partition(" / ")
        if not sep:
            jp, ko = rest, ""
        jp, ko = jp.strip(), ko.strip()
        if not jp:
            continue
        out.append({"text": jp, "korean": ko, "likes": likes})
    return out


# grok 이 게시물마다 덧붙이는 계정·시각·수치 줄(「@계정 · Thu, 01 Oct 2026 10:14:05 GMT · 조회 4979376 · 좋아요 …」).
# 제목·요약이 아니므로 고를 때 건너뛴다. 제목에 「조회수 100만」 같은 말이 들어갈 수 있어 수치 낱말 하나로는
# 판정하지 않는다 — @계정으로 시작하거나, GMT 시각이 있거나, 수치 칸이 둘 이상이면 수치 줄이다.
_META_HANDLE_RE = re.compile(r"^[*\-\s]*@[A-Za-z0-9_]{1,20}\s*[·|•]")
_META_TIME_RE = re.compile(r"\d{1,2}:\d{2}(?::\d{2})?\s*(?:GMT|UTC)")
_META_FIELD_RE = re.compile(r"(?:조회|좋아요|리포스트|댓글|북마크)\s*(?:수)?\s*[:·]?\s*[\d,]+|사진\s*\d+\s*장")


def _is_meta(line: str) -> bool:
    return bool(_META_HANDLE_RE.search(line) or _META_TIME_RE.search(line)
                or len(_META_FIELD_RE.findall(line)) >= 2)


def parse(text: str) -> list[dict[str, Any]]:
    """grok 이 돌려준 글에서 게시물을 줍는다.

    URL 한 줄을 하나의 게시물로 보고, **그 주변 몇 줄**에서 계정·수치·요약을 찾는다.
    형식이 흔들려도 URL 만 제대로면 건진다. 못 찾은 값은 빈 채로 둔다.
    """
    lines = text.splitlines()
    found: list[dict[str, Any]] = []
    seen: set[str] = set()

    for i, line in enumerate(lines):
        m = _URL_RE.search(line)
        if not m:
            continue
        post_id = m.group(2)
        if post_id in seen:
            continue
        seen.add(post_id)

        # 제목은 URL 바로 위, 수치·요약·답글은 아래쪽에 오는 것이 헬퍼의 출력 모양이다.
        # 답글 3줄이 더 붙으므로(2026-09-21 지침) 아래쪽을 넉넉히 본다 — 다음 게시물의
        # URL 을 만나면 거기서 끊어, 남의 답글을 주워 오지 않는다.
        before = [x.strip() for x in lines[max(0, i - 3):i] if x.strip()]
        after = []
        hit_next = False
        for nxt in lines[i + 1:i + 12]:
            if _URL_RE.search(nxt):
                hit_next = True
                break
            if nxt.strip():
                after.append(nxt.strip())
        # 다음 게시물 URL 위의 줄들은 **다음 게시물의 것**(제목, grok 이 덧붙인 계정·수치 줄)이다.
        # 요약 없이 「제목·URL」만 받게 바꾼 뒤(2026-10-05) 이 줄들이 앞 게시물의 요약으로 들어갔다 —
        # 수치 줄을 걷어 내고 그 위의 제목 한 줄까지 뗀다.
        if hit_next:
            while after and _is_meta(after[-1]):
                after.pop()
            if after:
                after.pop()
        title = ""
        # 「제목 | URL」 처럼 한 줄에 같이 오면 그 줄의 글이 제목이다.
        same = re.sub(r"[|｜:：\-–—→>]+\s*$", "", _URL_RE.sub("", line)).strip()
        for cand in [same, *reversed(before)]:
            # ⚠ 앞쪽 번호만 떼면 **뒤에 남은 `**` 가 제목에 딸려 들어간다**
            #   (2026-09-17 첫 회차 — 「서울의 그늘 걷는 권리**」). 양쪽 강조 기호를 다 떼고,
            #   grok 이 붙이는 「요약:」 같은 머리말도 지운다.
            cleaned = _BULLET_RE.sub("", cand).strip()
            cleaned = cleaned.strip("*_` ").strip()
            cleaned = re.sub(r"^(제목|주제|요약)\s*[:：]\s*", "", cleaned).strip()
            # ⚠ 계정·시각·수치 줄은 제목이 아니다(2026-10-07 트립앤라이프 피드백 — 제목이
            #   「@apricot_candy_a · Thu, 01 Oct 2026 … · 조회 4979376 …」 로 나왔다).
            if len(cleaned) >= 4 and not _URL_RE.search(cleaned) and not _is_meta(cleaned):
                title = cleaned
                break

        reply_lines = [x for x in after if _REPLY_RE.match(x)]
        body_lines = [x for x in after if x not in reply_lines]

        stats_line = next((x for x in body_lines if "조회" in x or "좋아요" in x), "")
        num = lambda rx: (lambda m: int(m.group(1).replace(",", "")) if m else 0)(rx.search(stats_line))
        summary = next(
            (x for x in body_lines
             if x is not stats_line and len(x) >= 10 and not _URL_RE.search(x) and not _is_meta(x)),
            "",
        )
        summary = re.sub(r"^(요약|내용)\s*[:：]\s*", "", summary.strip("*_` ").strip()).strip()

        found.append({
            "topic": title,
            "url": f"https://x.com/{m.group(1)}/status/{post_id}",
            "post_id": post_id,
            "account": m.group(1),
            "views": num(_VIEWS_RE),
            "likes": num(_LIKES_RE),
            "photos": num(_PHOTOS_RE),
            # grok 이 센 댓글 수. 원문에서 확인되면 `verify` 가 실제 값으로 덮는다.
            "replies": num(_REPLIES_RE),
            "why": summary,
            "reply_quotes": _parse_replies(reply_lines),
        })
    return found


def _syndication(post_id: str) -> dict[str, Any] | None:
    """X 공개 임베드로 원문을 확인한다. 로그인이 필요 없고 삭제·비공개면 비어서 온다."""
    url = (
        "https://cdn.syndication.twimg.com/tweet-result"
        f"?id={post_id}&lang=ja&token=a"
    )
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126",
    })
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode("utf-8", errors="replace"))
    except Exception:
        return None


def _fx_status(post_id: str) -> dict[str, Any] | None:
    """FxTwitter 공개 API 로 원문을 읽는다 — 본문·작성자·조회수·좋아요·댓글·미디어가 한 번에 온다.

    임베드(`_syndication`)는 조회수를 안 줘서 grok 이 센 값을 그대로 썼다. 이걸 쓰면 grok 에게는
    URL 만 받으면 된다(2026-10-05 — 10건 중 9건 확인, 1건은 삭제된 글이라 404).
    제3자 서비스라 막힐 수 있다 → 못 받으면 `None` 이고, 부르는 쪽이 임베드로 넘어간다.
    """
    req = urllib.request.Request(f"https://api.fxtwitter.com/status/{post_id}",
                                 headers={"User-Agent": "carousel-studio/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            tweet = json.loads(resp.read().decode("utf-8", errors="replace")).get("tweet")
    except Exception:
        return None
    return tweet if isinstance(tweet, dict) and tweet.get("text") is not None else None


def _from_fx(item: dict[str, Any], tweet: dict[str, Any]) -> dict[str, Any]:
    media = (tweet.get("media") or {}).get("all") or []
    photos = [m for m in media if m.get("type") == "photo"]
    # ⚠ 영상·GIF 는 여기서 손대지 않는다 — 표지는 `video_covers` 가 **영상 가운데 프레임**으로
    #   따로 만든다(2026-10-16 트립앤라이프 「중간 프레임에서 좋은 걸 가져와」).
    #   첫 화면을 사진인 척 섞으면 번진 장이 후보에 끼고 `photos` 수도 틀어진다 —
    #   그 수가 본문 장수를 정한다(3-3단계 「사진 1장당 1장 추가」).
    author = tweet.get("author") or {}
    ts = tweet.get("created_timestamp")
    made = (datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
            if ts else "")
    return {
        **item,
        "text": tweet.get("text") or "",
        "account": author.get("screen_name") or item.get("account", ""),
        "author": author.get("name") or "",
        "created_at": made,
        "photos": len(photos),
        "photo_urls": [m.get("url", "") for m in photos],
        "views": int(tweet.get("views") or item.get("views") or 0),
        "likes": int(tweet.get("likes") or item.get("likes") or 0),
        "replies": int(tweet.get("replies") or 0),
    }


async def verify(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """후보마다 원문을 열어 **살아 있는지** 보고 사진 장수·좋아요를 실제 값으로 바꾼다.

    grok 이 붙여 온 수치는 틀릴 때가 있다(2026-09-16 「250엔」 사고). 원문에서 확인되는
    것은 원문 값으로 덮고, 못 연 게시물은 **버린다** — 지침서가 「못 열면 뺀다」고 했다.

    ⚠ **영상·GIF 가 붙은 글도 버리지 않는다**(2026-10-16 트립앤라이프 「영상과 gif 까지
    모두 풀자」). 종전에는 `drop_videos` 로 통째로 뺐는데, 그 탓에 레퍼런스(트립초초)가
    영상에서 프레임을 떠 만든 소재가 우리 후보에는 아예 올라오지 않았다.
    영상 글의 첫 화면은 `_from_fx` 가 `photo_urls` 에 담아 준다.
    """
    async def one(item: dict[str, Any]) -> dict[str, Any] | None:
        tweet = await asyncio.to_thread(_fx_status, item["post_id"])
        if tweet is not None:
            return _from_fx(item, tweet)
        data = await asyncio.to_thread(_syndication, item["post_id"])
        if not data or not data.get("text"):
            logger.info(f"[x] 원문을 못 열어 뺍니다 — {item['url']}")
            return None
        media = data.get("mediaDetails") or []
        photos = [m for m in media if m.get("type") == "photo"]
        user = data.get("user") or {}
        return {
            **item,
            "text": data.get("text", ""),
            "account": user.get("screen_name") or item.get("account", ""),
            "author": user.get("name") or "",
            "created_at": data.get("created_at", ""),
            "photos": len(photos),
            "photo_urls": [m.get("media_url_https", "") for m in photos],
            # 좋아요·댓글은 원문 값이 정확하다. 조회수는 임베드가 안 주므로 grok 값을 남긴다.
            "likes": int(data.get("favorite_count") or item.get("likes") or 0),
            "replies": int(data.get("conversation_count") or 0),
        }

    results = await asyncio.gather(*(one(i) for i in items))
    return [r for r in results if r]


# 지침서 「정렬 — 앞에 둘 글」(2026-09-21)이 정한 기준값. 규칙 문장은 지침서가 원본이고
# 여기는 그 숫자만 둔다.
_REPLY_ENOUGH = 3
_RECENT_HOURS = 48
# 「최근 14일」 묶음과 「명예의전당」(14일~6개월 전) 묶음을 가르는 선
# — 2026-10-16 트립앤라이프 「시간이 지난 소재는 조회수 순으로 나열」.
_HALL_HOURS = 14 * 24


def sort_candidates(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """1단계 지침서 「정렬 — 앞에 둘 글」 그대로 줄 세운다.

      1. **게시 48시간 이내** 글을 앞에
      2. 그다음은 **댓글 수가 많은 순서**
      3. **14일보다 오래된 글(명예의전당)은 맨 뒤에 조회수 순**(2026-10-16 사람 지시)

    원클릭은 앞에 온 것부터 미리 만들어 두므로(`_do_prepare`), 이 순서가 곧 사람이 먼저
    보는 순서다.

    ⚠ 「답글 3개 이상을 앞에」는 **뺐다**(2026-09-23 사람 지시 ①). 그 규칙을 쓰려면 1단계에서
      게시물마다 답글을 열어 봐야 하는데, 그 무게 때문에 grok 이 8분 안에 결론을 못 내고
      중간 설명만 쓰다 잘렸다(09-22 20:59 · 09-23 03:31 — 넷 중 셋). 실제로 쓰는 답글은
      **고른 한 건의 3개뿐**이라 120개를 찾아 117개를 버리던 셈이다. 답글은 이제 주제를
      고른 뒤 `fetch_replies` 가 그 글만 받아 온다.
    """
    now = datetime.now(timezone.utc)

    def age_hours(item: dict[str, Any]) -> float:
        raw = str(item.get("created_at") or "").strip()
        if not raw:
            return 1e9      # 시각을 모르면 「오래된 것」으로 둔다 — 앞으로 올리지 않는다
        try:
            made = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return 1e9
        if made.tzinfo is None:
            made = made.replace(tzinfo=timezone.utc)
        return (now - made).total_seconds() / 3600

    def key(item: dict[str, Any]) -> tuple[int, int]:
        age = age_hours(item)
        if age > _HALL_HOURS:
            # 「명예의전당」 묶음 — 맨 뒤에 **조회수 순**으로 붙인다. 시의성이 없는 글이라
            # 48시간·댓글 잣대가 뜻이 없다. 시각을 모르는 글도 여기로 떨어진다.
            return (2, -int(item.get("views") or 0))
        return (
            0 if age <= _RECENT_HOURS else 1,  # 48시간 이내가 먼저
            -int(item.get("replies") or 0),    # 댓글 많은 순
        )

    return sorted(items, key=key)


# ── 원본 사진 쓰기 ─────────────────────────────────────────────────────────
#
# `X인용_3-2단계_썸네일이미지.md` 2026-09-16 사람 지시 —
#   「표지 배경은 업로드된 사진이 있다면 그걸로 사용하고, 사진이 없는 경우에만 생성」
#   「이미지가 있는데 왜 썸네일, CTA 이미지가 또 생성된거야?」
# 게시물에 사진이 붙어 있으면 **그리지 않는다.** 그 사진을 표지·CTA 배경으로 쓴다.

# 표지 낱장 크기. 지침서가 정한 값이다(1:1 여백판을 깔면 위아래에 흰 띠가 남는다).
COVER_W, COVER_H = 1080, 1350


def _fetch(url: str) -> bytes:
    # 웹 검색 결과에는 **주소에 한글·일본어가 그대로 박힌 것**이 섞여 있다(2026-10-16 —
    # 「…/일본-여행지-추천.jpg」가 ascii 인코딩 오류로 통째로 버려졌다). urllib 은 ascii 만
    # 받으므로 퍼센트 인코딩해 넘긴다 — `%` 를 그대로 둬서 이미 인코딩된 주소는 건드리지 않는다.
    url = urllib.parse.quote(url, safe="%/:=&?~#+!$,;'@()*[]")
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126",
    })
    with urllib.request.urlopen(req, timeout=40) as resp:
        return resp.read()


def _crop_cover(blob: bytes) -> bytes:
    """사진을 **4:5 로 잘라** 표지 배경으로 쓸 수 있게 만든다.

    늘리지 않고 **가운데를 잘라낸다** — 늘리면 얼굴·글자가 뭉개진다.
    세로로 긴 사진은 위쪽을 조금 더 남긴다(사람·간판이 위에 있는 경우가 많다).
    """
    from PIL import Image

    img = Image.open(io.BytesIO(blob))
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGB")
    w, h = img.size
    want = COVER_W / COVER_H

    if w / h > want:                      # 가로가 남는다 — 좌우를 자른다(가운데 기준)
        new_w = int(h * want)
        left = (w - new_w) // 2
        box = (left, 0, left + new_w, h)
    else:                                 # 세로가 남는다 — 위쪽을 조금 더 남기고 자른다
        new_h = int(w / want)
        top = int((h - new_h) * 0.35)
        box = (0, top, w, top + new_h)

    out = img.crop(box).resize((COVER_W, COVER_H), Image.LANCZOS)
    if out.mode == "RGBA":
        out = out.convert("RGB")
    buf = io.BytesIO()
    out.save(buf, format="PNG")
    return buf.getvalue()


async def cover_images(photo_urls: list[str]) -> list[bytes]:
    """게시물 사진들을 표지에 쓸 수 있는 4:5 판으로 만들어 돌려준다.

    여러 장이면 **전부** 돌려준다 — 어느 것을 표지로 쓸지는 사람이 고른다(지침서).
    """
    async def one(url: str) -> bytes | None:
        try:
            # ⚠ FxTwitter 주소는 이미 `?name=orig` 가 붙어 온다 — 그대로 덧붙이면 `…?name=orig?name=large`
            #   가 돼 404 였다(2026-10-05~10-08 X인용 표지가 원본 사진 없이 그림 생성으로 빠졌다).
            blob = await asyncio.to_thread(_fetch, url.split("?", 1)[0] + "?name=large")
            return await asyncio.to_thread(_crop_cover, blob)
        except Exception as e:
            logger.warning(f"[x] 원본 사진을 못 받았습니다 — {url} ({e})")
            return None

    made = await asyncio.gather(*(one(u) for u in photo_urls))
    return [m for m in made if m]


# ── 영상 글의 표지 — 가운데에서 **선명한 프레임**을 뜬다 ───────────────────
#
# 2026-10-16 트립앤라이프 「중간 프레임에서 좋은 걸 가져와」. 영상·GIF 글을 후보에 넣기로
# 하면서(1단계 지침서 같은 날) 생긴 일이다 — 첫 화면(`thumbnail_url`)은 **움직임에 번져
# 뭘 찍은 건지 안 보이는 장면일 때가 많다**(같은 날 온천 영상으로 확인). 레퍼런스(트립초초)도
# 첫 화면이 아니라 영상 가운데 장면을 쓴다.
#
# mp4 주소는 FxTwitter 가 그대로 준다 — X 는 yt-dlp 가 필요 없다(유튜브 소재는 3-2단계대로
# yt-dlp 를 쓴다. 거기는 mp4 주소가 공개되지 않는다).

FFMPEG = shutil.which("ffmpeg")
# 앞뒤는 버린다 — 시작은 움직임에 번지고, 끝은 암전·자막 화면이 잦다.
FRAME_HEAD, FRAME_TAIL = 0.20, 0.85
FRAME_SAMPLES = 8   # 가운데에서 이만큼 뜬 다음
FRAME_PICKS = 3     # 선명한 순으로 이만큼만 남긴다


def _sharpness(blob: bytes) -> float:
    """프레임이 얼마나 또렷한지 — 라플라시안 분산.

    번진 화면은 이웃 화소 차이가 작아 값이 낮다. 2026-10-16 온천 영상 8장 실측에서
    번진 장면 42 · 또렷한 장면 114 로 두 배 넘게 갈렸다.
    """
    import numpy as np
    from PIL import Image

    g = np.asarray(Image.open(io.BytesIO(blob)).convert("L"), dtype=np.float32)
    lap = g[:-2, 1:-1] + g[2:, 1:-1] + g[1:-1, :-2] + g[1:-1, 2:] - 4 * g[1:-1, 1:-1]
    return float(lap.var())


async def _best_frames(video_url: str, duration: float) -> list[bytes]:
    """영상 가운데에서 여러 장을 떠 **선명한 순으로** 몇 장만 돌려준다."""
    if not FFMPEG or duration <= 0:
        return []
    start = duration * FRAME_HEAD
    span = max(duration * (FRAME_TAIL - FRAME_HEAD), 0.5)
    with tempfile.TemporaryDirectory() as tmp:
        proc = await asyncio.create_subprocess_exec(
            FFMPEG, "-nostdin", "-loglevel", "error",
            # ⚠ `-ss` 를 `-i` **앞에** 둬야 빨리 넘어간다. 뒤에 두면 처음부터 다 받는다.
            "-ss", f"{start:.2f}", "-t", f"{span:.2f}", "-i", video_url,
            "-vf", f"fps={FRAME_SAMPLES}/{span:.2f}", "-frames:v", str(FRAME_SAMPLES),
            "-q:v", "2", "-y", str(Path(tmp) / "f_%02d.jpg"),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        try:
            _, err = await asyncio.wait_for(proc.communicate(), timeout=180)
        except asyncio.TimeoutError:
            proc.kill()
            logger.warning(f"[x] 영상이 제한 시간 안에 안 열렸습니다 — {video_url[:90]}")
            return []
        shots = sorted(Path(tmp).glob("f_*.jpg"))
        if not shots:
            logger.warning("[x] 영상 프레임을 한 장도 못 떴습니다 — %s",
                           (err or b"").decode("utf-8", "replace")[:200])
            return []
        scored = [(await asyncio.to_thread(_sharpness, b), b)
                  for b in (p.read_bytes() for p in shots)]
    # ⚠ **선명한 순으로 위에서 자르지 않는다.** 그러면 같은 장면의 이웃 프레임 셋이 뽑혀
    #   후보 3장이 사실상 한 장이 된다(2026-10-16 치이카와 영상 — 셋 다 모래사장이었고
    #   정작 인형은 한 장도 없었다). 영상을 **시간으로 3토막** 내고 토막마다 가장 선명한
    #   한 장을 올린다 — 앞·중간·뒤가 한 장씩이라 주제가 담길 확률이 높아진다.
    picks: list[bytes] = []
    size = max(len(scored) // FRAME_PICKS, 1)
    for n in range(FRAME_PICKS):
        chunk = scored[n * size:(n + 1) * size] if n < FRAME_PICKS - 1 else scored[n * size:]
        if chunk:
            picks.append(max(chunk, key=lambda row: row[0])[1])
    return picks


# ── 뜬 프레임 중 **주제가 담긴 장면**을 고른다 (2026-10-16 트립앤라이프 지시) ──
#
# 선명도만 보면 「선명하지만 쓸 수 없는 표지」가 올라온다 — 치이카와 글(조회 360만)은
# 붙은 영상이 2.4초 모래사장뿐이라 석 장이 다 모래였다. 봇은 그 장면에 **주제가 담겼는지**
# 는 못 본다. 그래서 글 내용과 프레임을 함께 gemini vision 에 주고 고르게 한다.
#
# ⚠ **후보를 버리지는 않는다.** 맞는 장면을 앞으로 올릴 뿐이다 — 고르는 것은 사람이고
#   (3-2단계 지침서), 한 장도 안 맞는다고 영상 글의 원본 장면을 통째로 빼면 그 글은
#   다시 그림 생성으로 돌아간다. 하나도 안 맞으면 로그에 남긴다.
# ⚠ **이 PC 에서는 gemini 쪽이 막혀 있다.** `GEMINI_API_KEY` 에 IP 제한이 걸려 있어 집 IP 로
#   부르면 403 이다(2026-10-16 확인). 그런데 원클릭 스튜디오는 이 PC 의 :8000 에서 돈다 —
#   그래서 gemini 가 막히면 **로그인된 codex 세션**(`-i` 로 그림을 받는다. 훅 창고가 표지
#   글자를 읽을 때 쓰는 길과 같다)으로 같은 것을 묻는다. 서버에서는 gemini 가 열려 더 빠르다.
# ⚠ 둘 다 실패하면 **선명도 순 그대로** 간다 — 이 단계는 더 나은 순서일 뿐 필수가 아니다.

_FRAME_PICK_HEAD = """X(트위터) 글에 붙은 영상에서 뜬 장면들이다. 이 글의 **표지**로 쓸 수 있는지 본다.

글 내용:
"""
_FRAME_PICK_TAIL = """

FRAME 한 장씩 보고 답해라.
- `what` — 그 장면에 **실제로 보이는 것**을 짧게 적는다. 짐작해서 보태지 마라.
- `shows` — 글이 말하는 대상(사람·사물·캐릭터·음식·장소·사건)이 그 장면에 보이면 true.
  배경·질감·바닥·벽·모래·하늘만 찍혔거나, 암전·전환·자막뿐이면 **false** 다. 선명한 것과는 상관없다.
  표지로 내보냈을 때 글을 모르는 사람이 무엇을 찍은 건지 알 수 없다면 false 다.
- 전부 false 여도 된다. 한 장은 true 여야 한다고 생각하지 마라.
"""
_FRAME_PICK_MODEL = "codex-luna"   # 훅 창고가 표지 글자를 읽을 때와 같은 길
_FRAME_PICK_SCHEMA = {
    "type": "object",
    "properties": {"frames": {"type": "array", "items": {
        "type": "object",
        "properties": {"i": {"type": "integer"}, "shows": {"type": "boolean"},
                       "what": {"type": "string"}},
        "required": ["i", "shows", "what"],
        "additionalProperties": False,
    }}},
    "required": ["frames"],
    "additionalProperties": False,
}


async def _ask_frames(paths: list[str], prompt: str) -> dict:
    """프레임을 **눈으로 보고** 고르게 한다 — gemini vision 먼저, 막히면 codex 세션."""
    from app.agents.llm_client import MODELS, _call_codex_cli, gemini_vision

    try:
        raw = await gemini_vision(paths, prompt, max_tokens=800,
                                  image_labels=[f"FRAME {i}" for i in range(len(paths))])
        if isinstance(raw, dict) and raw.get("frames"):
            return raw
        logger.warning("[x] gemini 답이 모양에 안 맞습니다 — codex 로 다시 묻습니다")
    except Exception as e:
        logger.info(f"[x] gemini vision 이 막혀 codex 로 묻습니다 — {str(e)[:120]}")
    # codex 는 `-i` 로 준 순서대로 그림을 본다 — 번호를 프롬프트에 못박아 둔다.
    out = await _call_codex_cli(prompt + "\n\n붙인 그림은 FRAME 0 번부터 차례대로다.",
                                model=MODELS[_FRAME_PICK_MODEL]["cli_model"],
                                json_schema=_FRAME_PICK_SCHEMA, images=paths, timeout=180)
    return json.loads(out)


async def _judge(frames: list[bytes], text: str) -> list[int]:
    """장면들을 **눈으로 보고** 글의 주제가 보이는 장 번호만 돌려준다(보이는 순서 그대로).

    못 물어봤거나 한 장도 안 맞으면 빈 목록이다 — 부르는 쪽이 「그대로 둘지 / 버릴지」를 정한다.
    """
    if not frames or not (text or "").strip():
        return []
    try:
        with tempfile.TemporaryDirectory() as tmp:
            paths = []
            for i, blob in enumerate(frames):
                shot = Path(tmp) / f"f{i}.png"
                shot.write_bytes(blob)
                paths.append(str(shot))
            raw = await _ask_frames(paths, _FRAME_PICK_HEAD + text.strip()[:600] + _FRAME_PICK_TAIL)
    except Exception as e:
        logger.warning(f"[x] 장면을 눈으로 못 봤습니다 — {e}")
        return []

    # ⚠ **고르게 하지 않고 한 장씩 판정하게 한다.** 「맞는 것 번호를 줘」로 물으면 모델이
    #   하나도 안 맞아도 빈손으로 오기를 꺼려 전부 집어 온다(2026-10-16 온천 영상 —
    #   「온천이 안 보인다」고 적어 놓고 셋 다 골랐다). true/false 는 그렇게 흔들리지 않는다.
    picks: list[int] = []
    for row in ((raw or {}).get("frames") or []):
        if not isinstance(row, dict):
            continue
        n = row.get("i")
        if not (isinstance(n, int) and not isinstance(n, bool) and 0 <= n < len(frames)):
            continue
        if n in picks:
            continue
        if row.get("shows") is True:
            picks.append(n)
        logger.info(f"[x]  {n}번 — {'주제 보임' if row.get('shows') else '주제 없음'} · "
                    f"{str(row.get('what') or '').strip()[:60]}")
    return picks


async def video_covers(post_id: str) -> tuple[list[bytes], bool]:
    """영상·GIF 가 붙은 글의 표지 후보 — 가운데에서 뜬 프레임을 4:5 로 돌려준다.

    돌려주는 것은 **(프레임들, 그 중 주제가 담긴 장이 있었는지)** 다. 두 번째 값이 거짓이면
    그 영상에는 글의 주제가 안 찍혔다는 뜻이라, 부르는 쪽이 웹 검색(`web_covers`)으로 넘어간다.

    사진이 없는 영상 글도 이걸로 원본 장면을 쓴다. 프레임을 못 뜨면 **첫 화면으로 물러선다**
    — 번져 있어도 생성 그림보다는 그 글의 장면이다.
    """
    tweet = await asyncio.to_thread(_fx_status, post_id)
    clips = [m for m in ((tweet or {}).get("media") or {}).get("all") or []
             if m.get("type") in ("video", "gif")]
    if not clips:
        return [], False

    made: list[bytes] = []
    for clip in clips:
        url = str(clip.get("url") or "")
        frames = await _best_frames(url, float(clip.get("duration") or 0)) if url else []
        if not frames:
            thumb = str(clip.get("thumbnail_url") or "")
            logger.info(f"[x] 프레임을 못 떠 첫 화면으로 갑니다 — {clip.get('type')} {post_id}")
            made.extend(await cover_images([thumb]) if thumb else [])
            continue
        for blob in frames:
            try:
                made.append(await asyncio.to_thread(_crop_cover, blob))
            except Exception as e:
                logger.warning(f"[x] 프레임을 4:5 로 못 잘랐습니다 — {e}")
    # 선명한 것 말고 **주제가 담긴 것**이 앞에 오게 다시 세운다(위 `_judge`).
    # ⚠ **프레임은 버리지 않는다.** 석 장이 전부라 버리면 그 글이 표지를 잃는다 — 순서만 바꾸고,
    #   한 장도 안 맞았다는 사실(`fits`)을 함께 올려 보낸다.
    picks = await _judge(made, str((tweet or {}).get("text") or ""))
    if picks:
        logger.info(f"[x] 주제에 맞는 프레임 {picks} 를 앞으로 올립니다")
        made = [made[n] for n in picks] + [b for i, b in enumerate(made) if i not in picks]
    else:
        logger.warning("[x] 주제가 담긴 프레임이 없습니다 — 선명도 순 그대로 둡니다")
    # 영상이 여럿이어도 표지 후보가 한없이 늘지는 않게 한다 — 사람이 고를 수 있는 양만.
    return made[:FRAME_PICKS * 2], bool(picks)


# ── 영상에 주제가 안 찍혔을 때 — **웹에서 찾아 온다** (2026-10-16 트립앤라이프 지시) ──
#
# 「웬만하면 네가 이미지를 찾고 정 안 될 때만 내가 찾는다」. 프레임 석 장이 다 주제를 못 담으면
# (치이카와 글 — 붙은 영상이 2.4초 모래사장뿐이었다) 그 글은 표지가 빈다. 그때 **주제로 웹
# 이미지를 찾아** 후보에 올린다. 여기서도 고르는 것은 눈이다 — 받아 온 장을 `_judge` 로 보고
# **주제가 보이는 것만** 남긴다(웹은 넉넉히 받으니 안 맞는 장은 버린다).
#
# ⚠ **구글이 아니다.** 구글은 검색 키가 없고 긁으면 막힌다. `image_search` 의 v2 묶음
#   (**bing → 네이버 → 위키미디어**)이 같은 웹 이미지를 긁어 온다 — 결과가 구글과 똑같지는 않다.
# ⚠ 저작권은 보지 않는다(2026-10-16 사람 지시 「저작권은 생각 안 해도 돼」).
# ⚠ 한 장도 못 건지면 **사람이 직접 넣는다**(같은 날 지시). 그래서 여기서 실패해도 예외를
#   올리지 않고 빈 목록을 준다 — 생성 그림 후보는 그대로 따로 만들어진다.

WEB_TRIES = 6      # 검색에서 받아 볼 장수. 눈으로 보는 값이라 많이 받을수록 느리다.
WEB_KEEP = 3       # 후보로 올릴 장수 — 프레임과 같은 수
NAMU_TRIES = 2     # 나무위키에 따로 떼어 주는 자리. 눈으로 보는 값이라 많이 받을수록 느리다.

# ⚠ **주제 문장을 그대로 검색창에 넣지 않는다.** 2026-10-16 실측 — 「300엔짜리 편의점
#   도시락이 초라해졌다」로 물으니 bing 이 블로그 썸네일 1장만 줬고 그마저 주제와 무관했다
#   (「일본 편의점 신상 디저트 화제」는 도쿄타워·성 사진 3장 → 눈 판정에서 0장 통과).
#   검색 엔진은 긴 말을 흘려 「일본 여행」 류 일반 사진으로 돌려준다. 그래서 **낱말 두세 개로
#   줄인 검색어**를 만들어 쓰고, 일본 소재는 **일본어 검색어도 함께** 쓴다 — 원래 사진이
#   올라와 있는 쪽은 일본 웹이다.
_WORDS_SCHEMA = {
    "type": "object",
    "properties": {"queries": {"type": "array", "items": {"type": "string"}}},
    "required": ["queries"],
    "additionalProperties": False,
}


async def _search_words(topic: str) -> list[str]:
    """주제 한 줄을 **이미지 검색용 낱말 묶음 두 개**(한국어·일본어)로 줄인다.

    못 물어봤으면 빈 목록이다 — 부르는 쪽이 주제 문장 그대로 검색한다.
    """
    from app.agents.llm_client import llm_json

    prompt = "\n".join([
        "아래 주제의 **사진을 찾기 위한 이미지 검색어**를 2개 만들어라.",
        f"주제: {topic.strip()[:200]}",
        "",
        "- 1번은 한국어, 2번은 일본어로 쓴다(일본 소재의 원본 사진은 일본 웹에 있다).",
        "- 문장이 아니라 **낱말 2~4개**다. 조사·서술어·「화제」·「충격」 같은 말은 뺀다.",
        "  예) 「300엔짜리 편의점 도시락이 초라해졌다」 → 「편의점 도시락」 · 「コンビニ弁当」",
        "- 사진으로 찍힐 **대상(물건·장소·음식)**만 남긴다. 감정·평가는 사진에 안 찍힌다.",
        "",
        '{"queries": ["한국어 검색어", "일본어 검색어"]} 만 돌려준다.',
    ])
    try:
        data = await llm_json(model="codex-sol", messages=[{"role": "user", "content": prompt}],
                              json_schema=_WORDS_SCHEMA, max_tokens=300)
    except Exception as e:
        logger.warning(f"[x] 검색어를 못 줄였습니다 — {topic} ({e})")
        return []
    out = [str(q).strip() for q in ((data or {}).get("queries") or []) if str(q).strip()]
    if out:
        logger.info(f"[x] 웹 검색어 — {' · '.join(out)}")
    return out[:2]


async def _web_hits(query: str) -> list:
    """v2 묶음(bing → 네이버 → 위키미디어)으로 한 번 찾는다. 빈손이면 **한 번만** 다시 묻는다.

    bing 은 같은 말로 물어도 빈손일 때가 있다(2026-10-16 실측 — 「東京タワー」가 첫 번에 0건,
    다시 묻자 3건).
    """
    from app.services.image_search import search_all

    for _ in range(2):
        try:
            hits = await search_all(query, limit=WEB_TRIES, profile="v2")
        except Exception as e:
            logger.warning(f"[x] 웹 이미지 검색이 실패했습니다 — {query} ({e})")
            return []
        if hits:
            return hits
    return []


async def web_covers(query: str, want: int = WEB_KEEP) -> list[bytes]:
    """주제로 웹 이미지를 찾아 **주제가 보이는 것만** 4:5 로 잘라 돌려준다."""
    if not (query or "").strip():
        return []
    # 검색어마다 **반씩 받는다.** 첫 검색어로 여섯 장을 채우면 일본어 검색어가 아예 안 돌아
    # 간다 — 2026-10-16 실측에서 「일본 편의점 도시락」은 bing 이 일반 여행 사진만 줬고
    # 「コンビニ 300円 弁当」은 돌지도 않았다. 눈 판정이 어느 쪽이든 맞는 것만 남긴다.
    queries = await _search_words(query) or [query]
    per = max(1, WEB_TRIES // len(queries))
    hits: list = []
    for q in queries:
        hits += (await _web_hits(q))[:per]
    # 나무위키는 **자리를 따로 떼어 둔다**(2026-10-16 트립앤라이프 「나무위키도 붙여줘」).
    # v2 체인 꼬리에 달려 있지만 bing 이 여섯 자리를 다 채워 실제로는 돌지 않는다 —
    # 캐릭터·IP·제품 소재에서는 문서 사진이 bing 의 굿즈 썸네일보다 주제를 담는다
    # (치이카와 → 문서 이름 「먼작귀」의 단체 그림·치이카와샵 사진). 한국어 위키라 **한국어
    # 검색어로만** 묻는다.
    from app.services.image_search import PROVIDERS

    hits += await PROVIDERS["namu"].safe_search(queries[0], NAMU_TRIES)
    if not hits:
        logger.warning(f"[x] 웹 검색에 걸린 사진이 없습니다 — {query}")
        return []

    blobs: list[bytes] = []
    for hit in hits[:WEB_TRIES + NAMU_TRIES]:
        url = str(getattr(hit, "source_url", "") or getattr(hit, "thumbnail_url", ""))
        if not url:
            continue
        try:
            raw = await asyncio.to_thread(_fetch, url)
            blobs.append(await asyncio.to_thread(_crop_cover, raw))
        except Exception as e:
            logger.info(f"[x] 검색 사진을 못 받았습니다 — {url[:80]} ({e})")
    if not blobs:
        logger.warning(f"[x] 웹에서 받아온 사진이 없습니다 — {query}")
        return []

    picks = await _judge(blobs, query)
    logger.info(f"[x] 웹에서 {len(blobs)}장을 받아 {len(picks)}장이 주제에 맞았습니다 — {query}")
    return [blobs[n] for n in picks][:want]


# ── 본문 칸에 넣을 X 화면 캡처 ─────────────────────────────────────────────
#
# `X인용_3-3단계_본문.md` — 「x에서 캡쳐한 이미지라는게 보이도록 UI 그대로 살려서 넣어줘」.
# 직접 그린 카드를 쓰지 않는다. 임베드 화면의 **일본어 글만 한국어로 갈아 끼우고** 통째로 찍는다.
# 찍는 절차는 봇의 `scripts/x-capture.js` 에 있다(playwright 가 거기 깔려 있다).

CAPTURE_HELPER = BOT_ROOT / "scripts" / "x-capture.js"
# 「일본 반응」 장 — 답글도 **임베드를 그대로 찍는다**(3-3 지침서 2026-10-13 교체).
# 손으로 그리던 봇의 `scripts/x-replies.js` 는 더 쓰지 않는다 — 좋아요·게시 시각이 실제로
# 찍힌 화면을 쓴다. 답글에도 공개 임베드 주소가 있다(2026-10-13 확인).
REPLY_HELPER = Path(__file__).resolve().parents[2] / "scripts" / "x-reply-card.mjs"
# 그 헬퍼는 이 레포 안에 있어 playwright 를 스스로 못 찾는다 — 봇 폴더의 것을 알려 준다.
PW_ENTRY = BOT_ROOT / "node_modules" / "playwright" / "index.js"

# 본문 이미지 칸 비율. 문서가 정한 값이다 — 안 맞추면 칸이 꽉 채우며 위아래를 잘라 먹는다.
BODY_W, BODY_H = 739, 825


def capture_available() -> bool:
    return bool(NODE) and CAPTURE_HELPER.exists()


async def capture_card(post_id: str, korean: str = "") -> bytes:
    """게시물 카드를 찍어 **본문 칸 비율(739:825)로 여백을 붙여** 돌려준다.

    `korean` 을 주면 본문 글자를 그것으로 갈아 끼운다(원문이 한국어면 비워 둔다).
    """
    if not capture_available():
        raise RuntimeError(f"캡처 헬퍼를 찾지 못했습니다 ({CAPTURE_HELPER}).")

    payload = json.dumps({"id": post_id, "korean": korean}, ensure_ascii=False)
    proc = await asyncio.create_subprocess_exec(
        NODE, str(CAPTURE_HELPER),
        cwd=str(BOT_ROOT),
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        out, err = await asyncio.wait_for(
            proc.communicate(payload.encode("utf-8")), timeout=240)
    except asyncio.TimeoutError:
        proc.kill()
        raise RuntimeError("X 캡처가 240초를 넘겼습니다.")

    path = out.decode("utf-8", errors="replace").strip().splitlines()[-1:] or [""]
    shot = Path(path[0]) if path[0] else None
    if not shot or not shot.exists():
        detail = err.decode("utf-8", errors="replace").strip()[-400:]
        raise RuntimeError(f"X 캡처에 실패했습니다. {detail}")
    return await asyncio.to_thread(_finish_body, shot.read_bytes())


# 「일본 반응」 장을 만들 최소 답글 수. 규칙 문장은 3-3 지침서가 원본이다
# (2026-10-13 교체 — 「답글 1개 = 1장, 2~3장. 1개뿐이면 1장만, 쓸 만한 게 없으면 안 만든다」).
# 2026-09-21~10-12 은 3개를 한 장에 모아 그렸고 그래서 최소도 3이었다.
REPLIES_NEEDED = 1

# 반응 장은 **최대 3장**, 본문 전체는 **5장 안쪽**이다(3-3 「장수」 · 2026-10-13).
# 반응을 3장 쓰면 글·사진 장은 2장까지 — 줄이는 쪽은 글·사진 장이다.
REPLY_SLIDES_MAX = 3
BODY_SLIDES_MAX = 5

# **받아 둘** 답글 수. 쓰는 것은 2~3개뿐인데 15개를 받는 이유는 사람 지시다
# (2026-10-13 — 「지금 캡처하는 건 1장밖에 없어 … 그것보다 더 선택지가 많아야 해」).
_REPLY_ASK = 15

# 좋아요 바닥. 이게 없으면 **조회 9 에 좋아요 1** 짜리가 비율 1위가 된다(2026-10-13 실측).
_REPLY_LIKE_FLOOR = 5


_FX_CONVERSATION = "https://api.fxtwitter.com/2/conversation/"


def _fx_replies_sync(post_id: str, pages: int = 3) -> tuple[list[dict[str, Any]], int | None]:
    """FxTwitter 공개 API 로 **로그인 없이** 답글을 받는다(2026-10-01 대표 지시 — grok 대신).

    grok 으로 답글 한 건을 받으면 2만~50만 토큰이 들었다. 이 경로는 토큰이 0 이다.
    원글 작성자 자신의 답글·원글이 아닌 글에 단 답글은 뺀다. 번역은 비워 두면
    `studio_worker` 가 `translate_post` 로 채운다.
    ⚠ 다 받은 뒤에도 cursor 가 남고 그 다음 쪽은 404 다 → 둘째 쪽부터의 실패는 끝으로 본다.

    **답글 id 를 함께 들고 온다**(2026-10-13) — 캡처가 그 id 로 임베드를 연다. 조회·답글·
    재게시도 같이 받는다. 임베드는 좋아요만 보여 주므로 나머지 수치는 여기서 온 값을 그린다.
    """
    seen: dict[str, dict[str, Any]] = {}
    cursor, author, total = "", "", None
    for page in range(pages):
        url = _FX_CONVERSATION + post_id + (f"?cursor={urllib.parse.quote(cursor)}" if cursor else "")
        req = urllib.request.Request(url, headers={"User-Agent": "carousel-studio/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=20) as res:
                data = json.loads(res.read().decode("utf-8"))
        except Exception:
            if page > 0:
                break
            raise
        if page == 0:
            author = str(((data.get("status") or {}).get("author") or {}).get("screen_name") or "").lower()
            total = (data.get("status") or {}).get("replies")
        for r in data.get("replies") or []:
            handle = str((r.get("author") or {}).get("screen_name") or "")
            if not handle or handle.lower() == author:
                continue
            if r.get("replying_to_status") and str(r.get("replying_to_status")) != post_id:
                continue
            text = re.sub(r"^(@\w+\s+)+", "", str(r.get("text") or ""))
            # 캡처 카드는 한 줄로 그린다 — 줄바꿈을 살리면 글상자가 들쭉날쭉해진다.
            text = " ".join(text.split())
            if text:
                seen[str(r.get("id"))] = {
                    "id": str(r.get("id")),      # 캡처가 이 id 로 임베드를 연다
                    "text": text, "korean": "",
                    "likes": int(r.get("likes") or 0),
                    "views": int(r.get("views") or 0),
                    "replies": int(r.get("replies") or 0),
                    "reposts": int(r.get("reposts") or 0),
                    "at": str(r.get("created_at") or ""),
                }
        cursor = str((data.get("cursor") or {}).get("bottom") or "")
        if not cursor or not data.get("replies"):
            break
    return _rank_replies(list(seen.values())), total


def _rank_replies(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """고르는 순서 (3-3 「고르는 법」 · 2026-10-13 사람 지시 — 좋아요만 보지 않는다).

    좋아요 5 이상만 깐 뒤 **좋아요÷조회수**가 높은 것부터 본다. 조회수만 큰 답글은
    원글 덕에 노출된 것일 수 있다. 비율이 같으면 **말이 오간 답글**(답글·재게시)을 앞세운다.
    바닥을 넘는 것이 하나도 없으면 바닥을 접고 있는 것으로 줄을 세운다.

    ⚠ 「결이 겹치지 않게」·「한국인이 못 알아듣는 답글은 뺀다」는 이 함수가 못 하는 판단이다.
      사람이 대화로 만들 때는 그 둘까지 보고 고른다(원클릭은 여기까지다).
    """
    strong = [r for r in rows if int(r.get("likes") or 0) >= _REPLY_LIKE_FLOOR]
    pool = strong or rows
    return sorted(pool, key=lambda r: (
        -(int(r.get("likes") or 0) / max(int(r.get("views") or 0), 1)),
        -(int(r.get("replies") or 0) + int(r.get("reposts") or 0)),
    ))


async def fetch_replies(url: str, post_id: str) -> list[dict[str, Any]]:
    """**고른 글 하나**의 답글을 FxTwitter 로 받아, 고를 순서대로 돌려준다.

    1단계에서 게시물마다 답글까지 찾게 했더니 그 무게로 grok 이 제한 시간 안에 결론을
    못 냈다(2026-09-23 사람 지시 ① — 1단계에서 빼고 고른 뒤에 받는다).

    ⚠ **grok 경로는 없앴다**(2026-10-13). grok 은 원문과 좋아요만 주고 **답글 id 를 주지
      않는다** — id 가 없으면 임베드를 못 열어 캡처를 못 띄운다(3-3 「받아 올 것」).
      FxTwitter 가 실패하면 반응 장을 **안 만든다**.

    못 받아도 예외를 내지 않는다 — 빈 목록이면 「일본 반응」 장을 안 만들 뿐이다.
    """
    m = _URL_RE.search(url or "")
    pid = str(post_id or (m.group(2) if m else ""))
    if not pid:
        return []
    try:
        got, total = await asyncio.to_thread(_fx_replies_sync, pid)
    except Exception as e:
        logger.warning(f"[x] FxTwitter 답글 실패 — 반응 장은 건너뜁니다: {str(e)[:150]}")
        return []
    logger.info(f"[x] 답글 {len(got)}개 받음(FxTwitter · 전체 {total}) — {url or pid}")
    return got[:_REPLY_ASK]


def replies_ready(quotes: list[dict[str, Any]] | None) -> bool:
    """「일본 반응」 장을 만들 만큼 **찍을 수 있는 답글**이 있는지.

    글만 있고 **id 가 없는 답글은 세지 않는다** — 캡처가 id 로 임베드를 연다(2026-10-13).
    """
    return len([q for q in (quotes or [])
                if (q or {}).get("id") and ((q or {}).get("korean") or (q or {}).get("text"))])         >= REPLIES_NEEDED


async def capture_reply(quote: dict[str, Any]) -> bytes:
    """답글 **한 개**를 X 임베드 화면 그대로 찍어 본문 칸 비율(739:825)로 돌려준다.

    3-3 「캡처 — 답글도 X 임베드로 찍는다」(2026-10-13). 위에 딸려 나오는 원글 카드는
    헬퍼가 잘라내고, 쓴 사람 한 줄도 헬퍼가 브라우저에서 블러한다 — 여기서는 여백만 붙인다
    (글 캡처의 `_finish_body` 와 달리 PIL 블러를 다시 넣지 않는다. 두 번 흐려질 자리다).
    """
    if not NODE or not REPLY_HELPER.exists():
        raise RuntimeError(f"답글 캡처 헬퍼를 찾지 못했습니다 ({REPLY_HELPER}).")

    rid = str(quote.get("id") or "")
    if not rid:
        raise RuntimeError("답글 id 가 없어 임베드를 열 수 없습니다.")

    out = Path(tempfile.gettempdir()) / f"xreply-{rid}-{secrets.token_hex(4)}.png"
    payload = json.dumps({
        "id": rid,
        "korean": str(quote.get("korean") or ""),
        "views": int(quote.get("views") or 0),
        "replies": int(quote.get("replies") or 0),
        "reposts": int(quote.get("reposts") or 0),
        "likes": int(quote.get("likes") or 0),
        "out": str(out),
    }, ensure_ascii=False)
    proc = await asyncio.create_subprocess_exec(
        NODE, str(REPLY_HELPER),
        cwd=str(REPLY_HELPER.parent),
        env={**os.environ, "PW_ENTRY": str(PW_ENTRY)},
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        got, err = await asyncio.wait_for(
            proc.communicate(payload.encode("utf-8")), timeout=240)
    except asyncio.TimeoutError:
        proc.kill()
        raise RuntimeError("답글 캡처가 240초를 넘겼습니다.")

    detail = err.decode("utf-8", errors="replace").strip()[-400:]
    if not out.exists():
        raise RuntimeError(f"답글 캡처에 실패했습니다. {detail}")
    if detail:
        logger.warning(f"[x] 답글 캡처 경고({rid}): {detail}")
    try:
        return await asyncio.to_thread(_pad_body, out.read_bytes())
    finally:
        out.unlink(missing_ok=True)


def _pad_body(blob: bytes) -> bytes:
    """좌우(또는 위아래)에 **흰 여백**을 붙여 739:825 로 맞춘다.

    잘라내지 않고 **붙인다** — 카드를 자르면 계정 줄이나 좋아요 줄이 날아가고,
    그러면 「X 캡처로 보이게」라는 규칙이 깨진다.
    """
    from PIL import Image

    img = Image.open(io.BytesIO(blob))
    if img.mode != "RGB":
        img = img.convert("RGB")
    w, h = img.size
    want = BODY_W / BODY_H

    if w / h > want:            # 가로가 넓다 — 위아래에 여백
        new_h = int(w / want)
        canvas = Image.new("RGB", (w, new_h), "white")
        canvas.paste(img, (0, (new_h - h) // 2))
    else:                        # 세로가 길다 — 좌우에 여백
        new_w = int(h * want)
        canvas = Image.new("RGB", (new_w, h), "white")
        canvas.paste(img, ((new_w - w) // 2, 0))

    buf = io.BytesIO()
    canvas.save(buf, format="PNG")
    return buf.getvalue()


# 게시자 한 줄을 흐리는 상자. 문서가 적어 둔 값이다 — **1644px 폭 기준**이라
# 캡처 폭이 다르면 비율로 환산한다(deviceScaleFactor 가 바뀌면 폭도 바뀐다).
# 게시자 한 줄을 덮는 상자(폭 1644 캡처 기준). 오른쪽 끝은 **X 로고 앞까지** 간다 —
# 로고는 살려야 한다(지침서). 800 이던 시절에는 이름이 긴 계정의 뒷부분·인증 배지·
# 「팔로우하기」가 밖으로 비어져 나왔다(2026-09-18 캐러셀 567 에서 확인).
_BLUR_BOX_AT_1644 = (40, 18, 1400, 188)
_BLUR_RADIUS = 16


def _blur_author(img):
    """프로필 사진·계정 이름·인증 배지·아이디·팔로우하기 한 줄만 흐린다.

    `X인용_3-3단계_본문.md` 2026-09-16 사람 지시 — 「게시자가 누군지 애매하게」.
    모자이크가 아니라 **블러**로 정해졌다(모자이크는 가린 티가 도드라진다).

    ⚠ X 로고·게시 시각·게시일·좋아요·답글하기 줄은 **그대로 둔다.**
      「X 에서 캡쳐한 것」으로 보이게 하는 것이 여전히 목적이다. 잘라 내는 것도 금지다.
    """
    from PIL import ImageFilter

    scale = img.size[0] / 1644
    box = tuple(int(v * scale) for v in _BLUR_BOX_AT_1644)
    # 상자가 이미지 밖으로 나가면 붙여 넣기가 실패한다 — 캡처가 짧을 때를 막는다.
    box = (box[0], box[1], min(box[2], img.size[0]), min(box[3], img.size[1]))
    if box[2] <= box[0] or box[3] <= box[1]:
        logger.warning("[x] 블러 상자가 캡처 밖이라 건너뜁니다.")
        return img
    patch = img.crop(box).filter(ImageFilter.GaussianBlur(int(_BLUR_RADIUS * scale) or 1))
    img.paste(patch, box)
    return img


def _finish_body(blob: bytes) -> bytes:
    """캡처를 본문 칸에 넣을 수 있게 마무리한다 — 게시자 블러 → 739:825 여백."""
    from PIL import Image

    img = Image.open(io.BytesIO(blob))
    if img.mode != "RGB":
        img = img.convert("RGB")
    img = _blur_author(img)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return _pad_body(buf.getvalue())
