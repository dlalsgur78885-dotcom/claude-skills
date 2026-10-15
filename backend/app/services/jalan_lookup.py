"""쟈란(じゃらん)에서 숙소의 **2인 최저가**와 **게재 등급(N성급)**을 읽는다 — 일본숙소 축 전용.

## 왜 필요한가

일본숙소 지침서가 요금과 성급을 **확인한 값으로만** 쓰라고 한다(`일본숙소_2단계_주제선택.md`
「요금은 반드시 조회한다」·「성급(N성급)도 함께 확인한다」). `place_lookup` 은 둘 다 주지 않는다.
봇 시절에는 회차 폴더에 스크립트를 두고 손으로 돌렸다(`.work/sukso46/jprice3.py` ·
`.work/sukso43/stars.py`) — 여기는 그 길을 그대로 함수로 옮긴 것이다.

## 길

  ① 일본어 상호 — 구글 지도에서 같은 place_id 를 `lang="ja"` 로 다시 찾는다(`place_lookup.local_name`).
  ② yad 번호 — 쟈란 키워드 검색(cp932)에서 이름·주소가 맞는 숙소 하나를 고른다.
     **맞는 것이 없으면 None 이다.** 엉뚱한 지점의 요금을 붙이느니 「확인 못 함」이 낫다.
  ③ 최저가 — 그 숙소의 플랜 페이지를 **네 날짜 이상**(비수기 평일 포함) 열어 2인 1실 최저가.
     한 날짜만 보면 비싼 날이 걸린다(2단계 지침서 2026-10-08 — 같은 호텔이 두 배까지 벌어졌다).
  ④ 성급 — 숙소 페이지에 **「N つ星」가 글자로 적혀 있을 때만** 읽는다. 없으면 None 이다.
     ⚠ 검색 결과의 별(`c-starRating`)은 **후기 평점**이지 등급이 아니다 — 읽지 않는다.
       아고다는 필터 이름표가 섞여 믿을 수 없다(2026-10 회차 기록). **절대 짐작하지 않는다.**

## 실패하면

전부 **부드럽게 넘어간다** — 로그를 남기고 None. 요금·성급이 없다고 본문을 못 짓지는 않는다
(지침서가 「확인 못 함」일 때의 꼴을 정해 두었다). 같은 숙소는 몇 시간 안에는 다시 열지 않는다(`_CACHE`).
"""

from __future__ import annotations

import asyncio
import difflib
import logging
import re
import time
import unicodedata
from datetime import date, timedelta
from typing import Any
from urllib.parse import quote

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# 회차 스크립트와 같은 머리말 — 이것 없이 부르면 쟈란이 빈 페이지를 줄 때가 있다.
UA = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "Chrome/129.0 Safari/537.36",
    "Accept-Language": "ja",
}
SEARCH_URL = "https://www.jalan.net/uw/uwp2011/uww2011init.do"
# 검색 조건 — 2026-10 회차에 손으로 맞춰 본 값 그대로다(숙소 전체 · 날짜 미정 · 인기순).
SEARCH_PARAMS = {
    "distCd": "06", "rootCd": "7701", "screenId": "UWW2011",
    "dateUndecided": "1", "actionId": "G", "activeSort": "1",
}
TIMEOUT = 40.0
# 한 번에 여는 쟈란 페이지 수 — 모음 8곳 × 날짜 4개가 한꺼번에 몰리지 않게.
CONCURRENCY = 4

# 날짜 — **오늘 기준으로 계산한다**(박아 두면 몇 달 뒤 지난 날짜를 조회한다).
# 수요일(평일)로 네 번, 몇 주씩 띄워 계절이 갈리게 한다. 일본 성수기(연휴)에 걸리면 한 주 민다.
STAY_DATES = 4
STAY_WEEKDAY = 2                 # 월=0 … 수=2
STAY_FIRST_WEEKS = 4             # 4주 뒤부터 — 너무 가까우면 빈방이 적어 비싸게 나온다
STAY_GAP_WEEKS = 4
# (월, 일) ~ (월, 일) — 골든위크 · 오봉 · 연말연시. 이 안에 들면 비수기 평일이 아니다.
_PEAK = (((4, 27), (5, 7)), ((8, 8), (8, 18)), ((12, 26), (1, 5)))

# 같은 숙소를 다시 열지 않는 시간. 요금은 날마다 변하므로 한 회차(밤 미리 만들기 한 번) 안쪽이다.
CACHE_SECONDS = 6 * 3600
_CACHE: dict[str, tuple[float, dict[str, Any] | None]] = {}
_CACHE_CAP = 200

# 이름이 이만큼 닮으면 주소 없이도 같은 숙소로 본다. 지점명만 다른 체인(도미인 간다/시부야)이
# 0.87 쯤 나오므로 그보다 높게 둔다.
NAME_SURE = 0.9
# 이름이 이만큼 닮고 **주소(동네까지)도 맞으면** 같은 숙소로 본다.
NAME_WITH_ADDRESS = 0.6


# ─── 순수 함수(시험이 부른다) ────────────────────────────────────────────────

def _text(html: str) -> str:
    t = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", html or "")
    t = re.sub(r"(?s)<[^>]+>", " ", t)
    t = t.replace("&nbsp;", " ").replace("&gt;", ">").replace("&lt;", "<").replace("&amp;", "&")
    return re.sub(r"\s+", " ", t).strip()


def _norm(s: str) -> str:
    """견줄 때 쓰는 납작한 글자 — 전각·반각·띄어쓰기·기호 차이를 지운다."""
    s = unicodedata.normalize("NFKC", s or "").lower()
    return re.sub(r"[\s・･·\-‐−ー_/()（）「」『』〈〉<>.,、。]+", "", s)


_BLOCK_RE = re.compile(r'<li class="p-yadoCassette p-searchResultItem"', re.S)


def parse_search(html: str) -> list[dict[str, str]]:
    """검색 결과 → `[{"yad", "name", "address"}]` (결과 순서 그대로)."""
    out: list[dict[str, str]] = []
    starts = [m.start() for m in _BLOCK_RE.finditer(html or "")]
    for i, s in enumerate(starts):
        block = html[s:starts[i + 1] if i + 1 < len(starts) else len(html)]
        yad = re.search(r"openYadoSyosai\('(\d+)'", block)
        name = re.search(r'class="p-searchResultItem__facilityName"[^>]*>(.*?)</', block, re.S)
        addr = re.search(r"住所</dt>\s*<dd[^>]*>(.*?)</dd>", block, re.S)
        if not yad or not name:
            continue
        out.append({
            "yad": yad.group(1),
            "name": _text(name.group(1)),
            "address": _text(addr.group(1)) if addr else "",
        })
    return out


def name_score(want: str, got: str) -> float:
    """두 상호가 얼마나 닮았나(0~1). 한쪽이 다른 쪽을 통째로 품으면 0.95 로 본다
    — 쟈란은 「明神の湯 ドーミーインPREMIUM神田」처럼 앞에 온천 이름을 붙인다."""
    a, b = _norm(want), _norm(got)
    if not a or not b:
        return 0.0
    if len(a) >= 4 and len(b) >= 4 and (a in b or b in a):
        return 0.95
    return difflib.SequenceMatcher(None, a, b).ratio()


def _town(address: str) -> str:
    """주소 앞머리 — 번지 숫자 앞까지(「東京都千代田区神田須田町」)."""
    s = unicodedata.normalize("NFKC", address or "")
    s = re.sub(r"〒?\s*\d{3}-\d{4}", "", s)
    s = re.sub(r"^\s*日本[、,]?\s*", "", s)
    s = re.sub(r"\s+", "", s)
    m = re.match(r"[^\d]+", s)
    return m.group(0) if m else ""


def pick_yad(results: list[dict[str, str]], name_ja: str, address: str = "") -> str | None:
    """검색 결과에서 **그 숙소** 하나를 고른다. 확신이 없으면 None.

    이름이 아주 닮았거나(`NAME_SURE`), 꽤 닮고 주소 동네까지 같아야(`NAME_WITH_ADDRESS`) 쓴다.
    """
    want_town = _town(address)
    best: tuple[float, str] | None = None
    for r in results:
        score = name_score(name_ja, r.get("name", ""))
        got_town = _town(r.get("address", ""))
        town_ok = bool(want_town and got_town and (got_town in want_town or want_town in got_town))
        if score >= NAME_SURE or (score >= NAME_WITH_ADDRESS and town_ok):
            if best is None or score > best[0]:
                best = (score, r["yad"])
    return best[1] if best else None


_PRICE_RE = re.compile(r'"roomTypeCd":"[^"]*","price":(\d+)')


def parse_min_price(html: str) -> int | None:
    """플랜 페이지 → 그 날짜의 **2인 1실** 최저가(엔). 빈방이 없으면 None.

    조회 주소에 `adultNum=2` 를 넣어 부르므로 `price` 가 곧 2인 1실 값이다(`unitPrice` 는 1인).
    """
    prices = [int(x) for x in _PRICE_RE.findall(html or "")]
    return min(prices) if prices else None


# 「4つ星」·「４つ星ホテル」. 전각 숫자는 NFKC 로 반각이 된다.
_STARS_RE = re.compile(r"([1-5])\s*つ星")


def parse_stars(html: str) -> int | None:
    """숙소 페이지에 **글자로 적힌** 등급만 읽는다. 없으면 None — 짐작하지 않는다.

    ⚠ 별 그림(`c-starRating`)은 후기 평점이다. 글자(`N つ星`)만 본다.
    """
    t = unicodedata.normalize("NFKC", _text(html))
    found = {int(m.group(1)) for m in _STARS_RE.finditer(t)}
    # 한 페이지에 다른 등급이 둘 이상 적혀 있으면(다른 숙소 추천 칸 등) 믿지 않는다.
    return found.pop() if len(found) == 1 else None


def _in_peak(d: date) -> bool:
    for (m1, d1), (m2, d2) in _PEAK:
        start = (m1, d1)
        end = (m2, d2)
        here = (d.month, d.day)
        if start <= end:
            if start <= here <= end:
                return True
        elif here >= start or here <= end:   # 해를 넘기는 구간(연말연시)
            return True
    return False


def stay_dates(today: date, n: int = STAY_DATES) -> list[date]:
    """오늘 기준 **비수기 평일** n개 — 몇 주씩 띄운 수요일. 성수기에 걸리면 한 주씩 민다."""
    out: list[date] = []
    d = today + timedelta(weeks=STAY_FIRST_WEEKS)
    d += timedelta(days=(STAY_WEEKDAY - d.weekday()) % 7)
    while len(out) < n:
        while _in_peak(d):
            d += timedelta(weeks=1)
        out.append(d)
        d += timedelta(weeks=STAY_GAP_WEEKS)
    return out


def krw_range(yen: int | None, rate: float | None = None) -> str:
    """엔 → 「N만원대」. 1만원이 안 되면 「1만원 미만」. 값이 없으면 빈 문자열."""
    if not yen:
        return ""
    won = yen * (settings.JPY_KRW_RATE if rate is None else rate)
    man = int(won // 10000)
    return f"{man}만원대" if man >= 1 else "1만원 미만"


def fact_line(fact: dict[str, Any] | None) -> str:
    """프롬프트에 싣는 한 줄 — 성급 · 2인 최저가 범위 · 조회 날짜. 못 찾은 칸은 「확인 못 함」이다."""
    if not fact:
        return "성급 확인 못 함 · 요금 확인 못 함(쟈란에서 이 숙소를 찾지 못했다)"
    stars = f"{fact['stars']}성급(쟈란 표기)" if fact.get("stars") else "성급 확인 못 함"
    yen = fact.get("min_yen")
    days = " · ".join(fact.get("dates") or [])
    if yen:
        per = krw_range(yen // 2)
        price = (f"2인 1실 최저 {krw_range(yen)}" + (f"(1인 환산 {per})" if per else "")
                 + f" — 쟈란 {days} 숙박 조회 중 가장 싼 1박")
    else:
        price = f"요금 확인 못 함(쟈란 {days} 조회에 빈방·요금이 없었다)" if days else "요금 확인 못 함"
    return f"{stars} · {price}"


# ─── 네트워크 ───────────────────────────────────────────────────────────────

async def _get(client: httpx.AsyncClient, url: str, params: str | dict | None = None) -> str:
    try:
        r = await client.get(url, params=params)
        if r.status_code != 200:
            logger.warning(f"[jalan] {r.status_code} — {url[:90]}")
            return ""
        return r.content.decode("cp932", "ignore")
    except Exception as e:
        logger.warning(f"[jalan] 열지 못함 — {url[:90]}: {type(e).__name__} {e}")
        return ""


def _search_query(keyword: str) -> str:
    """검색어는 **cp932 로** 인코딩해야 걸린다(utf-8 로 보내면 0건)."""
    parts = [f"keyword={quote(keyword, encoding='cp932', errors='ignore')}"]
    parts += [f"{k}={v}" for k, v in SEARCH_PARAMS.items()]
    return "&".join(parts)


async def _lookup(client: httpx.AsyncClient, gate: asyncio.Semaphore,
                  place: dict[str, Any]) -> dict[str, Any] | None:
    from app.services import place_lookup

    name_ja = await place_lookup.local_name(place)
    if not name_ja:
        logger.info(f"[jalan] 일본어 이름을 못 받아 건너뜁니다 — {place.get('name')}")
        return None
    async with gate:
        html = await _get(client, f"{SEARCH_URL}?{_search_query(name_ja)}")
    yad = pick_yad(parse_search(html), name_ja, str(place.get("address") or ""))
    if not yad:
        logger.info(f"[jalan] 맞는 숙소가 없습니다 — {place.get('name')} / {name_ja}")
        return None

    days = stay_dates(date.today())

    async def one_day(d: date) -> int | None:
        async with gate:
            page = await _get(
                client, f"https://www.jalan.net/yad{yad}/plan/",
                {"stayYear": d.year, "stayMonth": d.month, "stayDay": d.day,
                 "stayCount": 1, "roomCount": 1, "adultNum": 2})
        return parse_min_price(page)

    prices = await asyncio.gather(*(one_day(d) for d in days))
    async with gate:
        top = await _get(client, f"https://www.jalan.net/yad{yad}/")
    got = [p for p in prices if p]
    fact = {
        "yad": yad,
        "name_ja": name_ja,
        "min_yen": min(got) if got else None,
        "dates": [d.isoformat() for d in days],
        "stars": parse_stars(top),
    }
    logger.info(f"[jalan] {place.get('name')} → yad{yad} · 최저 {fact['min_yen']}엔 · 성급 {fact['stars']}")
    return fact


async def facts_many(places: list[dict[str, Any]]) -> list[dict[str, Any] | None]:
    """곳마다 `{"yad","name_ja","min_yen","dates","stars"}` 또는 None(못 찾음). 순서는 그대로다."""
    now = time.monotonic()
    out: list[dict[str, Any] | None] = [None] * len(places)
    todo: list[int] = []
    for i, p in enumerate(places):
        key = str(p.get("place_id") or "")
        hit = _CACHE.get(key) if key else None
        if hit and now - hit[0] < CACHE_SECONDS:
            out[i] = hit[1]
        elif key:
            todo.append(i)
    if not todo:
        return out
    gate = asyncio.Semaphore(CONCURRENCY)
    async with httpx.AsyncClient(timeout=TIMEOUT, headers=UA, follow_redirects=True) as client:
        async def safe(i: int) -> None:
            try:
                out[i] = await _lookup(client, gate, places[i])
            except Exception as e:
                # 한 곳이 터져도 나머지는 산다 — 요금·성급은 있으면 좋은 재료다.
                logger.warning(f"[jalan] 조회 실패 — {places[i].get('name')}: {type(e).__name__} {e}")
                out[i] = None
            _CACHE[str(places[i]["place_id"])] = (time.monotonic(), out[i])
        await asyncio.gather(*(safe(i) for i in todo))
    while len(_CACHE) > _CACHE_CAP:
        _CACHE.pop(next(iter(_CACHE)))
    return out
