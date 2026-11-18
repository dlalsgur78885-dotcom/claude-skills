"""쇼핑 ② 「매장 하나 + 추천 제품」 — 체인 공식몰에서 제품·세금 포함 가격·공식 사진을 받는다.

2026-11-12 솔희 지시 — 「원클릭에 1개짜리도 넣어야될 것 같아」. 그때까지 ②③ 꼴은
**대화로만** 만들었다(`솔희_축_쇼핑.md` — 「제품 가격·공식 사진을 체인 사이트마다 받는 길이
원클릭에 없다」). 그 길을 여기서 만든다 — 공식몰 카테고리 목록 한 장에 제품명·세금 포함
가격·공식 사진이 다 있어서, 쟈란·구글 호텔 요금을 읽는 길(`jalan_lookup`·`google_price`)과
같은 방식으로 브라우저로 읽는다.

⚠ **쓸 수 있는 체인은 지금 마츠모토키요시 하나다** (2026-11-12 실측). 도큐핸즈(hands.net)·
로프트(loft.co.jp/store)·마츠키요는 전부 curl 로 403 이고, 브라우저로도 핸즈·로프트는 403 이
그대로였다. 마츠키요만 `patchright`(크롬 채널)로 200 이 떴다 — 체인을 늘릴 때는 먼저
`CHAINS` 에 넣고 **실제로 열리는지 확인**하고 나서 지침서에 적는다.

가격은 목록 타일의 `data-datalayer` 에 든 `price` 다 — 화면에 「1,237円（税込）」로 찍히는
그 값이고, 本体가(1,125円)가 아니다. 지침서가 요구하는 **세금 포함 가격**이 이것이다
(`쇼핑_3-3단계_본문.md` — 「가격은 제품마다 출처가 다르다 … 못 찾은 제품은 뺀다」).
"""

from __future__ import annotations

import asyncio
import html
import io
import logging
import re
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36")

# 공식몰에서 제품을 읽을 수 있는 체인. `cats` 는 **여행객이 살 만한 칸만** 골라 둔 것이다 —
# 마츠키요 카테고리 006(화장지·세제)·007(간병)·008(기저귀)·009(생수)는 한국 여행객 쇼핑
# 캐러셀에 쓸 것이 아니라 뺐다(2026-11-12 아홉 칸을 다 열어 보고 고름).
#
# 칸(`cats`)은 `(번호, 이름, 주제에서 찾을 말)` 이다 — 주제의 **분류**와 맞는 칸만 읽는다
# (2026-11-18 — ② 가 회차마다 다섯 개가 되면서 「색조 화장품」 주제에 상비약이 섞이면 안 된다).
# 맞는 말이 없으면 칸을 다 돌며 섞는다(옛 동작).
CHAINS: dict[str, dict[str, Any]] = {
    "마츠모토키요시": {
        "aliases": ("마츠모토키요시", "마쓰모토키요시", "마츠키요", "마쓰키요", "matsukiyo"),
        "base": "https://www.matsukiyococokara-online.com",
        "cats": (("001", "상비약", ("의약품", "상비약", "감기", "진통")),
                 ("002", "건강·영양제", ("영양제", "건강", "비타민")),
                 ("004", "스킨케어·바디", ("기초 화장품", "기초화장품", "스킨케어", "바디", "보습")),
                 ("005", "메이크업", ("색조", "메이크업", "립", "화장품"))),
    },
    # 돈키호테 PB(情熱価格) 제품 소개 — **가격이 없다.** 점포마다 값이 달라 공식가를 안 낸다
    # (2026-11-18 `j-kakaku/product/list.php` 를 열어 확인 — 목록·상세 어디에도 엔 표시가 없다).
    # 그래서 가격 칸 대신 **한 줄 설명**을 넣는다(2026-11-18 솔희 지시 — 「가격 칸을 빼고 제품
    # 이름+한 줄 설명으로 넣어줘」). 정적 HTML 이라 브라우저 없이 읽는다(`kind: "html"`).
    # ⚠ PB 에 **의약품 칸은 없다** — 「돈키호테, 의약품」 주제는 내지 마라(마츠키요 상비약으로).
    "돈키호테": {
        "aliases": ("돈키호테", "돈키", "ドンキ", "donki"),
        "base": "https://www.donki.com/j-kakaku",
        "no_price": True,
        "kind": "html",
        "cats": (("24", "미용·건강", ("색조", "기초 화장품", "기초화장품", "화장품", "미용",
                                   "스킨케어", "메이크업", "건강")),
                 ("12", "과자", ("간식", "과자", "디저트", "주전부리")),
                 ("11", "위생용품", ("위생", "생활꿀템", "생활")),
                 ("15", "가정잡화", ("잡화", "생활꿀템", "생활", "살림")),
                 ("23", "주방잡화", ("주방", "키친", "생활꿀템")),
                 ("10", "음료·주류", ("음료", "술", "주류", "마실"))),
    },
}

_CAT_URL = "{base}/store/catalog/category/view/categories/{cid}/"
# 돈키 PB 목록·상세 — 정적 HTML 이다.
_DONKI_LIST = "{base}/product/list.php?cid={cid}"
_NAV_MS = 60_000
_SETTLE_MS = 3_500
# 한 칸에서 앞에서부터 몇 개까지 볼까 — 품목이 겹치면 뒤로 밀리니 넉넉히 본다.
_PER_CAT = 10
# 상품 페이지(공식 사진·소개)를 한 번에 몇 장 열까.
_CONC = 3

# 목록 타일 — `data-datalayer` 에 제품 번호(JAN)·이름·세금 포함 가격이 json 으로 들어 있다.
_TILES_JS = r"""() => {
  const out = [];
  document.querySelectorAll('[data-datalayer]').forEach(el => {
    let d = null;
    try { d = JSON.parse(el.getAttribute('data-datalayer')); } catch (e) { return; }
    if (!d || !d.item_id || !d.item_name) return;
    const a = el.querySelector('a[href*="/catalog/product/view/id/"]');
    const img = el.querySelector('img');
    out.push({
      jan: String(d.item_id),
      name_ja: String(d.item_name),
      price: Number(d.price) || 0,
      url: a ? a.href.split('?')[0] : '',
      image: img ? (img.currentSrc || img.src || '') : ''
    });
  });
  const seen = new Set();
  return out.filter(x => x.jan && x.price > 0 && !seen.has(x.jan) && seen.add(x.jan));
}"""

# 상품 페이지에서 받는 것 — 공식 사진과 한 줄 소개(meta description).
# ⚠ `og:image` 는 쓰지 않는다 — 어느 상품이든 마츠키요 **로고 그림**이 들어 있다
# (2026-11-12 실측 `media/wysiwyg/common/img_ogp.png`). 상품 사진은 본문 `img` 중
# `media/catalog` 주소를 쓴다.
_DETAIL_JS = r"""() => ({
  images: Array.from(document.images).map(i => i.currentSrc || i.src)
            .filter(u => u && u.includes('media/catalog/product/')).slice(0, 12),
  text: document.body.innerText
})"""

# 공식 사진인지 — 목록 타일의 img 는 느리게 불러오는 칸이 많아 아이콘(placeholder)이 들어온다.
_REAL_IMG = "/media/catalog/product/"


def chain_of(topic: str) -> str | None:
    """주제가 ② 「매장 하나」 꼴인가 — 공식몰을 읽을 수 있는 체인 이름이 들어 있으면 그 체인.

    ② 주제는 `[매장 이름] + [키워드]` 다(`쇼핑_1단계_주제후보.md`). 지역을 안 붙이는 꼴이라
    주제 맨 앞이 매장 이름이지만, 「마츠키요」처럼 줄여 쓸 수 있어 들어 있는지로 본다.
    """
    t = (topic or "").replace(" ", "").lower()
    if not t:
        return None
    for key, conf in CHAINS.items():
        if any(a.replace(" ", "").lower() in t for a in conf["aliases"]):
            return key
    return None


def _browser_mod() -> Any:
    """봇 막이를 지나갈 브라우저 — `patchright` 가 있으면 그것, 없으면 평범한 playwright.

    2026-11-12 실측 — 평범한 playwright(크로미움)로는 마츠키요도 403 이었고,
    `patchright` + 크롬 채널에서 200 이 떴다.
    """
    try:
        from patchright.async_api import async_playwright   # type: ignore
        return async_playwright
    except Exception:
        from playwright.async_api import async_playwright   # type: ignore
        logger.warning("[shop] patchright 가 없어 playwright 로 엽니다 — 막힐 수 있습니다")
        return async_playwright


def cats_for(conf: dict[str, Any], topic: str) -> tuple:
    """주제의 **분류**와 맞는 칸만. 맞는 칸이 없으면 전부(옛 동작).

    ② 주제는 `[매장 이름], [분류]` 다 — 「마츠모토키요시, 색조 화장품」이면 메이크업 칸만 읽어야
    낱장이 주제와 맞는다(2026-11-18 ② 가 회차마다 다섯 개가 되면서 생긴 자리).
    """
    t = (topic or "").replace(" ", "")
    hit = tuple(c for c in conf["cats"]
                if any(w.replace(" ", "") in t for w in (c[2] if len(c) > 2 else ())))
    return hit or tuple(conf["cats"])


async def pick(chain: str, want: int, exclude: set[str] | None = None,
               topic: str = "") -> list[dict[str, Any]]:
    """그 체인 공식몰에서 제품 `want` 개 — 이름(일본어)·세금 포함 가격·공식 사진·상품 주소.

    칸(`cats`)을 **돌아가며 한 개씩** 집는다 — 한 칸에서 일곱 개를 집으면 전부 스킨케어가
    되어 품목이 겹친다(지침서 「품목이 겹치지 않게」 · 13회차 「치즈는 셋까지」와 같은 자리).
    주제에 분류가 적혀 있으면 **그 칸만** 읽는다(`cats_for`).
    이미 나간 제품(`exclude` — `쇼핑_쓴가게.md` 의 번호)은 건너뛴다.

    못 받으면 **빈 목록**이다 — 부르는 쪽이 주제를 접는다(`make_product_body`).
    """
    conf = CHAINS.get(chain)
    if not conf:
        return []
    skip = {str(x) for x in (exclude or set())}
    if conf.get("kind") == "html":
        return await _pick_html(conf, want, skip, topic)
    per_cat: list[list[dict[str, Any]]] = []
    picked: list[dict[str, Any]] = []

    async_playwright = _browser_mod()
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True, channel="chrome")
        try:
            ctx = await browser.new_context(user_agent=UA, locale="ja-JP",
                                            viewport={"width": 1400, "height": 2400})
            try:
                for cid, label, *_ in cats_for(conf, topic):
                    rows = await _category(ctx, conf["base"], cid, label)
                    per_cat.append([r for r in rows if r["jan"] not in skip][:_PER_CAT])
                # 칸을 돌아가며 한 개씩 — 칸이 넷이면 7개가 2·2·2·1 로 섞인다.
                for i in range(_PER_CAT):
                    for rows in per_cat:
                        if i < len(rows) and len(picked) < want:
                            picked.append(rows[i])
                    if len(picked) >= want:
                        break
                await _fill_details(ctx, picked)
                # 공식 사진은 **브라우저 안에서** 받는다 — 같은 주소를 httpx 로 받으면 403 이다
                # (2026-11-12 실측 · CDN 이 브라우저 아닌 요청을 막는다).
                await _fill_photos(ctx, picked)
            finally:
                await ctx.close()
        finally:
            await browser.close()

    good = [p for p in picked if p.get("photo")]
    if len(good) < len(picked):
        logger.info(f"[shop] 공식 사진을 못 받은 제품 {len(picked) - len(good)}개를 뺐습니다")
    logger.info(f"[shop] {chain} 공식몰에서 제품 {len(good)}개 — "
                + " · ".join(f"{p['name_ja'][:14]} ¥{p['price']:,}" for p in good[:7]))
    return good


# ── 정적 HTML 공식몰(돈키호테 PB) — 브라우저 없이 읽는다 ───────────────────────────
#
# 목록 타일은 `<a href="./detail.php?item=…"><img src="…-sub.jpg" alt="제품명">` 하나뿐이고
# **가격이 없다.** 상품 페이지에 「ココに情熱！」(제조사가 쓴 소개)·내용량·JAN 이 있다.
_DONKI_TILE = re.compile(
    r'href="\./detail\.php\?item=(\d+)"[^>]*>\s*<img src="([^"]+)"[^>]*alt="([^"]*)"', re.S)
_DONKI_ABOUT = re.compile(r"ココに情熱！(.+?)商品概要", re.S)
_DONKI_JAN = re.compile(r"(?<!\d)(\d{13})(?!\d)")
_DONKI_SIZE = re.compile(r"内容量[：:]\s*([^" + chr(10) + r"■]{1,40})")
# 목록 타일 사진은 150×150 썸네일이라 낱장 배경으로 못 쓴다 — `-main` 쪽을 받는다.
_MIN_PX = 400


def _get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "ja-JP"})
    with urllib.request.urlopen(req, timeout=30) as res:
        return res.read()


def _plain(raw: str) -> str:
    raw = re.sub(r"<script.*?</script>|<style.*?</style>", " ", raw, flags=re.S)
    # `&middot;` 같은 실체 참조를 글자로 되돌린다 — 안 풀면 공식 소개에 그대로 실려 간다.
    return html.unescape(re.sub(r"[ " + chr(9) + r"]+", " ", re.sub(r"<[^>]+>", chr(10), raw)))


async def _pick_html(conf: dict[str, Any], want: int, skip: set[str],
                     topic: str) -> list[dict[str, Any]]:
    """정적 HTML 공식몰 — **가격 없이** 이름·공식 사진·공식 소개만 받는다(돈키호테 PB)."""
    per_cat: list[list[dict[str, Any]]] = []
    for cid, label, *_ in cats_for(conf, topic):
        url = _DONKI_LIST.format(base=conf["base"], cid=cid)
        try:
            page = (await asyncio.to_thread(_get, url)).decode("utf-8", errors="replace")
        except Exception as e:
            logger.warning(f"[shop] 칸 {cid}({label}) 를 못 읽었습니다 — {type(e).__name__} {e}")
            continue
        rows = [{"jan": item, "name_ja": html.unescape(name).strip(), "category": label,
                 "image": img.replace("-sub.", "-main."),
                 "url": f"{conf['base']}/product/detail.php?item={item}"}
                for item, img, name in _DONKI_TILE.findall(page)
                if item not in skip and name.strip()]
        per_cat.append(rows[:_PER_CAT])

    picked: list[dict[str, Any]] = []
    for i in range(_PER_CAT):
        for rows in per_cat:
            if i < len(rows) and len(picked) < want:
                picked.append(rows[i])
        if len(picked) >= want:
            break
    gate = asyncio.Semaphore(_CONC)

    async def one(it: dict[str, Any]) -> None:
        async with gate:
            await _html_detail(it)

    await asyncio.gather(*(one(p) for p in picked))
    good = [p for p in picked if p.get("photo")]
    if len(good) < len(picked):
        logger.info(f"[shop] 공식 사진을 못 받은 제품 {len(picked) - len(good)}개를 뺐습니다")
    logger.info(f"[shop] 공식몰에서 제품 {len(good)}개(가격 없는 체인) — "
                + " · ".join(f"{p['name_ja'][:14]}" for p in good[:7]))
    return good


async def _html_detail(it: dict[str, Any]) -> None:
    """상품 페이지에서 공식 소개·용량을 받고, 공식 사진을 내려받는다."""
    from PIL import Image

    try:
        text = _plain((await asyncio.to_thread(_get, it["url"])).decode("utf-8", errors="replace"))
        about = _DONKI_ABOUT.search(text)
        it["about"] = re.sub(r"\s+", " ", about.group(1)).strip()[:400] if about else ""
        size = _DONKI_SIZE.search(text)
        if size:
            it["size"] = size.group(1).strip()
    except Exception as e:
        logger.warning(f"[shop] 상품 페이지 실패 — {it.get('name_ja')}: {type(e).__name__} {e}")
    for url in (it["image"], it["image"].replace("-main.", "-sub.")):
        try:
            blob = await asyncio.to_thread(_get, url)
            if min(Image.open(io.BytesIO(blob)).size) >= _MIN_PX:
                it["photo"], it["image"] = blob, url
                return
        except Exception:
            continue
    logger.warning(f"[shop] 쓸 만한 공식 사진이 없습니다 — {it.get('name_ja')}")


async def _category(ctx: Any, base: str, cid: str, label: str) -> list[dict[str, Any]]:
    """카테고리 한 칸의 제품 타일. 한 칸이 막히면 **그 칸만** 빈손으로 둔다."""
    page = await ctx.new_page()
    try:
        res = await page.goto(_CAT_URL.format(base=base, cid=cid),
                              timeout=_NAV_MS, wait_until="domcontentloaded")
        await page.wait_for_timeout(_SETTLE_MS)
        if res and res.status >= 400:
            logger.warning(f"[shop] 카테고리 {cid}({label}) 가 {res.status} 입니다")
            return []
        rows = await page.evaluate(_TILES_JS)
        for r in rows:
            r["category"] = label
        return [r for r in rows if isinstance(r, dict)]
    except Exception as e:
        logger.warning(f"[shop] 카테고리 {cid}({label}) 를 못 읽었습니다 — {type(e).__name__} {e}")
        return []
    finally:
        await page.close()


# 상품 페이지 글에서 **제조사가 쓴 소개**와 브랜드만 떼어 낸다. 리뷰·배송 안내는 쓰지 않는다.
_ABOUT_RE = re.compile(r"商品詳細" + chr(10) + r"(.+?)" + chr(10) +
                       r"(?:商品情報|使用上の注意|成分|レビュー|あわせて|この商品)", re.S)
# ⚠ 맨 앞 「ブランド」 는 **왼쪽 메뉴**다(그 아래가 「マイストア」). 제품의 브랜드는
# 상품 정보 칸의 「メーカー … ブランド …」 자리다.
_BRAND_RE = re.compile(r"メーカー" + chr(10) + r".+?" + chr(10) + r"ブランド" + chr(10) + r"(.+?)" + chr(10))


def _norm(text: str) -> str:
    """빈 줄을 걷어낸 글 — 칸 이름과 값 사이에 빈 줄이 끼어 있다(「ブランド」 아래가 그렇다)."""
    return re.sub(chr(10) + r"[ " + chr(9) + r"]*" + chr(10) + "+", chr(10), text or "")


def _about_of(text: str) -> str:
    m = _ABOUT_RE.search(_norm(text))
    body = m.group(1) if m else ""
    body = re.sub(r"[ 	]+", " ", body).strip()
    return body[:400]


def _brand_of(text: str) -> str:
    m = _BRAND_RE.search(_norm(text))
    return (m.group(1).strip()[:40] if m else "")


async def _fill_details(ctx: Any, items: list[dict[str, Any]]) -> None:
    """제품마다 공식 사진과 한 줄 소개를 채운다 — 목록 타일 사진이 아이콘인 칸이 많다."""
    gate = asyncio.Semaphore(_CONC)

    async def one(it: dict[str, Any]) -> None:
        if _REAL_IMG in str(it.get("image") or "") and it.get("about"):
            return
        if not it.get("url"):
            return
        async with gate:
            page = await ctx.new_page()
            try:
                await page.goto(it["url"], timeout=_NAV_MS, wait_until="domcontentloaded")
                # ⚠ 제조사 소개(「商品詳細」)는 **아래로 내려야** 그려진다(2026-11-12 실측) —
                # 안 내리면 meta description 의 「…の詳細ページです」 같은 빈 말밖에 안 남는다.
                for _ in range(5):
                    await page.mouse.wheel(0, 2500)
                    await page.wait_for_timeout(700)
                await page.wait_for_timeout(1500)
                got = await page.evaluate(_DETAIL_JS)
            except Exception as e:
                logger.warning(f"[shop] 상품 페이지 실패 — {it.get('name_ja')}: {type(e).__name__} {e}")
                return
            finally:
                await page.close()
        # 목록 타일 사진이 이미 공식 사진이면 그대로 둔다. 아니면 상품 페이지 사진 중
        # **`<제품번호>_01_`** 를 고른다 — 그것이 정면 컷이고, 뒤 번호는 포장 뒷면·성분표다
        # (2026-11-12 — `_02` 를 집어 거꾸로 선 뒷면 라벨이 낱장 배경으로 나왔다).
        imgs = [str(u) for u in ((got or {}).get("images") or [])]
        if _REAL_IMG not in str(it.get("image") or "") and imgs:
            jan = str(it.get("jan") or "")
            it["image"] = next((u for u in imgs if f"{jan}_01" in u), imgs[0])
        text = str((got or {}).get("text") or "")
        it["about"] = _about_of(text)
        it["brand"] = _brand_of(text)

    await asyncio.gather(*(one(it) for it in items))


async def _fill_photos(ctx: Any, items: list[dict[str, Any]]) -> None:
    """공식 사진을 내려받아 `photo`(바이트)에 담는다 — 못 받은 제품은 비워 둔다."""
    gate = asyncio.Semaphore(_CONC)

    async def one(it: dict[str, Any]) -> None:
        url = str(it.get("image") or "")
        if _REAL_IMG not in url:
            return
        # ⚠ 사진 주소는 **낱장을 열어서** 받는다 — `request.get` 은 리퍼러를 붙여도 403 이고
        # (2026-11-12 실측) 페이지로 열면 200 이다.
        async with gate:
            page = await ctx.new_page()
            try:
                res = await page.goto(url, timeout=_NAV_MS)
                if res and res.ok:
                    it["photo"] = await res.body()
                else:
                    logger.warning(f"[shop] 사진 {res.status if res else '없음'} — {it.get('name_ja')}")
            except Exception as e:
                logger.warning(f"[shop] 사진 못 받음 — {it.get('name_ja')}: {type(e).__name__} {e}")
            finally:
                await page.close()

    await asyncio.gather(*(one(it) for it in items))


# ── 본문 배경 — 공식 사진 그대로 두고 **여백만 이어** 4:5 로 만든다 ──────────────
#
# 2026-11-04·11-09 회차에서 정한 길이다(`쇼핑_3-2단계_썸네일이미지.md` — 「공식 제품
# 사진 그대로 + 여백만 생성」). 제품을 다시 그리면 포장·글자를 지어낸다.
# 순백 배경은 **따뜻한 베이지**로 간다(14회차 확정색 A) — 흰 낱장에 흰 배경이 겹치면
# 제품이 떠 보인다.
_BEIGE = (243, 233, 221)
_WHITE_AT = 245
# 배경으로 볼 색 차이 — 돈키 PB 사진은 옅은 회백색이라 순백 기준으로는 안 걸린다.
_BG_TOL = 18
# 회차 배경색 — 제품에서 뽑은 색조를 **연하게**(채도 낮게·밝게) 깐다. 진하면 글이 묻힌다.
_BG_SAT, _BG_VAL = 26, 243
_HUE_BAND = 15
# 제품이 놓이는 칸 — 글 칸(y 981~)과 표지 누끼 띠(y 60~930)를 피해 위쪽에 둔다.
_BOX = (760, 820)
_BOX_CENTER = (540, 495)


def _bg_alpha(src: Any, bg: tuple[int, int, int]) -> Any:
    """가장자리에서 **이어진** 배경색만 지운 알파 — 제품 안쪽 흰 칸은 남긴다.

    테두리만 네모로 자르면 제품이 네모를 안 채우는 사진(봉투 + 막대처럼 둘로 떨어진 컷)은
    그 사이 흰 바탕이 베이지 낱장 위에 흰 네모로 남는다(2026-11-18 솔희 지적 — 돈키
    「もっちり綿棒モチペタ」). 그래서 색만 보고 다 지우지 않고, **사진 가장자리에서 이어진
    덩어리만** 배경으로 본다 — 포장 안쪽 흰 칸에 구멍이 나면 안 된다.
    """
    import cv2
    import numpy as np

    arr = np.asarray(src, dtype=np.int16)
    bgish = (np.abs(arr - np.array(bg, dtype=np.int16)).max(axis=2) <= _BG_TOL).astype(np.uint8)
    # 1px 테두리를 배경으로 덧대고 거기서 이어진 덩어리를 고른다.
    pad = np.zeros((bgish.shape[0] + 2, bgish.shape[1] + 2), np.uint8)
    pad[1:-1, 1:-1] = bgish
    pad[0, :] = pad[-1, :] = pad[:, 0] = pad[:, -1] = 1
    _, lab = cv2.connectedComponents(pad, connectivity=4)
    outer = lab[1:-1, 1:-1] == lab[0, 0]
    alpha = np.where(outer, 0, 255).astype(np.uint8)
    # 경계 한 줄을 흐려 톱니를 없앤다.
    return cv2.GaussianBlur(alpha, (3, 3), 0)


def _product(blob: bytes) -> tuple[Any, Any, tuple[int, int, int]]:
    """사진 한 장 → (RGB 사진, 제품만 남긴 알파, 그 사진의 바탕색)."""
    from PIL import Image

    raw = Image.open(io.BytesIO(blob))
    src = raw.convert("RGB")
    if "A" in raw.getbands():
        # 투명 PNG(맥도날드 공식 컷)는 알파가 이미 정확하다 — 다시 잴 것 없다.
        return src, raw.convert("RGBA").getchannel("A"), (255, 255, 255)
    # 배경색은 네 귀퉁이에서 받는다 — 공식 사진은 대개 단색 배경이다.
    w, h = src.size
    corners = [src.getpixel(p) for p in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1))]
    bg = tuple(sum(c[i] for c in corners) // len(corners) for i in range(3))
    return src, Image.fromarray(_bg_alpha(src, bg)), bg


def sheet_bg(blobs: list[bytes]) -> tuple[int, int, int]:
    """그 회차 제품들에서 뽑은 **낱장 배경색 하나** — 제품 색조를 연하게 깐 색.

    2026-11-18 솔희 지시 — 「회차당 한 색으로, 제품에 어울리게」. 낱장마다 다른 색을 깔면
    회차 통일감이 깨져서, 일곱 장에서 **같이** 뽑아 한 색으로 쓴다. 회색·검정뿐인 회차는
    뽑을 색조가 없으니 베이지(14회차 확정색 A)로 둔다.
    """
    import cv2
    import numpy as np

    hist = np.zeros(180, dtype=np.float64)
    for blob in blobs:
        try:
            src, alpha, _bg = _product(blob)
        except Exception:
            continue
        mask = np.asarray(alpha) > 128
        if not mask.any():
            continue
        hsv = cv2.cvtColor(np.asarray(src), cv2.COLOR_RGB2HSV)
        hue, sat, val = hsv[..., 0][mask], hsv[..., 1][mask], hsv[..., 2][mask]
        # 무채색(포장 흰 칸·검은 글자)은 색조가 없다 — 또렷한 색만 센다.
        keep = (sat > 60) & (val > 60)
        if keep.sum() < 50:
            continue
        # 사진마다 무게를 같게 — 큰 사진이 회차 색을 혼자 정하면 안 된다.
        np.add.at(hist, hue[keep], sat[keep].astype(np.float64) / 255 / int(keep.sum()))
    if hist.sum() <= 0:
        return _BEIGE
    # 이웃한 색조끼리 묶어 본다(색조는 원형이라 세 번 이어 붙여 넘긴다).
    band = np.convolve(np.tile(hist, 3), np.ones(_HUE_BAND) / _HUE_BAND, "same")[180:360]
    hue = int(np.argmax(band))
    rgb = cv2.cvtColor(np.uint8([[[hue, _BG_SAT, _BG_VAL]]]), cv2.COLOR_HSV2RGB)[0][0]
    return (int(rgb[0]), int(rgb[1]), int(rgb[2]))


def padded_png(blob: bytes, size: tuple[int, int] = (1080, 1350),
               sheet: tuple[int, int, int] | None = None) -> bytes:
    """공식 제품 사진을 4:5 낱장 배경으로 — 제품은 그대로, 배경만 낱장 색으로 간다.

    `sheet` 는 회차 공통 배경색(`sheet_bg`)이다. 안 주면 베이지로 간다.
    """
    from PIL import Image

    src, alpha, src_bg = _product(blob)
    # 바탕을 지운 사진만 회차 색으로 간다 — 배경이 사진인 컷은 그 바탕색을 그대로 둬야
    # 네모 테두리가 안 드러난다.
    bg = (sheet or _BEIGE) if min(src_bg) >= _WHITE_AT else src_bg
    # 제품이 든 자리만 잘라 낸다 — 배경을 지우고 난 뒤라 빈 여백이 안 따라온다.
    box = alpha.getbbox()
    if box:
        src, alpha = src.crop(box), alpha.crop(box)
    else:
        # 사진이 통째로 배경색으로 읽힌 꼴 — 지우지 말고 사진을 그대로 쓴다(빈 낱장 방지).
        alpha = Image.new("L", src.size, 255)
    w, h = src.size
    scale = min(_BOX[0] / w, _BOX[1] / h)
    wh = (max(1, int(w * scale)), max(1, int(h * scale)))
    src, alpha = src.resize(wh, Image.LANCZOS), alpha.resize(wh, Image.LANCZOS)
    canvas = Image.new("RGB", size, bg)
    canvas.paste(src, (_BOX_CENTER[0] - wh[0] // 2, _BOX_CENTER[1] - wh[1] // 2), alpha)
    out = io.BytesIO()
    canvas.save(out, format="PNG")
    return out.getvalue()


def facts_block(items: list[dict[str, Any]]) -> str:
    """문구 모델에게 넘길 **확인된 사실만** — 이름·가격·칸·공식 소개.

    가격이 없는 체인(돈키호테 PB)은 가격 줄을 빼고 용량을 싣는다 — 없는 값을 0엔으로 넘기면
    모델이 그 숫자를 글에 쓴다.
    """
    rows = []
    for n, it in enumerate(items, 1):
        about = re.sub(r"\s+", " ", str(it.get("about") or "")).strip()
        rows.append(chr(10).join([
            f"[{n}] {it.get('name_ja')}",
            *( [f"- 가격(세금 포함): {int(it['price']):,}엔"] if it.get("price") else [] ),
            *( [f"- 용량: {it.get('size')}"] if it.get("size") else [] ),
            f"- 칸: {it.get('category')}",
            *( [f"- 브랜드: {it.get('brand')}"] if it.get("brand") else [] ),
            *( [f"- 공식 소개: {about[:200]}"] if about else [] ),
        ]))
    return (chr(10) * 2).join(rows)
