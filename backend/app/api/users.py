"""User management endpoints (admin-only)."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.schemas.user import UserResponse
from app.api.auth import get_current_user, hash_password
from app.api.categories import require_admin
from pydantic import BaseModel


router = APIRouter(prefix="/users", tags=["users"])


class AdminUserCreate(BaseModel):
    username: str
    password: str
    role: str = "worker"


class UserRoleUpdate(BaseModel):
    role: str


class ParaphrasePromptUpdate(BaseModel):
    # kind: "body" (카드뉴스 속지) | "title" (제목) | "caption" (캡션)
    kind: str = "body"
    # Empty string is meaningful: it clears the override (back to system default).
    prompt: str


# kind -> User column. 제목·속지·캡션은 글 성격이 달라 프롬프트를 따로 둔다
# (carousel studio feedback #11-13).
_PARAPHRASE_PROMPT_FIELDS = {
    "body": "paraphrase_prompt",
    "title": "title_paraphrase_prompt",
    "caption": "caption_paraphrase_prompt",
}


@router.get("/me/paraphrase-prompt")
async def get_my_paraphrase_prompt(user: User = Depends(get_current_user)):
    """Return the user's saved override + system default for all three
    rewrite-prompt kinds (제목 / 속지 / 캡션) so the settings modal can show
    each kind in its own tab."""
    from app.api.carousels import (
        default_paraphrase_body,
        default_paraphrase_title,
        default_paraphrase_caption,
    )
    return {
        "body": {
            "prompt": user.paraphrase_prompt or "",
            "default_prompt": default_paraphrase_body(n=10, tone="marketing"),
        },
        "title": {
            "prompt": getattr(user, "title_paraphrase_prompt", None) or "",
            "default_prompt": default_paraphrase_title(n=10),
        },
        "caption": {
            "prompt": getattr(user, "caption_paraphrase_prompt", None) or "",
            "default_prompt": default_paraphrase_caption(),
        },
    }


@router.put("/me/paraphrase-prompt")
async def update_my_paraphrase_prompt(
    data: ParaphrasePromptUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Save a per-account override for one rewrite-prompt kind (제목/속지/캡션).
    Empty string clears that kind's override → falls back to the system prompt."""
    field = _PARAPHRASE_PROMPT_FIELDS.get(data.kind)
    if not field:
        raise HTTPException(status_code=400, detail="알 수 없는 프롬프트 종류입니다")
    value = (data.prompt or "").strip()
    setattr(user, field, value or None)
    db.add(user)
    await db.commit()
    return {"kind": data.kind, "prompt": getattr(user, field) or ""}


@router.get("/", response_model=list[UserResponse])
async def list_users(
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).order_by(User.created_at.desc()))
    return result.scalars().all()


@router.post("/", response_model=UserResponse, status_code=201)
async def create_user(
    data: AdminUserCreate,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    if data.role not in ("admin", "worker"):
        raise HTTPException(status_code=400, detail="역할은 admin 또는 worker만 가능합니다")

    result = await db.execute(select(User).where(User.username == data.username))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="이미 등록된 아이디입니다")

    new_user = User(
        username=data.username,
        password_hash=hash_password(data.password),
        role=data.role,
    )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)
    return new_user


@router.patch("/{user_id}/role", response_model=UserResponse)
async def update_user_role(
    user_id: int,
    data: UserRoleUpdate,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    if data.role not in ("admin", "worker"):
        raise HTTPException(status_code=400, detail="역할은 admin 또는 worker만 가능합니다")

    result = await db.execute(select(User).where(User.id == user_id))
    target = result.scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다")

    target.role = data.role
    await db.commit()
    await db.refresh(target)
    return target


@router.delete("/{user_id}", status_code=204)
async def delete_user(
    user_id: int,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    if user_id == user.id:
        raise HTTPException(status_code=400, detail="자기 자신은 삭제할 수 없습니다")

    result = await db.execute(select(User).where(User.id == user_id))
    target = result.scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다")

    await db.delete(target)
    await db.commit()
