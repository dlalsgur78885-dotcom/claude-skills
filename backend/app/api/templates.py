"""Template Studio API - generate and manage rendering templates."""

import logging
import secrets
from typing import Literal

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.config import settings
from app.database import get_db
from app.models.user import User
from app.services.instagram import InstagramAPI
from app.services.layout_hidden import set_hidden
from app.services.template_studio import (
    clone_template,
    delete_template,
    generate_and_save_template,
    get_template,
    list_layout_catalog,
    list_templates_db,
    template_row_summary,
    template_row_to_dict,
    update_template,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/templates", tags=["templates"])


class LayoutHint(BaseModel):
    """User-provided layout classification for one carousel slide.

    `kind="single"` means an ordinary one-main-content slide.
    `kind="grid"` means a multi-item grid; `rows`/`cols` MUST be set in that case.
    `kind="none"` excludes the slide from template extraction entirely.
    """
    slide_index: int
    kind: Literal["single", "grid", "none"] = "single"
    rows: int | None = None
    cols: int | None = None


class GenerateTemplateRequest(BaseModel):
    post_url: str
    template_name: str
    channel_id: int | None = None
    layout_hints: list[LayoutHint] | None = None


class PreviewSlidesRequest(BaseModel):
    post_url: str


class UpdateTemplateRequest(BaseModel):
    name: str | None = None
    canvas: dict | None = None
    brand: dict | None = None
    layouts: dict | None = None


class CopyLayoutRequest(BaseModel):
    src_template_id: int
    src_layout_name: str


class HideLayoutRequest(BaseModel):
    """낱장 목록에서 숨기기/숨김 해제. 템플릿 원본은 바뀌지 않는다."""
    template_id: int
    layout_key: str
    hidden: bool = True


@router.get("/")
async def list_all_templates(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all templates visible to the current user (own + system)."""
    return {"templates": await list_templates_db(db, user.id)}


@router.get("/layouts")
async def list_layouts(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """템플릿을 낱장(레이아웃 하나)으로 펼친 카탈로그.

    세트 선택(`GET /`)은 그대로 두고 낱장 선택을 병렬로 제공한다. 분류는 키 이름이
    아니라 구조로 매긴다 — layout_classify 참고.

    ⚠ 이 라우트는 `/{template_id}` 보다 **먼저** 등록돼야 한다. 뒤에 두면 "layouts"
    가 template_id 로 잡혀 422 가 난다.
    """
    return {"layouts": await list_layout_catalog(db, user.id)}


@router.post("/layouts/hidden")
async def set_layout_hidden(
    body: HideLayoutRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """낱장 하나를 낱장 목록에서 숨기거나 다시 보이게 한다.

    템플릿 원본(layouts JSON)은 건드리지 않는다 — 숨긴 뒤에도 그 템플릿을 세트로
    고르는 건 그대로 동작한다. 숨김은 유저별이다.

    ⚠ `/{template_id}` 보다 먼저 등록돼야 한다 (`/layouts` 와 같은 이유).
    """
    keys = await set_hidden(db, user.id, body.template_id, body.layout_key, body.hidden)
    return {"hidden_count": len(keys)}


@router.post("/preview-slides")
async def preview_slides(
    body: PreviewSlidesRequest,
    user: User = Depends(get_current_user),
):
    """Return slide thumbnail URLs for a benchmark post — no Vision call.

    Used by the UI to show carousel slides to the user so they can classify
    each one as single/grid before kicking off the (expensive) Vision pipeline.
    """
    api = InstagramAPI()
    try:
        post = await api.scrape_post(body.post_url)
    except Exception as e:
        logger.exception("Slide preview scrape failed")
        raise HTTPException(status_code=400, detail=f"게시글을 불러올 수 없습니다: {e}")
    finally:
        await api.close()
    image_urls = post.get("image_urls") or []
    if not image_urls:
        raise HTTPException(status_code=400, detail="캐러셀 이미지를 찾지 못했습니다")
    return {"slide_urls": image_urls}


@router.post("/generate")
async def generate_template(
    body: GenerateTemplateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate a new template from a benchmark Instagram post URL.

    Calls Gemini Vision once, validates the output, persists to DB.
    If channel_id is provided, links the template to that channel and applies
    the per-channel limit.
    """
    try:
        row = await generate_and_save_template(
            db=db,
            post_url=body.post_url,
            template_name=body.template_name,
            user_id=user.id,
            channel_id=body.channel_id,
            layout_hints=[h.model_dump() for h in body.layout_hints] if body.layout_hints else None,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Template generation failed")
        raise HTTPException(status_code=500, detail=str(e))

    return template_row_summary(row)


# ─── Asset upload ───
# Used by the template editor to attach user-supplied PNGs (logos, CTA badges,
# stamps) to a layout decoration. Returns a public /api/images/... path that
# both the in-editor preview canvas and the final renderer can fetch.
#
# IMPORTANT — must be declared BEFORE any `/{template_id}` route below: a
# request to `POST /upload-asset` would otherwise match `/{template_id}` first
# (with template_id="upload-asset"), and since that path is only registered for
# GET/PATCH/DELETE, Starlette returns 405 instead of falling through.
_ASSET_EXT_BY_MIME = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/webp": ".webp",
    "image/svg+xml": ".svg",
}


@router.post("/upload-asset")
async def upload_template_asset(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
):
    """Save a decoration asset (PNG/JPG/WEBP/SVG) and return its public path.

    The asset is namespaced by user id so deletions don't collide. We don't
    track ownership in the DB — the URL itself is the only handle, baked into
    the template's layout JSON. That's fine for the studio's scope.
    """
    if not (file.content_type or "").startswith("image/"):
        raise HTTPException(status_code=415, detail="이미지 파일만 업로드 가능합니다")
    ext = _ASSET_EXT_BY_MIME.get((file.content_type or "").lower(), ".png")

    out_dir = settings.DATA_DIR / "images" / "template_assets" / str(user.id)
    out_dir.mkdir(parents=True, exist_ok=True)

    fname = f"{secrets.token_hex(8)}{ext}"
    out_path = out_dir / fname
    out_path.write_bytes(await file.read())

    return {"path": f"/api/images/template-assets/{user.id}/{fname}"}


@router.get("/{template_id}")
async def get_full_template(
    template_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    row = await get_template(db, template_id, user.id)
    if not row:
        raise HTTPException(status_code=404, detail="템플릿을 찾을 수 없습니다")
    return template_row_to_dict(row)


@router.patch("/{template_id}")
async def patch_template(
    template_id: int,
    body: UpdateTemplateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    row = await update_template(
        db,
        template_id,
        user.id,
        name=body.name,
        canvas=body.canvas,
        brand=body.brand,
        layouts=body.layouts,
    )
    if not row:
        raise HTTPException(
            status_code=404,
            detail="템플릿을 찾을 수 없거나 수정 권한이 없습니다",
        )
    return template_row_to_dict(row)


@router.post("/{template_id}/layouts/copy-from", status_code=201)
async def copy_layout_into_template(
    template_id: int,
    body: CopyLayoutRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Copy one layout from a source template into this (destination) template.

    Source must be readable by the user (own/system/public-shared); destination
    must be writable (own or system — same rule as update_template). On name
    collision, the new layout is suffixed with -copy / -copy-2 / ... until unique.
    """
    dst = await db.get(CarouselTemplate, template_id)
    if not dst or (dst.user_id is not None and dst.user_id != user.id):
        raise HTTPException(
            status_code=404,
            detail="대상 템플릿을 찾을 수 없거나 본인 소유가 아닙니다",
        )
    src = await get_template(db, body.src_template_id, user.id)
    if not src:
        raise HTTPException(status_code=404, detail="원본 템플릿을 찾을 수 없습니다")
    src_layouts = src.layouts or {}
    if body.src_layout_name not in src_layouts:
        raise HTTPException(
            status_code=404,
            detail=f"원본 템플릿에 '{body.src_layout_name}' 레이아웃이 없습니다",
        )
    layout_data = src_layouts[body.src_layout_name]

    dst_layouts = dict(dst.layouts or {})
    new_name = body.src_layout_name
    if new_name in dst_layouts:
        i = 1
        while True:
            cand = f"{body.src_layout_name}-copy" if i == 1 else f"{body.src_layout_name}-copy-{i}"
            if cand not in dst_layouts:
                new_name = cand
                break
            i += 1
    dst_layouts[new_name] = layout_data
    dst.layouts = dst_layouts
    await db.commit()
    await db.refresh(dst)
    return {"layout_name": new_name, "template": template_row_to_dict(dst)}


@router.post("/{template_id}/clone", status_code=201)
async def clone_existing_template(
    template_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    row = await clone_template(db, template_id, user.id)
    if not row:
        raise HTTPException(status_code=404, detail="템플릿을 찾을 수 없습니다")
    return template_row_summary(row)


@router.delete("/{template_id}", status_code=204)
async def remove_template(
    template_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ok = await delete_template(db, template_id, user.id)
    if not ok:
        raise HTTPException(status_code=404, detail="템플릿을 찾을 수 없습니다")


# ─── Sharing ───

from app.models.template import CarouselTemplate
from sqlalchemy import select


@router.post("/{template_id}/share")
async def share_template(
    template_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate (or return existing) share code for a template the user owns.

    Returns {share_code, share_url}. Share code is opaque so URLs can't be guessed.
    """
    row = await db.get(CarouselTemplate, template_id)
    if not row or row.user_id != user.id:
        raise HTTPException(status_code=404, detail="템플릿을 찾을 수 없거나 본인 소유가 아닙니다")
    if not row.share_code:
        # 18-char URL-safe random — collision probability negligible (≈ 1e-32 per row).
        row.share_code = secrets.token_urlsafe(13)[:18]
    row.is_public = True
    await db.commit()
    await db.refresh(row)
    return {
        "share_code": row.share_code,
        "share_url": f"/templates/import?code={row.share_code}",
        "is_public": row.is_public,
    }


@router.delete("/{template_id}/share", status_code=204)
async def unshare_template(
    template_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    row = await db.get(CarouselTemplate, template_id)
    if not row or row.user_id != user.id:
        raise HTTPException(status_code=404, detail="템플릿을 찾을 수 없거나 본인 소유가 아닙니다")
    row.share_code = None
    row.is_public = False
    await db.commit()


@router.get("/by-share/{code}")
async def get_template_by_share(
    code: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Resolve a share code to its template (read-only summary preview).

    Any authenticated user can call this — share code itself is the access
    token. Returns template summary + a few preview fields.
    """
    result = await db.execute(
        select(CarouselTemplate).where(CarouselTemplate.share_code == code)
    )
    row = result.scalar_one_or_none()
    if not row or not row.is_public:
        raise HTTPException(status_code=404, detail="공유된 템플릿을 찾을 수 없습니다")
    return template_row_to_dict(row)


@router.post("/by-share/{code}/clone", status_code=201)
async def clone_template_by_share(
    code: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Clone a shared template into the current user's library."""
    result = await db.execute(
        select(CarouselTemplate).where(CarouselTemplate.share_code == code)
    )
    src = result.scalar_one_or_none()
    if not src or not src.is_public:
        raise HTTPException(status_code=404, detail="공유된 템플릿을 찾을 수 없습니다")
    # Reuse the existing clone_template path which handles slug-collision
    # numbering. Pass the source row's id so service treats it as a clone.
    row = await clone_template(db, src.id, user.id)
    if not row:
        raise HTTPException(status_code=500, detail="복제 실패")
    return template_row_summary(row)
