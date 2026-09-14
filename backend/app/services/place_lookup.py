"""장소를 **사실로** 확인한다 — 이름 → place_id → 주소·영업시간·평점·사진.

## 왜 필요한가

일본맛집 축은 **실제 가게**를 다룬다. 가게 이름·주소·영업시간이 캐러셀에 그대로 들어가므로
지어내면 안 된다(`docs/process/_공통.md` 「장소를 다룰 때는 place_info 로 확인한다」).
문구 모델은 그럴듯하게 틀리기 때문에, 짓기 **전에** 여기서 걸러야 한다.

## 어디서 오는가

봇이 쓰던 것과 **같은 벤더**를 그대로 부른다(`캐러셀 봇/vendor/`). 봇은 JS 라 파이썬을
자식 프로세스로 띄웠지만, 일꾼은 파이썬이라 **바로 임포트**하면 된다.

  gmap_search  이름 → place_id (정식 API 없이 HTTP 검색, 비용 0)
  elfsight     place_id → 이름·주소·영업시간·평점·전화·대표사진·리뷰

API 키가 필요 없다. 대신 **봇 폴더가 있어야 돈다** — 없으면 조용히 빈 결과를 준다.

⚠ `elfsight` 와 `gmap_search` 는 sys.path 에 함께 올리면 이름이 부딪힌다(봇에서 겪음).
  그래서 **부를 때마다 넣고 빼는** 방식으로 격리한다.
"""

import asyncio
import logging
import sys
import threading
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# 벤더 조회를 한 줄로 세운다 — 이유는 `_with_path` 주석 참고.
_VENDOR_LOCK = threading.Lock()

# 주소를 현지 말로 다시 받아 올 나라. 여기 없는 나라는 검색을 한 번만 한다.
_LOCAL_LANG = {"jp": "ja"}

# 봇 폴더는 이 레포의 형제다. 이동하면 여기만 고치면 된다.
BOT_ROOT = Path(__file__).resolve().parents[3].parent / "캐러셀 봇"
VENDOR_ELFSIGHT = BOT_ROOT / "vendor" / "elfsight"
VENDOR_SEARCH = BOT_ROOT / "vendor" / "gmap_search"
VENDOR_KOALA = BOT_ROOT / "vendor" / "koalamap"


def is_available() -> bool:
    return VENDOR_ELFSIGHT.is_dir() and VENDOR_SEARCH.is_dir()


def _with_path(vendor: Path, fn):
    """벤더 하나만 sys.path 에 올린 채 부르고 곧바로 뺀다(이름 충돌 방지).

    ⚠ **한 번에 하나만 돌아야 한다.** `sys.path` 와 `sys.modules` 는 프로세스 전체가 함께
      쓰는 것이라, 여러 곳을 동시에 조회하면 A 가 임포트하는 중에 B 가 같은 이름을 지운다
      (2026-09-03 실측 — 8곳 중 1곳이 `KeyError: 'elfsight_reviews'` 로 주소를 못 받았다).
      그래서 자물쇠로 줄을 세운다. 그만큼 느려지지만, 조용히 틀린 값을 쓰는 것보다 낫다.
    """
    p = str(vendor)
    with _VENDOR_LOCK:
        return _run_with_path(p, fn)


def _run_with_path(p: str, fn):
    sys.path.insert(0, p)
    try:
        return fn()
    finally:
        try:
            sys.path.remove(p)
        except ValueError:
            pass
        # 다음 호출이 다른 벤더의 같은 이름 모듈을 받도록 캐시도 비운다.
        for name in list(sys.modules):
            # ⚠ `elfsight` 도 비워야 한다 — elfsight 벤더의 것과 koalamap 안의 패키지가
            #   이름이 같아서, 한쪽이 캐시에 남아 있으면 다른 쪽이 영영 안 잡힌다.
            if name.split(".")[0] in ("elfsight", "elfsight_place", "elfsight_reviews", "models", "modules"):
                sys.modules.pop(name, None)


def _search_sync(name: str, country: str) -> dict[str, Any] | None:
    def go():
        from modules.finder import Finder  # type: ignore
        res = Finder().search(name, country=country)
        # ⚠ 버전에 따라 목록을 바로 주기도 하고 {"results": [...]} 로 감싸 주기도 한다
        #   (봇의 JS 래퍼가 감싸 줘서 헷갈렸다 — 2026-09-03 실측). 둘 다 받는다.
        items = res if isinstance(res, list) else (res or {}).get("results") or []
        if not items:
            return None
        first = items[0]
        # 객체(dataclass)로 올 수도 있다 — dict 로 맞춘다.
        if not isinstance(first, dict):
            first = {k: getattr(first, k, None) for k in
                     ("pid", "place_id", "name", "address", "category", "rating", "photo", "phone",
                      "lat", "lng", "cid")}
        # ⚠ 이 벤더는 place_id 를 **`pid`** 로 부른다(2026-09-03 실측 — 이름이 달라 조용히
        #   "못 찾았다" 로 떨어졌다). 둘 다 받아 하나로 맞춘다.
        if not first.get("place_id") and first.get("pid"):
            first["place_id"] = first["pid"]
        return first
    try:
        return _with_path(VENDOR_SEARCH, go)
    except Exception as e:
        logger.warning(f"[place] 검색 실패 — {name}: {type(e).__name__} {e}")
        return None


def _local_address_sync(name: str, country: str, place_id: str, cid: str) -> str:
    """**현지 말로 한 번 더 검색해** 우편번호까지 붙은 전체 주소를 받는다.

    기본 검색(`lang="ko"`)이 주는 주소는 **첫 줄 조각뿐**이다 — 「503 Godocho」처럼
    시·현·우편번호가 통째로 빠진다(2026-09-09 사람 신고 — 일본맛집 본문 📍위치 칸이
    전부 조각 주소로 나갔다). 같은 곳을 `lang="ja"` 로 찾으면 구글이
    「〒456-0043 愛知県名古屋市熱田区神戸町５０３」 를 한 줄로 준다. 지침서가 요구하는
    모양(`지도_3-3단계_본문.md` — 「우편번호(〒)도 포함한다」)이 이쪽이다.

    **place_id 가 같은 것만** 쓴다. 검색어가 같아도 다른 가게가 1위로 올라올 수 있는데,
    엉뚱한 주소를 붙이는 것은 조각 주소보다 나쁘다. 못 맞추면 빈 값을 주고 부르는 쪽이
    쓰던 주소를 그대로 쓴다.
    """
    def go():
        from modules.finder import Finder  # type: ignore
        res = Finder().search(name, country=country, lang=_LOCAL_LANG[country])
        items = res if isinstance(res, list) else (res or {}).get("results") or []
        for it in items:
            d = it if isinstance(it, dict) else {
                k: getattr(it, k, None) for k in ("pid", "place_id", "cid", "address")}
            if (d.get("place_id") or d.get("pid")) == place_id or (cid and d.get("cid") == cid):
                return str(d.get("address") or "")
        return ""
    try:
        return _with_path(VENDOR_SEARCH, go) or ""
    except Exception as e:
        logger.warning(f"[place] 현지어 주소 검색 실패 — {name}: {type(e).__name__} {e}")
        return ""


def _meta_address_sync(place_id: str) -> str:
    """현지어 검색이 못 맞췄을 때의 마지막 수단 — 리뷰 벤더가 들고 있는 **전체 주소**.

    영어 표기라 「〒」 는 없지만 시·현·우편번호가 다 들어 있다
    (`2 Chome-2-1 Honmachi, Kanazawa, Ishikawa 920-0853, Japan`).
    조각 주소(`1階`)를 낱장에 올리는 것보다 낫다 — place_id 로 바로 받으므로
    **엉뚱한 가게가 섞일 일도 없다.**
    """
    def go():
        from elfsight_reviews import _Elf  # type: ignore

        async def run():
            elf = _Elf()
            await elf._setup()
            try:
                src = await elf._wait(place_id, 40)
                return str(((src or {}).get("meta") or {}).get("address") or "")
            finally:
                await elf.session.close()

        # 별도 스레드에서 도는 함수라 새 루프를 열어도 바깥과 부딪히지 않는다(`_photos_sync` 와 같다).
        return asyncio.run(run())
    try:
        return _with_path(VENDOR_ELFSIGHT, go) or ""
    except Exception as e:
        logger.warning(f"[place] 주소 되찾기 실패 — {place_id}: {type(e).__name__} {e}")
        return ""


def _detail_sync(place_id: str) -> dict[str, Any] | None:
    def go():
        from elfsight_place import fetch_place  # type: ignore
        p = fetch_place(place_id)
        return p if isinstance(p, dict) else None
    try:
        return _with_path(VENDOR_ELFSIGHT, go)
    except Exception as e:
        logger.warning(f"[place] 상세 실패 — {place_id}: {type(e).__name__} {e}")
        return None


async def verify(name: str, country: str = "jp") -> dict[str, Any]:
    """가게 이름 하나를 확인한다.

    돌려주는 것: `{"ok", "name", "address", "hours", "rating", "reviews", "photo", "place_id"}`
    `ok=False` 면 **그 장소는 쓰지 않는다** — 검색에 안 나오는 이름은 지어낸 것일 수 있다.
    """
    if not is_available():
        return {"ok": False, "name": name, "why": "장소 조회 도구가 없습니다"}

    hit = await asyncio.to_thread(_search_sync, name, country)
    if not hit or not hit.get("place_id"):
        return {"ok": False, "name": name, "why": "구글 지도에서 찾지 못했습니다"}

    detail = await asyncio.to_thread(_detail_sync, hit["place_id"]) or {}
    # 주소만 현지 말로 한 번 더 받는다 — 위 둘은 조각만 준다(`_local_address_sync`).
    local_addr = ""
    if country in _LOCAL_LANG:
        local_addr = await asyncio.to_thread(
            _local_address_sync, name, country, hit["place_id"], hit.get("cid") or "")
        # 이름만으로는 같은 곳을 다시 못 집을 때가 있다(흔한 상호·지점명). 그때만 한 번 더.
        if not local_addr:
            local_addr = await asyncio.to_thread(_meta_address_sync, hit["place_id"])
    # 검색 결과가 기본, 상세가 있으면 덮어쓴다(상세 쪽이 더 정확하다).
    return {
        "ok": True,
        "place_id": hit["place_id"],
        "name": detail.get("name") or hit.get("name") or name,
        # ⚠ 현지어 주소가 먼저다. 나머지 둘은 첫 줄 조각이라 우편번호·시·현이 없다.
        "address": local_addr or detail.get("address") or hit.get("address") or "",
        "category": detail.get("category") or hit.get("category") or "",
        "rating": detail.get("rating") or hit.get("rating"),
        "reviews": detail.get("reviews_count") or detail.get("review_count"),
        "hours": detail.get("hours") or detail.get("opening_hours") or "",
        "photo": detail.get("photo") or hit.get("photo") or "",
        # 구글이 직접 적어 두는 가게 소개. 짧지만 **그 가게에만 해당하는 말**이라
        # 본문 넉 줄을 채울 때 제일 값지다(2026-09-07 — 받아 놓고 버리고 있었다).
        "description": detail.get("description") or "",
        "phone": detail.get("phone") or hit.get("phone") or "",
        "website": detail.get("website") or "",
        # 아래 셋은 사진을 더 받을 때만 쓴다(`photos`). 지금 안 쓰더라도 여기서 챙겨 둬야
        # 나중에 다시 검색하지 않는다.
        "lat": detail.get("lat") or hit.get("lat"),
        "lng": detail.get("lng") or hit.get("lng"),
        "cid": hit.get("cid") or "",
        "asked": name,          # 모델이 부른 이름 — 실제 이름과 다르면 사람이 알아야 한다
    }


def _photos_sync(place: dict[str, Any], cap: int) -> list[str]:
    """한 가게의 사진을 여러 장 받는다. 봇의 `fetchPhotos` 와 같은 길이다.

    `verify` 가 주는 대표 사진은 **한 장**뿐이다. 사람이 고를 수 있으려면 여러 장이 필요한데,
    그건 elfsight 가 아니라 **koalamap** 벤더가 준다. 두 걸음이다:

      ① place_id → cid. 검색이 이미 준 게 있으면 그걸 쓰고, 없으면 elfsight 로 바꾼다.
      ② cid 로 **진짜 지도 주소 형태**를 만들어 koalamap 에 넣는다.

    ⚠ 합성 주소(`?q=place_id:...`)는 400 "Unable to parse Map url" 이 난다.
      아래 `/maps/place/이름/@위도,경도,17z/...!1s<cid>` 형태만 통한다(봇에서 겪은 것).
    """
    cid = place.get("cid") or ""
    if not cid:
        def to_cid():
            from elfsight_place import place_id_to_cid  # type: ignore
            return place_id_to_cid(place.get("place_id") or "")
        cid = _with_path(VENDOR_ELFSIGHT, to_cid)
    if not cid:
        return []

    name = (place.get("name") or "place").replace(" ", "+")
    url = (f"https://www.google.com/maps/place/{name}"
           f"/@{place.get('lat') or 0},{place.get('lng') or 0},17z/data=!3m1!4b1!4m6!3m5!1s{cid}")

    def go():
        # elfsight 벤더가 path 에서 빠진 뒤라야 koalamap 안의 `elfsight` 패키지가 잡힌다.
        from elfsight import Elfsight  # type: ignore

        async def run():
            m = await Elfsight().fetch(url, max_reviews=1, include_reviews=False, include_photos=True)
            if not m:
                return []
            out = []
            for a in (getattr(m, "attachments", None) or []):
                kind = str(getattr(a, "type", "")).split(".")[-1].lower()
                u = getattr(a, "url", None)
                if u and kind != "video":
                    out.append(str(u))
            return out[:cap]

        # 이 함수는 별도 스레드에서 돈다 — 새 루프를 열어도 바깥 루프와 부딪히지 않는다.
        return asyncio.run(run())

    return _with_path(VENDOR_KOALA, go)


PHOTO_TRIES = 3


async def photos(place: dict[str, Any], cap: int = 6) -> list[str]:
    """`verify` 결과 하나를 받아 그 가게의 사진 주소들을 준다. 실패하면 빈 목록이다.

    **한 번 어긋났다고 포기하지 않는다** (2026-09-07). 이 조회는 정식 API 가 아니라 구글
    지도 페이지를 긁는 것이라 간헐적으로 실패한다 — 벤더가 파싱하다
    `AttributeError: 'NoneType' … .get` 으로 죽는다. **같은 가게를 몇 초 뒤에 다시 부르면
    6장을 그대로 준다**(2026-09-07 재현 확인 — 그 전 회차에 실패했던 세 곳이 전부 성공).

    그냥 넘기면 그 낱장만 사진 후보가 `verify` 의 대표 1장뿐이라 화면에서 바꿀 수가 없다
    (2026-09-07 일본맛집 회차에서 8곳 중 5곳이 그랬다).
    """
    if not VENDOR_KOALA.is_dir() or not place.get("place_id"):
        return []
    last: Exception | None = None
    for attempt in range(1, PHOTO_TRIES + 1):
        try:
            return await asyncio.to_thread(_photos_sync, place, cap)
        except Exception as e:
            last = e
            if attempt < PHOTO_TRIES:
                logger.info(f"[place] 사진 다시 시도 {attempt + 1}/{PHOTO_TRIES} — "
                            f"{place.get('name')}: {type(e).__name__}")
                await asyncio.sleep(1.5 * attempt)
    # 세 번 다 실패했으면 그때는 자취를 남긴다 — 한 줄짜리 이름만으론 원인을 못 찾는다.
    logger.warning(f"[place] 사진 실패 — {place.get('name')}: {type(last).__name__} {last}"
                   f" ({PHOTO_TRIES}번 시도)", exc_info=last)
    return []


async def photos_many(places: list[dict[str, Any]], cap: int = 6, limit: int = 3) -> list[list[str]]:
    """여러 가게의 사진을 동시에 받는다.

    ⚠ 이 호출은 `verify` 보다 무겁다(장소마다 지도 페이지를 한 번 더 연다). 그래서 동시
      개수를 3 으로 낮춰 뒀다 — 8곳이면 10~20초쯤 걸린다. 밤에 미리 도는 작업이라 괜찮다.
    """
    gate = asyncio.Semaphore(limit)

    async def one(p: dict[str, Any]) -> list[str]:
        async with gate:
            return await photos(p, cap)

    return list(await asyncio.gather(*(one(p) for p in places)))


def _reviews_sync(place_id: str, cap: int) -> list[dict[str, Any]]:
    def go():
        from elfsight_reviews import fetch_reviews  # type: ignore
        r = fetch_reviews(place_id, cap=cap) or {}
        return [x for x in (r.get("reviews") or []) if isinstance(x, dict) and x.get("text")]
    return _with_path(VENDOR_ELFSIGHT, go) or []


async def reviews(place: dict[str, Any], cap: int = 30) -> list[dict[str, Any]]:
    """한 가게의 리뷰 본문. 실패하면 빈 목록이다 — 본문은 리뷰 없이도 나와야 한다.

    왜 필요한가 — 본문 넉 줄에 「그 가게만의 것」을 넣으라고 지침서가 요구하는데,
    `verify` 가 주는 이름·주소·평점·영업시간만으로는 어느 집에나 붙는 말밖에 못 쓴다.
    같은 주제로 8곳을 쓰면 여덟 장이 전부 비슷해진다(2026-09-07 사람 신고 — 삿포로 징기스칸).
    **웨이팅·예약·자리 수·간판 메뉴·값은 리뷰에만 있다.**
    """
    if not is_available() or not place.get("place_id"):
        return []
    try:
        return await asyncio.to_thread(_reviews_sync, place["place_id"], cap)
    except Exception as e:
        logger.warning(f"[place] 리뷰 실패 — {place.get('name')}: {type(e).__name__} {e}")
        return []


async def reviews_many(places: list[dict[str, Any]], cap: int = 30,
                       limit: int = 3) -> list[list[dict[str, Any]]]:
    """여러 가게의 리뷰를 받는다.

    ⚠ 실제로는 `_with_path` 자물쇠 때문에 한 줄로 선다(벤더 임포트가 프로세스 전역이라
      동시에 돌 수 없다). 8곳이면 30초 안팎이다 — 밤에 미리 도는 작업이라 괜찮다.
    """
    gate = asyncio.Semaphore(limit)

    async def one(p: dict[str, Any]) -> list[dict[str, Any]]:
        async with gate:
            return await reviews(p, cap)

    return list(await asyncio.gather(*(one(p) for p in places)))


async def verify_many(names: list[str], country: str = "jp", limit: int = 4) -> list[dict[str, Any]]:
    """여러 곳을 동시에 확인한다. 한 곳이 실패해도 나머지는 살린다."""
    gate = asyncio.Semaphore(limit)

    async def one(n: str) -> dict[str, Any]:
        async with gate:
            try:
                return await verify(n, country)
            except Exception as e:
                return {"ok": False, "name": n, "why": f"{type(e).__name__}: {e}"}

    return list(await asyncio.gather(*(one(n) for n in names)))
