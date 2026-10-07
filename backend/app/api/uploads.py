"""캐러셀 → 인스타 업로드 — instagram-reel-uploader 의 외부 사이트 API(v1)로 넘긴다.

2026-10-06 트립앤라이프 피드백: 에디터 [업로드] 로 바로 게시·예약하고, 「내 작업」 에서
예약을 보고 고치고 취소하게. 업로더에 같은 기능(캐러셀 게시 · 예약 목록)이 이미 있어서
여기서는 **대신 불러 주기만** 한다 — 인스타 게시 로직을 다시 만들지 않는다.

- 장 이미지는 에디터가 그린 JPEG 을 받아 **잠깐 공개 주소로 둔다**. 업로더가 POST 를 처리하는
  동안 그 주소에서 받아 자기 저장소로 옮기므로, 응답이 오면 바로 지운다.
- 업로더 키는 서버에만 있다(`data/secrets/uploader_api_key`). 화면에는 절대 내보내지 않는다.
- 업로더는 키 단위로 항목을 묶는다(스튜디오 전체가 키 하나). 그래서 `ref` 에 캐러셀 번호를 넣고
  (`carousel-<id>-<난수>`), 목록·수정·취소 때 그 캐러셀의 주인인지 여기서 확인한다.
- 업로더 문서: https://instagram-reel-uploader.vercel.app/api-docs
"""

from __future__ import annotations

import json
import logging
import os
import re
import secrets
from typing import Any

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.config import settings
from app.database import get_db
from app.models.app_setting import AppSetting
from app.models.carousel import GeneratedCarousel
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/uploads", tags=["uploads"])

UPLOADER_BASE = os.environ.get("UPLOADER_API_BASE", "https://instagram-reel-uploader.vercel.app/api/v1")
# 업로더가 장 이미지를 받아 갈 주소의 앞부분. nginx 가 Host 에서 포트를 떼어 넘겨서
# 요청에서 알아낼 수 없다 — 실무 환경(dev :3443)을 기본값으로 둔다.
PUBLIC_BASE = os.environ.get("PUBLIC_BASE_URL", "https://3-35-18-166.sslip.io:3443").rstrip("/")
KEY_FILE = settings.DATA_DIR / "secrets" / "uploader_api_key"

MIN_SLIDES, MAX_SLIDES = 2, 10   # 메타 API 한도(인스타 앱의 20장은 API 로 안 된다)
_REF_RE = re.compile(r"^carousel-(\d+)-")

# 「목록에서 지우기」 한 업로더 항목 id — 사람마다 `app_settings` 한 줄(JSON 목록)에 둔다.
# 업로더 v1 API 에는 숨기기가 없어서(대시보드 전용 `queue-hide`) 여기서 걸러 낸다.
HIDDEN_KEY = "uploads_hidden:"
HIDEABLE = {"published", "deleted", "failed"}   # 끝난 것만 — 대기·진행 중인 것은 취소로 없앤다
HIDDEN_CAP = 500                                # 업로더 목록이 최근 100건이라 이만큼이면 넉넉하다
# 이 상태의 항목이 있는 캐러셀은 「작업 중·완성」 탭에서 뺀다(예약 탭과 겹치지 않게).
# 목록에서 지운 게시됨도 포함 — 이미 나간 것이라 「전체」 에서만 보인다(2026-10-07 사람 결정).
# 실패·인스타에서 삭제됨은 다시 올려야 하므로 돌려보낸다.
BUSY = {"pending", "uploading", "processing", "published"}


def _key() -> str:
    key = os.environ.get("UPLOADER_API_KEY", "").strip()
    if not key and KEY_FILE.exists():
        key = KEY_FILE.read_text(encoding="utf-8").strip()
    if not key:
        raise HTTPException(status_code=503, detail="업로더 API 키가 서버에 없습니다. 관리자에게 알려 주세요.")
    return key


async def _call(method: str, path: str, *, body: dict | None = None, timeout: float = 60) -> dict[str, Any]:
    """업로더를 부른다. 업로더의 한국어 오류 문구를 그대로 화면까지 올린다."""
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            res = await client.request(method, f"{UPLOADER_BASE}{path}", json=body,
                                       headers={"Authorization": f"Bearer {_key()}"})
    except httpx.HTTPError as e:
        logger.warning(f"[uploads] {method} {path} 연결 실패: {e!r}")
        raise HTTPException(status_code=502, detail="업로더에 연결하지 못했습니다. 잠시 뒤 다시 해 주세요.")
    try:
        data = res.json()
    except ValueError:
        data = {"error": res.text[:300]}
    if res.status_code >= 400:
        detail = (data or {}).get("error") or f"업로더 오류 ({res.status_code})"
        logger.info(f"[uploads] {method} {path} → {res.status_code}: {detail[:200]}")
        # 400·404·409 는 사람이 고칠 수 있는 이유라 그대로 넘긴다. 나머지는 업로더 쪽 문제다.
        raise HTTPException(status_code=res.status_code if res.status_code in (400, 404, 409) else 502,
                            detail=detail)
    return data or {}


def _carousel_id(ref: str | None) -> int | None:
    m = _REF_RE.match(ref or "")
    return int(m.group(1)) if m else None


async def _own_carousel(db: AsyncSession, carousel_id: int, user: User) -> GeneratedCarousel:
    row = await db.get(GeneratedCarousel, carousel_id)
    if not row or row.user_id != user.id:
        raise HTTPException(status_code=404, detail="캐러셀을 찾을 수 없습니다.")
    return row


async def _own_item(db: AsyncSession, item_id: str, user: User) -> dict[str, Any]:
    """업로더 항목이 **이 사람의 캐러셀**에서 나간 것인지 확인하고 항목을 돌려준다."""
    item = (await _call("GET", f"/posts/{item_id}")).get("item") or {}
    cid = _carousel_id(item.get("ref"))
    if cid is None:
        raise HTTPException(status_code=404, detail="스튜디오에서 올린 예약이 아닙니다.")
    await _own_carousel(db, cid, user)
    return item


def _thumb(carousel: GeneratedCarousel) -> str | None:
    path = settings.DATA_DIR / "images" / "thumbnails" / f"{carousel.id}.png"
    if path.exists():
        return f"/api/images/thumbnails/{carousel.id}.png?v={int(path.stat().st_mtime)}"
    return None


@router.get("/accounts")
async def accounts(user: User = Depends(get_current_user)) -> dict[str, Any]:
    """올릴 수 있는 인스타 계정과 댓글 자동응답 템플릿."""
    return await _call("GET", "/accounts")


@router.post("/carousels/{carousel_id}", status_code=201)
async def upload_carousel(
    carousel_id: int,
    files: list[UploadFile] = File(...),
    caption: str = Form(""),
    account: str = Form(""),
    at: str = Form(""),
    auto_respond: bool = Form(True),
    preset: str = Form(""),
    nonce: str = Form(""),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """장 이미지(JPEG)를 받아 업로더에 캐러셀 게시·예약을 맡긴다. `at` 이 비면 바로 게시."""
    await _own_carousel(db, carousel_id, user)
    if not (MIN_SLIDES <= len(files) <= MAX_SLIDES):
        raise HTTPException(status_code=400,
                            detail=f"캐러셀은 {MIN_SLIDES}~{MAX_SLIDES}장이어야 합니다 (지금 {len(files)}장).")
    if len(caption) > 2200:
        raise HTTPException(status_code=400, detail=f"캡션이 너무 깁니다 ({len(caption)}자, 최대 2200자).")

    out_dir = settings.DATA_DIR / "images" / "uploads" / str(user.id)
    out_dir.mkdir(parents=True, exist_ok=True)
    saved = []
    try:
        for f in files:
            data = await f.read()
            if not data or not (f.content_type or "").startswith("image/"):
                raise HTTPException(status_code=400, detail="장 이미지가 비었거나 이미지가 아닙니다.")
            name = f"ig_{secrets.token_hex(8)}.jpg"
            (out_dir / name).write_bytes(data)
            saved.append(out_dir / name)
        urls = [f"{PUBLIC_BASE}/api/images/uploads/{user.id}/{p.name}" for p in saved]
        # 같은 창에서 두 번 누르면 업로더가 같은 ref 를 보고 한 번만 올린다(중복 게시 방지).
        ref = f"carousel-{carousel_id}-{re.sub(r'[^A-Za-z0-9]', '', nonce)[:16] or secrets.token_hex(4)}"
        body = {
            "type": "carousel",
            "media_urls": urls,
            "caption": caption,
            "account": account or None,
            "at": at or None,
            "auto_respond": auto_respond,
            "preset": preset or None,
            "ref": ref,
        }
        # 업로더가 이 요청 안에서 장 이미지를 다 받아 간다 — 장수가 많으면 오래 걸린다.
        got = await _call("POST", "/posts", body=body, timeout=280)
        logger.info(f"[uploads] 캐러셀 {carousel_id} → 업로더 {((got.get('item') or {}).get('id'))} "
                    f"@{account or '기본'} at={at or '바로'} ({len(urls)}장)")
        return got
    finally:
        for p in saved:
            p.unlink(missing_ok=True)


async def _hidden(db: AsyncSession, user: User) -> tuple[AppSetting | None, list[str]]:
    row = await db.get(AppSetting, f"{HIDDEN_KEY}{user.id}")
    try:
        ids = json.loads(row.value) if row and row.value else []
    except ValueError:
        ids = []
    return row, [str(i) for i in ids if i] if isinstance(ids, list) else []


async def _my_items(db: AsyncSession, user: User) -> list[dict[str, Any]]:
    """이 사람의 캐러셀에서 나간 업로더 항목 — 캐러셀 제목·썸네일을 붙여서."""
    items = (await _call("GET", "/posts")).get("items") or []
    ids = {cid for cid in (_carousel_id(i.get("ref")) for i in items) if cid is not None}
    mine: dict[int, GeneratedCarousel] = {}
    if ids:
        rows = (await db.execute(select(GeneratedCarousel).where(
            GeneratedCarousel.id.in_(ids), GeneratedCarousel.user_id == user.id))).scalars().all()
        mine = {r.id: r for r in rows}
    out = []
    for item in items:
        c = mine.get(_carousel_id(item.get("ref")) or -1)
        if c is None:
            continue
        out.append({**item, "carousel": {"id": c.id, "title": c.title, "thumbnail_url": _thumb(c)}})
    return out


@router.get("/scheduled")
async def scheduled(user: User = Depends(get_current_user),
                    db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """이 사람의 캐러셀에서 나간 업로드 목록(대기·게시됨·실패). 최근 100건까지(업로더 한도).
    「목록에서 지우기」 한 항목은 뺀다. `busy_carousel_ids` 는 「작업 중·완성」 에서 뺄 캐러셀(`BUSY`)."""
    _, hidden = await _hidden(db, user)
    gone = set(hidden)
    items = await _my_items(db, user)
    busy = sorted({i["carousel"]["id"] for i in items if i.get("status") in BUSY})
    return {"items": [i for i in items if i.get("id") not in gone], "busy_carousel_ids": busy}


class HideBody(BaseModel):
    id: str | None = None   # 한 건
    done: bool = False      # 게시·삭제된 것 전부


@router.post("/scheduled/hide")
async def hide_scheduled(body: HideBody,
                         user: User = Depends(get_current_user),
                         db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """끝난 항목을 이 목록에서만 뺀다 — 인스타 게시물과 업로더 기록은 그대로 둔다.

    2026-10-07 트립앤라이프 피드백 「게시된 캐러셀이 계속 쌓인다」. 규칙은 업로더 예약목록의
    [목록에서 지우기]·[게시·삭제된 항목 모두 지우기] 그대로다 — 일괄은 실패를 남긴다(이유를 보고
    하나씩 지운다).
    """
    row, hidden = await _hidden(db, user)
    gone = set(hidden)
    done = [i for i in await _my_items(db, user)
            if i.get("id") and i.get("id") not in gone and i.get("status") in HIDEABLE]
    targets = ([i for i in done if i.get("status") != "failed"] if body.done
               else [i for i in done if i.get("id") == body.id])
    if not targets:
        raise HTTPException(status_code=400, detail="지울 항목이 없습니다.")

    value = json.dumps((hidden + [str(i["id"]) for i in targets])[-HIDDEN_CAP:])
    if row:
        row.value = value
    else:
        db.add(AppSetting(key=f"{HIDDEN_KEY}{user.id}", value=value))
    await db.commit()
    return {"ok": True, "hidden": len(targets)}


class ScheduleEdit(BaseModel):
    caption: str | None = None
    at: str | None = None
    account: str | None = None
    auto_respond: bool | None = None
    preset: str | None = None   # null 이면 기본 템플릿 — 보낸 경우에만 바뀐다


@router.patch("/scheduled/{item_id}")
async def edit_scheduled(item_id: str, body: ScheduleEdit,
                         user: User = Depends(get_current_user),
                         db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """대기 중인 예약의 캡션·시각·계정·자동응답·템플릿을 고친다. 사진은 못 바꾼다(취소 후 다시)."""
    await _own_item(db, item_id, user)
    change = body.model_dump(exclude_unset=True)
    if not change:
        raise HTTPException(status_code=400, detail="바꿀 값이 없습니다.")
    return await _call("PATCH", f"/posts/{item_id}", body=change)


@router.delete("/scheduled/{item_id}")
async def delete_scheduled(item_id: str,
                           user: User = Depends(get_current_user),
                           db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """대기 중이면 예약을 취소하고, 게시된 것은 인스타에서 지운다."""
    await _own_item(db, item_id, user)
    return await _call("DELETE", f"/posts/{item_id}")
