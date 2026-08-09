"""Admin-only settings — read/update API keys at runtime."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.database import get_db
from app.models.app_setting import AppSetting
from app.models.user import User
from app.services.settings_provider import (
    EDITABLE_KEYS,
    apply_to_environ,
    invalidate_cache,
    list_settings_for_admin,
)


def _require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="admin 권한이 필요합니다")
    return user


router = APIRouter(prefix="/settings", tags=["settings"])


class SettingsUpdate(BaseModel):
    values: dict[str, str]


@router.get("/")
async def get_settings(
    user: User = Depends(_require_admin),
):
    """Return all editable API keys with masked previews."""
    data = await list_settings_for_admin()
    return {"settings": data, "editable_keys": EDITABLE_KEYS}


@router.put("/")
async def update_settings(
    body: SettingsUpdate,
    user: User = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Bulk-update API keys. Empty string deletes the DB row (falls back to env)."""
    unknown = [k for k in body.values if k not in EDITABLE_KEYS]
    if unknown:
        raise HTTPException(status_code=400, detail=f"알 수 없는 키: {unknown}")

    for key, value in body.values.items():
        value = (value or "").strip()
        result = await db.execute(select(AppSetting).where(AppSetting.key == key))
        row = result.scalar_one_or_none()
        if value:
            if row:
                row.value = value
                row.updated_at = datetime.now()
            else:
                db.add(AppSetting(key=key, value=value))
        else:
            if row:
                await db.delete(row)

    await db.commit()
    await invalidate_cache()
    await apply_to_environ()
    return await list_settings_for_admin()
