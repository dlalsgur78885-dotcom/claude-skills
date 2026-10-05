"""훅 창고 — 벤치마크 게시물 중 반응 좋았던 표지 훅을 모아 두고, 훅을 지을 때 예시로 넘긴다.

## 왜 필요한가

2026-09-29 까지 훅은 **주제와 지침서만 보고** 지었다. 남의 계정에서 실제로 먹힌 표지를
하나도 안 봤다. 수집 게시물은 서버에 9천 건 넘게 쌓여 있는데, 표지 글자(OCR)는
「쓸게요」를 누른 것에만 있어 그대로는 못 쓴다.

## 어떻게 모으나

1. 서버 `/posts/?category=…` 로 그 축 카테고리의 캐러셀 게시물 목록을 받는다(축 주인 계정).
2. 좋아요 순으로, 아직 안 읽은 것만 몇 건씩 골라
3. Koalagram(`app/vendor/koalagram`)으로 게시물을 **다시** 받아 표지 이미지를 내려받고
4. codex 에게 표지를 보여 줘 훅 글자만 옮겨 적게 한다.

**천천히 돈다**(2026-09-29 사람 — 「속도 천천히 해도 된다」). 인스타에 몰아서 요청하면
막힌다. 한 번에 `MAX_NEW` 건, 건마다 `PAUSE_SECONDS` 쉰다.

창고는 이 PC 의 `backend/data/hook_bank.json` 이다(일꾼도 이 PC 에서 돈다).
"""

import asyncio
import json
import logging
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

logger = logging.getLogger(__name__)

BANK_PATH = Path(__file__).resolve().parents[2] / "data" / "hook_bank.json"

# 한 번 돌 때 새로 읽는 게시물 수 · 게시물 사이 쉬는 시간
MAX_NEW = 20
PAUSE_SECONDS = 8
# 읽기에 실패한 게시물은 다음 번에 다시 본다 — 이만큼 실패하면 그만둔다(내려받기가 가끔 끊긴다)
MAX_TRIES = 3
# 훅을 지을 때 넘기는 예시 수
EXAMPLES = 15
# 서버 목록 한 쪽의 크기(서버 상한이 200)
PAGE = 200

# 표지 글자 읽기는 **옮겨 적기**다 — 가벼운 모델 자리다(studio_steps.LIGHT_MODEL 과 같은 이유).
READ_MODEL = "codex-luna"
READ_SCHEMA = {
    "type": "object",
    "properties": {"hook": {"type": "string"}},
    "required": ["hook"],
    "additionalProperties": False,
}
READ_PROMPT = (
    "이 인스타그램 카드뉴스 표지에 **가장 크게 적힌 제목(훅) 문구**만 줄바꿈 그대로 옮겨 적어라. "
    "작은 부제·계정명·로고·지도 지명은 빼라. 글자를 고치거나 보태지 마라. "
    "표지에 제목 글자가 없으면 빈 문자열을 낸다."
)

_lock = asyncio.Lock()


def _load() -> dict[str, Any]:
    try:
        return json.loads(BANK_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {"posts": {}}


def _save(bank: dict[str, Any]) -> None:
    BANK_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = BANK_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(bank, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(BANK_PATH)


async def _list_posts(category: str, account: str | None) -> list[dict[str, Any]]:
    """그 카테고리의 캐러셀 게시물 전부(서버가 만료된 것은 빼고 준다)."""
    from app.services import studio_remote

    posts: list[dict[str, Any]] = []
    offset = 0
    while True:
        page = await studio_remote.call(
            f"/posts/?category={quote(category)}&is_video=false&min_slides=2"
            f"&limit={PAGE}&offset={offset}",
            method="GET", account=account)
        posts += page or []
        if len(page or []) < PAGE:
            return posts
        offset += PAGE


def _fetch_cover(url: str, dest: Path) -> int:
    """게시물을 다시 받아 표지를 `dest` 에 저장하고 지금 좋아요 수를 돌려준다."""
    from curl_cffi import requests

    from app.vendor.koalagram import Koalagram

    media = Koalagram().fetch_sync(url)
    if not media.image_urls:
        raise RuntimeError("표지 이미지가 없습니다")
    r = requests.get(media.image_urls[0], impersonate="chrome", timeout=90)
    r.raise_for_status()
    dest.write_bytes(r.content)
    return int(media.like_count or 0)


async def _read_hook(image: Path) -> str:
    from app.agents.llm_client import MODELS, _call_codex_cli

    raw = await _call_codex_cli(READ_PROMPT, model=MODELS[READ_MODEL]["cli_model"],
                                json_schema=READ_SCHEMA, images=[str(image)], timeout=120)
    return str(json.loads(raw).get("hook") or "").strip()


async def refresh(category: str, account: str | None = None,
                  extra_urls: list[str] | None = None) -> int:
    """아직 안 읽은 게시물을 좋아요 순으로 `MAX_NEW` 건 읽어 창고에 넣는다. 넣은 수를 돌려준다.

    `extra_urls` — 서버 목록에 없는 주소(만료된 옛 게시물)를 한 번에 채울 때 쓴다.
    """
    async with _lock:
        bank = _load()
        known = bank["posts"]
        listed = await _list_posts(category, account)
        candidates = [{"post_url": p["post_url"], "like_count": p.get("like_count", 0)}
                      for p in listed]
        candidates += [{"post_url": u, "like_count": 0} for u in extra_urls or []]
        def pending(url: str) -> bool:
            old = known.get(url)
            return old is None or (bool(old.get("error")) and int(old.get("tries") or 1) < MAX_TRIES)

        todo = sorted((c for c in candidates if pending(c["post_url"])),
                      key=lambda c: -int(c["like_count"] or 0))[:MAX_NEW]

        added = 0
        with tempfile.TemporaryDirectory(prefix="hookbank_") as tmp:
            for i, c in enumerate(todo):
                if i:
                    await asyncio.sleep(PAUSE_SECONDS)
                url = c["post_url"]
                entry: dict[str, Any] = {"category": category, "likes": int(c["like_count"] or 0),
                                         "hook": "", "read_at": datetime.now().isoformat(timespec="seconds"),
                                         "tries": int((known.get(url) or {}).get("tries") or 0) + 1}
                try:
                    cover = Path(tmp) / f"{i}.jpg"
                    entry["likes"] = await asyncio.to_thread(_fetch_cover, url, cover) or entry["likes"]
                    entry["hook"] = await _read_hook(cover)
                except Exception as e:
                    # 실패도 적어 둔다 — 안 적으면 다음 번에 같은 게시물에서 또 막힌다.
                    entry["error"] = str(e)[:200]
                    logger.warning(f"[hook-bank] {url} 읽기 실패: {entry['error']}")
                known[url] = entry
                added += bool(entry["hook"])
                _save(bank)   # 건마다 저장한다 — 중간에 멈춰도 읽은 것은 남는다
        if todo:
            logger.info(f"[hook-bank] 「{category}」 {len(todo)}건 확인, 훅 {added}개 추가")
        return added


def examples(category: str, n: int = EXAMPLES) -> str:
    """훅 프롬프트에 붙일 예시 블록. 창고가 비었으면 빈 문자열."""
    if not category:
        return ""
    rows = [p for p in _load()["posts"].values()
            if p.get("category") == category and p.get("hook")]
    rows.sort(key=lambda p: -int(p.get("likes") or 0))
    if not rows:
        return ""
    lines = [f"- (좋아요 {p['likes']:,}) " + p["hook"].replace("\n", " / ") for p in rows[:n]]
    return "\n".join([
        "===== 참고 — 비슷한 계정에서 반응이 좋았던 표지 훅 =====",
        "문장을 베끼지 마라. 무엇이 눈길을 끌었는지(숫자·반전·말투·길이)만 참고하고, "
        "지침서의 규칙이 이 예시보다 우선한다.",
        *lines,
    ])
