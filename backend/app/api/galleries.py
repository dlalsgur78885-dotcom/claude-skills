"""생성한 이미지를 링크 하나로 모아 보여주는 갤러리.

봇이 사진을 여러 장 만들면 낱장 링크를 여러 번 보내야 했다. 한 링크로 묶어 전부
보이게 하고, 각 장을 따로 고르거나 받을 수 있게 한다.

새 테이블을 만들지 않고 app_settings(key/value)에 얹는다 — prod 는 create_all 로
스키마를 올리기 때문에 테이블을 늘리면 배포 때 손이 더 간다.

보기(GET)는 인증을 걸지 않는다. 브라우저에서 토큰 없이 열려야 링크로서 쓸모가 있고,
이미지 자체(/api/images/uploads/...)도 이미 토큰 없이 서빙된다. 대신 id 를 64비트
난수로 만들어 주소를 모르면 닿을 수 없게 한다.
"""

import asyncio
import html
import json
import logging
import secrets
import tempfile
import zipfile
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from starlette.background import BackgroundTask
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.api.images import _check_host, _referer_for
from app.config import settings
from app.database import get_db
from app.models.app_setting import AppSetting
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/galleries", tags=["galleries"])

KEY_PREFIX = "gallery:"

# 한 번에 몇 장씩 받아 zip 에 넣는가. 메모리에 들고 있는 양이 이 수에 비례한다
# (dev 컨테이너는 512MB 로 묶여 있다).
FETCH_AT_ONCE = 4
MAX_IMAGE_BYTES = 20 * 1024 * 1024
_EXT_BY_MIME = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp", "image/gif": ".gif"}


class GalleryImage(BaseModel):
    url: str
    prompt: str = ""


class GalleryCreate(BaseModel):
    title: str = ""
    images: list[GalleryImage] = []


@router.post("/", status_code=201)
async def create_gallery(
    data: GalleryCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if not data.images:
        raise HTTPException(status_code=400, detail="images가 비어 있습니다")

    gallery_id = secrets.token_hex(8)
    payload = {
        "title": data.title,
        "user_id": user.id,
        "images": [image.model_dump() for image in data.images],
    }
    db.add(AppSetting(key=f"{KEY_PREFIX}{gallery_id}", value=json.dumps(payload, ensure_ascii=False)))
    await db.commit()
    return {"id": gallery_id, "count": len(data.images)}


async def _load(gallery_id: str, db: AsyncSession) -> dict[str, Any]:
    result = await db.execute(
        select(AppSetting).where(AppSetting.key == f"{KEY_PREFIX}{gallery_id}")
    )
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="갤러리를 찾을 수 없습니다")
    return json.loads(row.value)


@router.get("/{gallery_id}", response_class=HTMLResponse)
async def view_gallery(gallery_id: str, db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    return HTMLResponse(_render(gallery_id, await _load(gallery_id, db)))


@router.get("/{gallery_id}/zip")
async def download_gallery(gallery_id: str, db: AsyncSession = Depends(get_db)):
    """한 장씩 누르지 않고 전부 받는다 — 갤러리의 사진을 zip 하나로 묶어 준다.

    갤러리에는 서버에 올린 사진(`/api/images/...`)과 구글 지도·CDN 주소가 섞여 있어
    둘 다 받는다. 못 받은 장은 건너뛰고 로그에 남긴다.
    """
    data = await _load(gallery_id, db)
    items = list(enumerate(data.get("images") or [], start=1))

    tmp_path = Path(tempfile.mkstemp(prefix=f"gallery-{gallery_id}-", suffix=".zip")[1])
    packed = 0
    try:
        # 이미 압축된 PNG·JPG 라 다시 압축하지 않는다(ZIP_STORED) — 그만큼 빠르다.
        with zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_STORED) as zf:
            for start in range(0, len(items), FETCH_AT_ONCE):
                batch = items[start : start + FETCH_AT_ONCE]
                blobs = await asyncio.gather(
                    *(_read_one(str(image.get("url") or "")) for _, image in batch)
                )
                for (index, _image), blob in zip(batch, blobs):
                    if blob is None:
                        continue
                    ext, body = blob
                    zf.writestr(f"{index:02d}{ext}", body)
                    packed += 1
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise

    if not packed:
        tmp_path.unlink(missing_ok=True)
        raise HTTPException(status_code=404, detail="받을 수 있는 사진이 없습니다")

    title = (str(data.get("title") or "").strip() or f"gallery-{gallery_id}")[:60]
    return FileResponse(
        tmp_path,
        media_type="application/zip",
        filename=f"{title}.zip",
        background=BackgroundTask(tmp_path.unlink, missing_ok=True),
    )


async def _read_one(url: str) -> tuple[str, bytes] | None:
    """사진 한 장을 (확장자, 바이트) 로 읽는다. 못 읽으면 None."""
    path = _local_path(url)
    if path is not None:
        if not path.is_file():
            logger.warning(f"[gallery-zip] 파일이 없습니다: {path}")
            return None
        return path.suffix.lower() or ".png", await asyncio.to_thread(path.read_bytes)
    return await _fetch_remote(url)


async def _fetch_remote(url: str) -> tuple[str, bytes] | None:
    """밖의 주소에서 받아 온다. `/api/images/proxy` 와 같은 SSRF 방어를 쓴다."""
    parsed = urlsplit(url)
    host = parsed.hostname or ""
    if parsed.scheme not in ("http", "https") or not host:
        logger.warning(f"[gallery-zip] 주소를 알 수 없습니다: {url[:120]}")
        return None
    ok, reason = await asyncio.to_thread(_check_host, host)
    if not ok:
        logger.warning(f"[gallery-zip] {host}: {reason}")
        return None

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Referer": _referer_for(host),
    }
    try:
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
            r = await client.get(url, headers=headers)
            r.raise_for_status()
    except Exception as e:
        logger.warning(f"[gallery-zip] 받기 실패 {url[:120]}: {e}")
        return None

    body = r.content
    if not body or len(body) > MAX_IMAGE_BYTES:
        logger.warning(f"[gallery-zip] 크기가 맞지 않습니다({len(body)}): {url[:120]}")
        return None

    mime = (r.headers.get("content-type") or "").split(";")[0].strip().lower()
    ext = _EXT_BY_MIME.get(mime) or Path(unquote(parsed.path)).suffix.lower()
    return (ext if ext in _EXT_BY_MIME.values() else ".jpg"), body


def _local_path(url: str) -> Path | None:
    """`/api/images/...` 주소를 서버 안의 파일 자리로 바꾼다. 밖의 주소는 None."""
    prefix = "/api/images/"
    path = urlsplit(url).path
    if not path.startswith(prefix):
        return None
    rel = unquote(path[len(prefix):])
    if not rel or any(part in ("", "..") for part in rel.split("/")):
        return None
    root = (settings.DATA_DIR / "images").resolve()
    full = (root / rel).resolve()
    if root not in full.parents:
        return None
    return full


def _render(gallery_id: str, data: dict[str, Any]) -> str:
    title = html.escape(data.get("title") or "생성한 이미지")
    images = data.get("images") or []

    cards = []
    for index, image in enumerate(images, start=1):
        url = html.escape(str(image.get("url") or ""))
        prompt = html.escape(str(image.get("prompt") or ""))
        cards.append(
            f'<figure class="card">'
            f'<a href="{url}" target="_blank" rel="noopener">'
            f'<img src="{url}" alt="{index}번 이미지" loading="lazy">'
            f"</a>"
            f'<figcaption><span class="num">{index}</span>'
            f'<span class="desc">{prompt}</span>'
            f'<a class="save" href="{url}" download>저장</a></figcaption>'
            f"</figure>"
        )

    return f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
  :root {{ color-scheme: light dark; --bg:#faf9f7; --fg:#1b1a18; --muted:#6b6862; --line:#e3e0d9; --card:#fff; }}
  @media (prefers-color-scheme: dark) {{
    :root {{ --bg:#17161a; --fg:#eceaf2; --muted:#9d99a8; --line:#2c2a33; --card:#201f25; }}
  }}
  * {{ box-sizing: border-box; }}
  body {{ margin:0; padding:32px 20px 64px; background:var(--bg); color:var(--fg);
         font-family: system-ui, "Segoe UI", "Malgun Gothic", sans-serif; }}
  header {{ max-width:1100px; margin:0 auto 28px; }}
  h1 {{ margin:0 0 6px; font-size:1.5rem; letter-spacing:-.01em; }}
  .count {{ color:var(--muted); font-size:.9rem; }}
  .grid {{ max-width:1100px; margin:0 auto; display:grid; gap:18px;
           grid-template-columns:repeat(auto-fill, minmax(240px, 1fr)); }}
  .card {{ margin:0; background:var(--card); border:1px solid var(--line);
           border-radius:12px; overflow:hidden; }}
  .card img {{ display:block; width:100%; height:auto; background:var(--bg); }}
  figcaption {{ display:flex; align-items:center; gap:8px; padding:10px 12px;
                border-top:1px solid var(--line); font-size:.85rem; }}
  .num {{ flex:none; width:22px; height:22px; border-radius:50%; background:var(--fg);
          color:var(--card); display:grid; place-items:center; font-size:.75rem; }}
  .desc {{ flex:1; color:var(--muted); overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }}
  .save {{ flex:none; color:inherit; text-decoration:none; border:1px solid var(--line);
           padding:3px 9px; border-radius:6px; }}
  .save:hover {{ border-color:var(--fg); }}
  .all {{ display:inline-block; margin-top:12px; color:var(--card); background:var(--fg);
          text-decoration:none; padding:8px 14px; border-radius:8px; font-size:.9rem; }}
  .all:hover {{ opacity:.85; }}
</style></head>
<body>
  <header><h1>{title}</h1><div class="count">{len(images)}장 · 각 장을 눌러 크게 보거나 저장하세요</div>
  <a class="all" href="/api/galleries/{gallery_id}/zip" download>전체 저장 ({len(images)}장 ZIP)</a></header>
  <div class="grid">{''.join(cards)}</div>
</body></html>"""
