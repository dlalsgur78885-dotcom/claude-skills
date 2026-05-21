"""User-uploaded fonts for the carousel editor.

The user downloads a font file and uploads it here; we store it under
data/fonts/{user_id}/ and list a user's fonts by globbing that directory —
no DB table needed (mirrors the on-disk approach of the CTA image).

The editor registers each font as a FontFace so canvas text can use it; PNG
export is client-side (canvas.toDataURL), so a loaded FontFace renders into
the export automatically — no server-side font embedding required.
"""

import re

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app.api.auth import get_current_user
from app.config import settings
from app.models.user import User

router = APIRouter(prefix="/fonts", tags=["fonts"])

_ALLOWED_EXT = {".ttf", ".otf", ".woff", ".woff2"}
# Korean fonts carry thousands of CJK glyphs — full serif faces routinely run
# 20-30MB — so the cap has to be generous to be useful for this product.
_MAX_BYTES = 30 * 1024 * 1024  # 30MB


def _fonts_dir(user_id: int):
    return settings.DATA_DIR / "fonts" / str(user_id)


def _safe_family(filename: str) -> str:
    """Derive the font-family name from the upload filename.

    This name is shown in the editor's font dropdown AND used as the CSS
    font-family / FontFace family, so keep only letters (incl. Korean),
    digits, spaces and `.-_`. Also blocks path traversal via the filename.
    """
    stem = (filename or "").rsplit(".", 1)[0]
    stem = re.sub(r"[^\w .-]+", "", stem, flags=re.UNICODE).strip()
    return stem or "font"


def _ext(filename: str) -> str:
    name = (filename or "").lower()
    return "." + name.rsplit(".", 1)[-1] if "." in name else ""


@router.get("")
async def list_fonts(user: User = Depends(get_current_user)):
    """List the fonts this user has uploaded."""
    d = _fonts_dir(user.id)
    fonts = []
    if d.exists():
        for p in sorted(d.iterdir()):
            if p.suffix.lower() in _ALLOWED_EXT:
                fonts.append({
                    "family": p.stem,
                    "filename": p.name,
                    "url": f"/api/fonts/{user.id}/{p.name}",
                })
    return {"fonts": fonts}


@router.post("/upload")
async def upload_font(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
):
    """Store (or replace) an uploaded font file for this user."""
    ext = _ext(file.filename or "")
    if ext not in _ALLOWED_EXT:
        raise HTTPException(status_code=415, detail="ttf · otf · woff · woff2 파일만 업로드 가능합니다")
    data = await file.read()
    if len(data) > _MAX_BYTES:
        raise HTTPException(status_code=413, detail="폰트 파일이 너무 큽니다 (>30MB)")
    family = _safe_family(file.filename or "font")
    d = _fonts_dir(user.id)
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{family}{ext}"
    path.write_bytes(data)
    return {"family": family, "filename": path.name, "url": f"/api/fonts/{user.id}/{path.name}"}


@router.delete("/{filename}")
async def delete_font(filename: str, user: User = Depends(get_current_user)):
    """Remove one of the user's uploaded fonts."""
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="bad path")
    path = _fonts_dir(user.id) / filename
    if path.exists():
        path.unlink()
    return {"ok": True}


@router.get("/{user_id}/{filename}")
async def serve_font(user_id: str, filename: str):
    """Serve a font file.

    Unauthenticated by design: the browser's FontFace fetch can't carry the
    JWT Bearer header. Path-traversal guarded; font files aren't sensitive.
    """
    if not user_id.isdigit() or "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="bad path")
    path = settings.DATA_DIR / "fonts" / user_id / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="폰트를 찾을 수 없습니다")
    return FileResponse(path)
