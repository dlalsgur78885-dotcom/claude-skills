"""CTA image — register and reuse a call-to-action PNG for carousel endings.

One PNG per user, stored at a fixed path so re-registration overwrites it.
The carousel editor drops it onto a fresh last slide via "CTA 추가".
"""

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.api.auth import get_current_user
from app.config import settings
from app.models.user import User

router = APIRouter(prefix="/cta", tags=["cta"])


def _cta_path(user_id: int):
    """On-disk location of a user's registered CTA image (one per user)."""
    return settings.DATA_DIR / "images" / "cta" / str(user_id) / "cta.png"


@router.get("")
async def get_cta_image(user: User = Depends(get_current_user)):
    """Return the registered CTA image URL, or null when none is registered."""
    path = _cta_path(user.id)
    if not path.exists():
        return {"url": None}
    # Cache-buster: the filename is fixed, so without ?v= the browser would
    # keep showing the old image after a re-registration.
    mtime = int(path.stat().st_mtime)
    return {"url": f"/api/images/cta/{user.id}/cta.png?v={mtime}"}


@router.post("/upload")
async def upload_cta_image(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
):
    """Register (or replace) the user's reusable CTA PNG."""
    ctype = (file.content_type or "").lower()
    if ctype != "image/png" and not (file.filename or "").lower().endswith(".png"):
        raise HTTPException(status_code=415, detail="PNG 파일만 업로드 가능합니다")
    path = _cta_path(user.id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(await file.read())
    mtime = int(path.stat().st_mtime)
    return {"url": f"/api/images/cta/{user.id}/cta.png?v={mtime}"}
