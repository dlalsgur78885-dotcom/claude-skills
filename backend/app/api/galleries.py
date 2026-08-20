"""생성한 이미지를 링크 하나로 모아 보여주는 갤러리.

봇이 사진을 여러 장 만들면 낱장 링크를 여러 번 보내야 했다. 한 링크로 묶어 전부
보이게 하고, 각 장을 따로 고르거나 받을 수 있게 한다.

새 테이블을 만들지 않고 app_settings(key/value)에 얹는다 — prod 는 create_all 로
스키마를 올리기 때문에 테이블을 늘리면 배포 때 손이 더 간다.

보기(GET)는 인증을 걸지 않는다. 브라우저에서 토큰 없이 열려야 링크로서 쓸모가 있고,
이미지 자체(/api/images/uploads/...)도 이미 토큰 없이 서빙된다. 대신 id 를 64비트
난수로 만들어 주소를 모르면 닿을 수 없게 한다.
"""

import html
import json
import secrets
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.database import get_db
from app.models.app_setting import AppSetting
from app.models.user import User

router = APIRouter(prefix="/galleries", tags=["galleries"])

KEY_PREFIX = "gallery:"


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


@router.get("/{gallery_id}", response_class=HTMLResponse)
async def view_gallery(gallery_id: str, db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    result = await db.execute(
        select(AppSetting).where(AppSetting.key == f"{KEY_PREFIX}{gallery_id}")
    )
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="갤러리를 찾을 수 없습니다")

    data = json.loads(row.value)
    return HTMLResponse(_render(data))


def _render(data: dict[str, Any]) -> str:
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
</style></head>
<body>
  <header><h1>{title}</h1><div class="count">{len(images)}장 · 각 장을 눌러 크게 보거나 저장하세요</div></header>
  <div class="grid">{''.join(cards)}</div>
</body></html>"""
