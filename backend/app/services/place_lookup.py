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
import re
import sys
import threading
import time
import unicodedata
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


_POSTAL_RE = re.compile(r"〒?\s*(\d{3}-\d{4})")
_CJK_RE = re.compile(r"[　-ヿ㐀-鿿]+")
_DASH_RE = re.compile(r"[‐-―−]")                  # `1 Chome−3−7` 의 − 도 - 로
_FLOOR_RE = re.compile(r"\b(B?\d+F|B\d+)\b")      # 1F · B1F · B1
_LOT_RE = re.compile(r"^\d+ Chome-[\d-]*\d|^\d[\d-]*")


def en_address_lines(raw: str) -> str:
    """구글 영문 주소 → 낱장 📍위치 **한 줄**(번지·동네, 구·시·현).

    2026-09-21 사람 결정 — 일본맛집 위치 칸을 영문으로 통일한다. 처음엔 2줄이었다가 같은 날
    글자를 줄여(30px) 1줄로 바꿨다.
    2026-09-22 사람 지시 — 「주소에 우편 번호, 층 호수까지 다 빼줘」. 건물 이름도 함께 뺀다.
    구글이 주는 영문 주소는 모양이 제각각이라 그대로 못 쓴다(실측):
      `1 Chome-29-11 Asakusa, 台東区 Taito City, Tokyo 111-0032, Japan`  ← 한자가 섞인다
      `Japan, 〒604-8041 Kyoto, Nakagyo Ward, Uraderacho, 598`           ← 순서가 거꾸로다
      `Japan, 〒150-0041 Tokyo, Shibuya, Jinnan, 1 Chome−22−7 岩本ビル B1F` ← 번지 뒤에 건물·층
    그래서 `Japan` 과 한자를 떼고 순서를 맞춘다. **글자를 새로 짓지는 않는다** — 구글이 준
    로마자·숫자만 옮겨 담는다. 못 알아보면 빈 값을 주고 부르는 쪽이 일본어 주소를 쓴다.
    """
    s = unicodedata.normalize("NFKC", raw or "").strip()
    s = _DASH_RE.sub("-", s)
    reversed_order = s.lower().startswith("japan")
    s = _POSTAL_RE.sub("", s)
    s = re.sub(r"(\d+)\s*階", r"\1F ", s)          # 1 階D号 → 1F D
    s = _FLOOR_RE.sub(" ", s)
    s = _CJK_RE.sub(" ", s)
    parts = [re.sub(r"\s+", " ", p).strip() for p in s.split(",")]
    parts = [p for p in parts if p and p.lower() != "japan"]
    if not parts:
        return ""
    if reversed_order:
        # 시 → 구 → 동네 → 번지 로 온다. 뒤집어 번지를 동네 앞에 붙이고,
        # 번지 뒤에 남은 건물·호수 조각은 버린다.
        parts.reverse()
        lot = _LOT_RE.match(parts[0])
        if lot and len(parts) > 1:
            parts = [f"{lot.group(0)} {parts[1]}"] + parts[2:]
    # 번지가 든 칸부터 쓴다 — 그 앞에 붙어 오는 건물·층 칸은 버린다.
    k = next((i for i, p in enumerate(parts) if p[0].isdigit()), 0)
    return ", ".join(parts[k:])


# 우편번호 — `〒604-8055` · 영문 주소 끝의 `, 814-0032`
_POSTAL_ANY_RE = re.compile(r",?\s*〒?\s*(?<![\d-])\d{3}[-−－]\d{4}(?!\d)")
# 층·호수 — `1F` · `1階105` · `地下1階` · `3층` · `8 층` · `지하 1층` · `101호`
_FLOOR_ANY_RE = re.compile(
    r"\s*(?<![A-Za-z0-9])B?\d+[FＦ](?![A-Za-z])"
    r"|\s*(地下)?\s*\d+\s*階\s*[A-Za-z0-9]*(号室|号)?"
    r"|\s*(지하)?\s*\d+\s*층"
    r"|\s*\d+\s*호(?!선)"
)


def strip_postal_floor(addr: str) -> str:
    """지도 축 📍위치 — 가이드 주소 글자는 그대로 두고 **우편번호·층·호수만** 뗀다.

    2026-09-22 사람 지시 — 일본맛집처럼 지도 축도 「우편 번호, 층 호수까지 다 빼줘」.
    건물 이름은 모델이 뗀다(모양이 제각각이라 글자로는 못 가린다). 줄바꿈은 살린다.
    """
    s = _POSTAL_ANY_RE.sub("", addr or "")
    s = _FLOOR_ANY_RE.sub("", s)
    lines = [re.sub(r"[ \t　]+", " ", ln).strip(" ,").replace("📍 ", "📍") for ln in s.split("\n")]
    return "\n".join(ln for ln in lines if ln and ln != "📍")


async def english_address(place: dict[str, Any]) -> str:
    """한 가게의 영문 주소 한 줄. 못 받으면 빈 값이다."""
    if not is_available() or not place.get("place_id"):
        return ""
    raw = await asyncio.to_thread(_meta_address_sync, place["place_id"])
    if raw and "japan" not in raw.lower():
        return ""  # 일본 주소만 다룬다 — 지도 축의 국내 가게는 한국어 주소를 그대로 쓴다
    lines = en_address_lines(raw)
    if not lines:
        logger.warning(f"[place] 영문 주소를 못 받았습니다 — {place.get('name')}: {raw!r}")
    return lines


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
    """한 가게의 사진을 여러 장 받는다.

    `verify` 가 주는 대표 사진은 **한 장**뿐이다. 사람이 고를 수 있으려면 여러 장이 필요하다.
    두 걸음이다:

      ① place_id → cid. 검색이 이미 준 게 있으면 그걸 쓰고, 없으면 elfsight 로 바꾼다.
      ② cid 로 구글 사진첩 API(카테고리 → 사진)를 **바로** 부른다.

    ⚠ 전에는 koalamap 벤더(`Elfsight().fetch`)를 거쳤다. 그 벤더는 cid 를 알아내려고 구글 지도
      **페이지**를 먼저 여는데, 이 PC 에서 그 페이지가 429(`/sorry`)로 막히면 cid 를 못 찾았다며
      **예외 없이 빈 목록**을 준다 — 2026-09-10 부터 일본맛집 본문 사진 후보가 전부 대표 1장뿐이었다
      (2026-09-15 실측: 지도 페이지 429, 아래 두 API 는 200 으로 40장). cid 는 이미 있으니 페이지를 건너뛴다.
    """
    cid = place.get("cid") or ""
    if not cid:
        def to_cid():
            from elfsight_place import place_id_to_cid  # type: ignore
            return place_id_to_cid(place.get("place_id") or "")
        cid = _with_path(VENDOR_ELFSIGHT, to_cid)
    if not cid:
        return []

    import json
    import re
    from curl_cffi import requests  # type: ignore

    s = requests.Session(impersonate="chrome")
    s.headers.update({"accept": "*/*", "accept-language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7"})
    r = s.get(
        "https://www.google.com/httpservice/web/PrivateLocalSearchUiDataService/GetPlaceAttributeServiceBoqProxy",
        params={"reqpld": f'[null,[[["{cid}"]],[[21]],["local-photo-browser"],[null,null,[["ko-KR"],["KR"]]]]]'},
    )
    r.raise_for_status()
    data = json.loads(r.text.replace(")]}'\n", "").strip())
    # 카테고리 뽑는 식과 사진 주소 고르는 식은 koalamap 벤더(`__attachments`)와 같다.
    cats = re.findall(r"\['([\w/+]+=+)', \[.*?\], '([^']+)'\]", str(data))

    out: list[str] = []
    for cat_id, _ in cats:
        if len(out) >= cap:
            break
        req = [[["wTe8We",
                 f'["{cid}",null,null,"{cat_id}",null,null,null,null,null,null,"LU_PHOTO_GALLERY",'
                 f'["use_experimental_ng3_is3_score"],["{cid}"],0]',
                 None, "generic"]]]
        r = s.post("https://www.google.com/wizrpcui/_/WizRpcUi/data/batchexecute",
                   params={"rpcids": "wTe8We", "hl": "ko-KR"},
                   headers={"content-type": "application/x-www-form-urlencoded;charset=UTF-8"},
                   data=f"f.req={json.dumps(req)}")
        r.raise_for_status()
        found = re.findall(r'https://lh3\.googleusercontent\.com/[^"]+',
                           r.text.replace("\\u003d", "=").replace("\\", ""))
        groups: dict[str, list[tuple[str, str]]] = {}
        for u in found:
            if "=" in u:
                base, params = u.split("=", 1)
                key = base.split("/")[-1].split("-")[0] if "-" in base else base
                groups.setdefault(key, []).append((base, params))
        for urls in groups.values():
            if any(p.startswith("m") and p[1:].isdigit() for _, p in urls):
                continue    # 동영상
            u = re.sub(r"-w\d+-h\d+.*$", "", urls[0][0]) + "=s2048"
            if u not in out:
                out.append(u)
    return out[:cap]


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
    if not place.get("place_id"):
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


# 빈손일 때 다시 받기 전에 쉬는 시간(초). 횟수는 이 목록 길이 + 1 이다.
#
# **빈손은 가게를 타는 게 아니라 때를 탄다** (2026-09-30 실측). 리뷰가 30건씩 잘 오던
# 다섯 곳이 3분 뒤 한꺼번에 전부 0건이 됐다가, 2분 더 지나니 도로 30건이 왔다. 벤더가
# 잠깐씩 통째로 빈손을 주는 구간이 있다는 뜻이다. 5초·30초로는 그 구간을 못 넘긴다 —
# 같은 날 주제 확인에서 스무 곳 넘게 0건으로 떨어졌고, 그 가게들도 8분 뒤엔 24~30건이
# 그대로 왔다.
REVIEW_WAITS = (10, 60, 120)
REVIEW_TRIES = len(REVIEW_WAITS) + 1

# 빈손이 연달아 나오면 **다 같이 쉰다.** 한 구간에서 저마다 재시도를 태워 버리면
# 모두가 빈손으로 끝난다 — 그러면 멀쩡한 가게가 「쓸 장점 없음」으로 걸러지고,
# 주제까지 통째로 버려진다(2026-09-30 솔희 방 신고의 실제 경로).
COOLDOWN_AFTER = 3      # 연속 빈손 이만큼이면
COOLDOWN_SECS = 120.0   # 이만큼 쉬었다 다시 부른다
_empty_streak = 0
_cooldown_until = 0.0


async def _wait_out_cooldown() -> None:
    """벤더가 빈손 구간이면 그 구간이 지날 때까지 기다린다."""
    left = _cooldown_until - time.monotonic()
    if left > 0:
        await asyncio.sleep(left)


def _note_reviews(got: bool) -> None:
    global _empty_streak, _cooldown_until
    if got:
        _empty_streak = 0
        return
    _empty_streak += 1
    if _empty_streak >= COOLDOWN_AFTER and time.monotonic() >= _cooldown_until:
        _cooldown_until = time.monotonic() + COOLDOWN_SECS
        _empty_streak = 0
        logger.info(f"[place] 리뷰가 연달아 빈손 — {COOLDOWN_SECS:.0f}초 쉬었다 다시 받습니다")


async def reviews(place: dict[str, Any], cap: int = 30) -> list[dict[str, Any]]:
    """한 가게의 리뷰 본문. 실패하면 빈 목록이다 — 본문은 리뷰 없이도 나와야 한다.

    왜 필요한가 — 본문 넉 줄에 「그 가게만의 것」을 넣으라고 지침서가 요구하는데,
    `verify` 가 주는 이름·주소·평점·영업시간만으로는 어느 집에나 붙는 말밖에 못 쓴다.
    같은 주제로 8곳을 쓰면 여덟 장이 전부 비슷해진다(2026-09-07 사람 신고 — 삿포로 징기스칸).
    **웨이팅·예약·자리 수·간판 메뉴·값은 리뷰에만 있다.**

    빈손이면 조금 쉬었다 다시 받는다 (2026-09-22). 벤더가 오류 없이 빈 목록을 줄 때가 있다
    — 아구로 바이센 커피가 같은 place_id 로 0건 → 5초 뒤 13건. 리뷰가 없으면 본문 판정에서
    「쓸 장점이 없는 가게」로 빠지므로, 벤더가 어긋난 탓에 멀쩡한 가게를 잃지 않게 한다.

    **기다리는 시간을 5초에서 5·30초로 늘렸다** (2026-09-30 솔희 방 신고 — 「일본맛집2 본문
    내용 제대로 생성 안돼」). 그날 주제 확인에서 덴푸라·우동·야키토리 가게가 스무 곳 넘게
    한꺼번에 빈손으로 떨어져 「쓸 장점 없음」으로 걸러졌고, 남은 주제가 신오쿠보 한국 간식
    하나뿐이라 **일본 맛집이 아닌 캐러셀**이 나왔다. 떨어진 가게를 뒤에 다시 부르니 전부
    리뷰가 왔다 — 가게 탓이 아니라 벤더가 프로필을 만드는 데 걸리는 시간 탓이었다.
    """
    if not is_available() or not place.get("place_id"):
        return []
    try:
        for attempt in range(REVIEW_TRIES):
            if attempt:
                await asyncio.sleep(REVIEW_WAITS[attempt - 1])
            await _wait_out_cooldown()
            got = await asyncio.to_thread(_reviews_sync, place["place_id"], cap)
            _note_reviews(bool(got))
            if got:
                return got
        logger.info(f"[place] 리뷰 {REVIEW_TRIES}번 모두 빈손 — {place.get('name')}")
        return []
    except Exception as e:
        logger.warning(f"[place] 리뷰 실패 — {place.get('name')}: {type(e).__name__} {e}")
        return []


async def reviews_many(places: list[dict[str, Any]], cap: int = 30,
                       limit: int = 12) -> list[list[dict[str, Any]]]:
    """여러 가게의 리뷰를 받는다.

    ⚠ 실제로는 `_with_path` 자물쇠 때문에 한 줄로 선다(벤더 임포트가 프로세스 전역이라
      동시에 돌 수 없다). 8곳이면 30초 안팎이다 — 밤에 미리 도는 작업이라 괜찮다.

    동시 개수를 3 에서 12 로 올렸다(2026-09-30). 벤더를 더 세게 두드리려는 게 아니다 —
    호출은 위 자물쇠가 어차피 한 줄로 세운다. **빈손일 때 기다리는 시간이 겹치게** 하려는
    것이다. 셋씩이면 한 곳이 3분을 기다리는 동안 나머지가 줄을 서서 주제 하나에 30분이 든다.
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
