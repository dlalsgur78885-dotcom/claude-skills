"""트래블어시 가이드를 읽는다 — 지도 축의 **모든 재료**가 여기서 온다.

## 왜 이 파일이 필요한가

지도 축은 다른 두 축과 재료가 다르다. 상황별 일본어는 모델이 지어내고, 일본맛집은
구글 지도에서 확인한다. **지도 축은 트래블어시 가이드에 이미 있는 것만 쓴다** —
주제도, 장소 3곳도, 그 숫자도 전부 가이드 데이터가 정한다
(`지도_1단계_주제후보.md` 「가이드 데이터를 읽어서 찾는다. 기억으로 짜지 않는다」).

## 어디서 오는가

봇의 `read_travel_guide` 와 **같은 공개 API** 다. 로그인·쿠키가 필요 없어
(2026-08-24 맨몸 curl 로 확인) 파이썬에서 그냥 부르면 된다.

  GET /api/web/guides/list?limit=300   가이드 목록
  GET /api/web/guides/list?id=<가이드ID> 그 가이드의 장소·버튼 전부

⚠ 가이드 화면 주소(`…guides<ID>.apsl`)를 그냥 열면 **빈 껍데기**만 온다. 화면을
  자바스크립트가 그리기 때문이다. 반드시 위 API 를 쓴다.

## 「상단 버튼」이 무엇인가

지침서가 말하는 **상단 버튼 카테고리**는 응답의 `composition` 이다 —
`[{"name": "키즈카페·놀이터", "n": 90}, ...]`. 이 `n` 이 곧

  · 주제 문구 끝에 붙는 숫자 (「…실내 놀이터 **90**곳」)
  · 3-1 SUBHEADLINE 의 `N`

이고 **둘은 같은 숫자여야 한다**(`지도_1단계_주제후보.md` 2026-08-28).

⚠ 장소의 `category`(박물관·동물원…)는 **버튼 이름이 아니다.** 버튼 이름을 그대로
  `category` 필터에 넣으면 0건이 난다(지침서 2026-08-28 실측). 버튼 안의 장소는
  `category` 가 아니라 `groups[].keys`(place_id 목록)로 찾는다.
"""

import asyncio
import logging
import random
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)

BASE = "https://travelassi-web-production.up.railway.app"
TIMEOUT = 20.0

# ⚠ 가이드 서버에 한꺼번에 몰아 부르지 않는다(2026-10-05). 주제 하나마다 `all_buttons` 가 가이드
#   155개를 **동시에** 다시 받았고, 주제 5개를 겹쳐 돌리니 수백 개가 몰려 시간 초과로 무더기 실패했다
#   (22:04 한 순간에 155건). 못 받은 가이드의 버튼은 목록에서 빠져 「어느 가이드 버튼인지 찾지 못했습니다」
#   가 났다. 그래서 ① 동시에 부르는 수를 묶고 ② 실패하면 한 번 더 부르고 ③ 받은 가이드는 잠시 재사용한다.
CONCURRENCY = 8
CACHE_SECONDS = 30 * 60
_sem = asyncio.Semaphore(CONCURRENCY)
_guide_cache: dict[str, tuple[float, dict[str, Any] | None]] = {}
_buttons_cache: tuple[float, list[dict[str, Any]]] | None = None
_buttons_lock = asyncio.Lock()


async def _get(params: dict[str, Any]) -> list[dict[str, Any]]:
    async with _sem:
        for attempt in (1, 2):
            try:
                async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                    r = await client.get(f"{BASE}/api/web/guides/list", params=params)
                    r.raise_for_status()
                    return ((r.json() or {}).get("data") or {}).get("list") or []
            except (httpx.TimeoutException, httpx.TransportError):
                if attempt == 2:
                    raise
                await asyncio.sleep(2)
    return []


async def list_guides() -> list[dict[str, Any]]:
    """가이드 목록. 각 항목은 id·name·tagline·place_count 를 갖는다."""
    return [
        {
            "id": g.get("id"),
            "name": g.get("name"),
            "tagline": g.get("tagline"),
            "region": g.get("region"),
            "place_count": g.get("place_count"),
        }
        for g in await _get({"limit": 300})
        if g.get("id")
    ]


async def read_guide(guide_id: str) -> dict[str, Any] | None:
    """가이드 하나를 통째로. 장소·버튼(composition)·묶음(groups)이 다 들어 있다."""
    hit = _guide_cache.get(guide_id)
    if hit and time.monotonic() - hit[0] < CACHE_SECONDS:
        return hit[1]
    got = await _get({"id": guide_id})
    guide = got[0] if got else None
    _guide_cache[guide_id] = (time.monotonic(), guide)
    return guide


def buttons(guide: dict[str, Any]) -> list[dict[str, Any]]:
    """그 가이드의 **상단 버튼** 목록 — `[{"name", "n"}]`.

    `groups` 에는 버튼이 아닌 묶음도 섞여 있다(984곳짜리 가이드에서 composition 6개 :
    groups 10개). 화면 상단에 실제로 보이는 것은 `composition` 쪽이다.
    """
    out = []
    for c in guide.get("composition") or []:
        name = str(c.get("name") or "").strip()
        n = int(c.get("n") or 0)
        if name and n > 0:
            out.append({"name": name, "n": n})
    return out


def _ftid(place_id: str) -> str:
    """`ChIJ…` → `0x…:0x…`. **네트워크를 타지 않는다**(2026-09-04 실측 0ms).

    왜 필요한가 — 가이드마다 `groups[].keys` 의 형식이 다르다. kids_family 는 `ChIJ…` 를,
    pet_water 는 `0x…:0x…` 를 쓴다. 한쪽만 보면 그 가이드의 버튼이 통째로 **장소 0곳**이
    되어 주제가 실패한다(2026-09-04 「계곡 63곳」이 그랬다).
    """
    try:
        from app.services.place_lookup import VENDOR_ELFSIGHT, _with_path

        def go():
            from elfsight_place import place_id_to_cid  # type: ignore
            return place_id_to_cid(place_id) or ""
        return _with_path(VENDOR_ELFSIGHT, go)
    except Exception:
        return ""


def places_in(guide: dict[str, Any], button: str, count: int = 3,
              region: str = "") -> list[dict[str, Any]]:
    """그 버튼 안의 장소를 무작위로 `count` 곳 (`지도_1단계` 「버튼 안에서 랜덤」).

    `region` 을 주면 **그 지역 장소 중에서만** 고른다 — 「가이드 + 지역」 주제가
    「도쿄 …」 라고 해 놓고 부산 가게를 싣지 않게 하는 자리다(2026-09-04).

    ⚠ `groups[].keys` 의 place_id 가 `places` 에 다 있지는 않다(2026-09-04 실측 —
      90개 키 중 30곳만 조회됐다). 없는 것은 조용히 건너뛴다. 3곳을 고르기에는
      남는 수가 충분하고, **주제에 적는 숫자는 버튼의 `n`** 이라 이 차이와 무관하다.
    """
    # 두 형식을 다 걸어 둔다 — 어느 쪽으로 오든 찾히게(위 `_ftid` 주석).
    by_id: dict[str, dict[str, Any]] = {}
    for p in (guide.get("places") or []):
        pid = p.get("place_id")
        if not pid:
            continue
        by_id[pid] = p
        alt = _ftid(pid)
        if alt:
            by_id[alt] = p

    keys: list[str] = []
    for g in guide.get("groups") or []:
        if str(g.get("name") or "").strip() == button:
            keys = [str(k) for k in (g.get("keys") or [])]
            break

    pool = [by_id[k] for k in keys if k in by_id]
    if region:
        pool = [p for p in pool if region_of_place(p) == region]
    if not pool:
        return []
    # 사진 있는 곳을 먼저 채운다 — 그 사진이 본문 낱장 **배경**이라, 없으면 빈 낱장이 된다
    # (2026-09-04 실측 — 빵지순례 「동네 빵집」 3곳 중 1곳이 사진 0장이었다).
    def has_photo(p: dict[str, Any]) -> bool:
        return bool(p.get("thumb") or (p.get("photos") or []))

    withs = [p for p in pool if has_photo(p)]
    withouts = [p for p in pool if not has_photo(p)]
    picked = random.sample(withs, min(count, len(withs)))
    if len(picked) < count:  # 사진 있는 곳이 모자랄 때만 나머지로 채운다
        picked += random.sample(withouts, min(count - len(picked), len(withouts)))
    return [
        {
            "name": p.get("name") or "",
            # 📍위치 는 **구글맵 주소 그대로, 우편번호 포함**(지도_3-3단계).
            "address": p.get("address") or "",
            "category": p.get("category") or "",
            "rating": p.get("rating"),
            "tip": p.get("tip") or "",
            "blurb": (str(p.get("blurb") or ""))[:200],
            "why": (str(p.get("why") or ""))[:200],
            # 본문 낱장 배경 — 가이드가 이미 구글맵 사진을 들고 있어 따로 조회할 필요가 없다.
            "photo": p.get("thumb") or (p.get("photos") or [None])[0] or "",
            "photos": [u for u in [p.get("thumb"), *(p.get("photos") or [])] if u][:6],
            "place_id": p.get("place_id") or "",
        }
        for p in picked
    ]


_SIDO = {
    "서울": "서울", "부산": "부산", "대구": "대구", "인천": "인천", "광주": "광주",
    "대전": "대전", "울산": "울산", "세종": "세종", "경기": "경기", "강원": "강원",
    "충북": "충북", "충청북": "충북", "충남": "충남", "충청남": "충남",
    "전북": "전북", "전라북": "전북", "전남": "전남", "전라남": "전남",
    "경북": "경북", "경상북": "경북", "경남": "경남", "경상남": "경남", "제주": "제주",
}

# 일본 도도부현 (2026-09-04 사람 지시 — 「가이드 + 지역으로도 주제 생성 가능하도록」).
#
# ⚠ 가이드에는 **처음부터** 일본 장소가 섞여 있었다 — 아이랑 가이드의 도쿄 디즈니랜드·
#   스카이트리 같은 곳이다. 아래 표가 없던 동안 그 장소들은 전부 「전국」에 묻혀,
#   일본 주제를 낼 방법이 없었다.
# ⚠ 키는 都·道·府·県 까지 **통째로** 적는다. 「京都」 로 자르면 「東京都」 안에도 들어 있어
#   도쿄 장소가 교토로 세어진다.
_JP = {
    "北海道": "홋카이도", "青森県": "아오모리", "岩手県": "이와테", "宮城県": "미야기",
    "秋田県": "아키타", "山形県": "야마가타", "福島県": "후쿠시마", "茨城県": "이바라키",
    "栃木県": "도치기", "群馬県": "군마", "埼玉県": "사이타마", "千葉県": "지바",
    "東京都": "도쿄", "神奈川県": "가나가와", "新潟県": "니가타", "富山県": "도야마",
    "石川県": "이시카와", "福井県": "후쿠이", "山梨県": "야마나시", "長野県": "나가노",
    "岐阜県": "기후", "静岡県": "시즈오카", "愛知県": "아이치", "三重県": "미에",
    "滋賀県": "시가", "京都府": "교토", "大阪府": "오사카", "兵庫県": "효고",
    "奈良県": "나라", "和歌山県": "와카야마", "鳥取県": "돗토리", "島根県": "시마네",
    "岡山県": "오카야마", "広島県": "히로시마", "山口県": "야마구치", "徳島県": "도쿠시마",
    "香川県": "가가와", "愛媛県": "에히메", "高知県": "고치", "福岡県": "후쿠오카",
    "佐賀県": "사가", "長崎県": "나가사키", "熊本県": "구마모토", "大分県": "오이타",
    "宮崎県": "미야자키", "鹿児島県": "가고시마", "沖縄県": "오키나와",
}


def region_of_place(place: dict[str, Any]) -> str:
    """장소 하나가 **어디에 있는지** 한 낱말로. 모르면 빈 문자열이다."""
    addr = str(place.get("address") or "").strip()
    if not addr:
        return ""
    for key, name in _JP.items():
        if key in addr:
            return name
    # 국내 주소는 시·도가 맨 앞에 온다. 일본 주소는 우편번호(〒…)가 먼저 와서 못 쓴다.
    head = addr.split()[0]
    for key, name in _SIDO.items():
        if head.startswith(key):
            return name
    return ""


def region_counts(places: list[dict[str, Any]]) -> dict[str, int]:
    """지역별 장소 수. 「가이드 + 지역」 주제의 **숫자가 여기서 나온다.**"""
    counts: dict[str, int] = {}
    for p in places:
        name = region_of_place(p)
        if name:
            counts[name] = counts.get(name, 0) + 1
    return counts


def region_of(places: list[dict[str, Any]]) -> str:
    """그 장소들이 실제로 **어디에 있는지** 한 낱말로.

    ⚠ 가이드 이름·id 로 짐작하면 안 된다. `demo_bread_busan` 은 이름만 부산이고
      실제로는 부산 28 · 서울 24 · 대전 23 … 전국이다. 그런데 모델은 이름을 보고
      「부산 — …」 이라고 적었고, 정작 장소는 **후쿠오카** 가게였다(2026-09-04).
      주제 문구에 지역이 들어가므로 **주소에서 세어** 정한다.

    한 곳이 6할을 넘으면 그 지역, 아니면 「전국」이다. 지역을 못 읽은 것이 많아도
    「전국」으로 두고 지역을 붙이지 않는다 — 틀리게 붙이는 것보다 낫다.
    """
    counts = region_counts(places)
    total = sum(counts.values())
    if not total or total < len(places) * 0.6:
        return "전국"
    top, n = max(counts.items(), key=lambda kv: kv[1])
    return top if n >= total * 0.6 else "전국"


async def all_buttons() -> list[dict[str, Any]]:
    """모든 가이드의 버튼을 한 줄로 편다 — 주제 후보를 만들 재료다.

    `지도_1단계` 「여러 가이드를 가로질러 10개를 뽑는다」(2026-08-27 확정).

    주제마다 부르므로 한 번 편 목록은 `CACHE_SECONDS` 동안 그대로 돌려준다. 여럿이 동시에
    부르면 한 번만 받고 나머지는 그 결과를 기다린다(`_buttons_lock`).
    """
    global _buttons_cache
    async with _buttons_lock:
        if _buttons_cache and time.monotonic() - _buttons_cache[0] < CACHE_SECONDS:
            return list(_buttons_cache[1])
        rows, failed = await _collect_buttons()
        # 일부라도 못 받았으면 재사용하지 않는다 — 빠진 가이드의 버튼을 30분 동안 못 찾게 된다.
        if not failed:
            _buttons_cache = (time.monotonic(), rows)
        return rows


async def _collect_buttons() -> tuple[list[dict[str, Any]], int]:
    guides = await list_guides()
    got = await asyncio.gather(*(read_guide(g["id"]) for g in guides), return_exceptions=True)

    rows: list[dict[str, Any]] = []
    failed = 0
    for g, full in zip(guides, got):
        if isinstance(full, Exception) or not full:
            failed += 1
            # 시간 초과는 메시지가 빈 문자열이라 종류를 함께 남긴다(전에는 「읽지 못했습니다: 」 로만 찍혔다).
            logger.warning(f"[guide] {g['id']} 를 읽지 못했습니다: {full!r}")
            continue
        for b in buttons(full):
            # 지역은 **그 버튼 안의 장소**에서 센다. 가이드 전체와 다를 수 있다
            # (빵지순례의 케이크·디저트 버튼은 일본 가게가 섞여 있었다).
            inside = places_in(full, b["name"], 999)
            rows.append({
                "guide_id": g["id"],
                "guide_name": g.get("name") or "",
                "guide_tagline": g.get("tagline") or "",
                "button": b["name"],
                "n": b["n"],
                "region": region_of(inside),
                # 「가이드 + 지역」 주제의 재료. 지역마다 **몇 곳인지**와 **지도를 그 지역으로
                # 점프시킬 장소 하나**를 함께 둔다(3-2 캡처가 앵커로 쓴다).
                "regions": _regions_in(inside),
            })
    return rows, failed


def _regions_in(places: list[dict[str, Any]], top: int = 8) -> list[dict[str, Any]]:
    """그 버튼 안의 지역들 — `[{"name", "n", "anchor"}]`, 많은 순.

    `anchor` 는 그 지역 장소 하나의 이름이다. 지도 캡처가 버튼 칩만 누르면 화면이
    **버튼 전체 핀**에 맞춰져, 「도쿄 …」 주제인데 한국까지 담긴 지도가 나온다.
    """
    counts = region_counts(places)
    anchors: dict[str, str] = {}
    for p in places:
        name = region_of_place(p)
        if name and name not in anchors and p.get("name"):
            anchors[name] = str(p["name"])
    ordered = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)[:top]
    return [{"name": k, "n": v, "anchor": anchors.get(k, "")} for k, v in ordered]
