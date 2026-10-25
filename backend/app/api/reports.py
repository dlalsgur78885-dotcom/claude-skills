"""정리가 필요한 답을 링크 하나로 — 웹 보고서.

디스코드 답은 1900자에서 잘리고, 봇은 「3줄 안쪽」으로 답한다(2026-10-25 사람 지시).
비교표·회차 정리·조사 결과처럼 길게 봐야 하는 것은 여기 마크다운으로 올리고
디스코드에는 결론 한 줄과 링크만 보낸다.

갤러리(`galleries.py`)와 같은 방식이다 — 새 테이블 없이 app_settings 에 얹고,
보기(GET)는 인증 없이 열리되 id 를 64비트 난수로 만들어 주소를 모르면 닿지 않는다.

⚠ 본문은 **마크다운만** 받는다. 원시 HTML 은 글자로 바꿔 보여준다(`html: False`).
  이 페이지는 스튜디오와 같은 주소에서 열리므로 남이 넣은 스크립트가 돌면 안 된다.
"""

import html
import json
import secrets
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from markdown_it import MarkdownIt
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.database import get_db
from app.models.app_setting import AppSetting
from app.models.user import User

router = APIRouter(prefix="/reports", tags=["reports"])

KEY_PREFIX = "report:"
# 보고서 하나가 DB 한 칸이다. 이보다 길면 나눠 올리게 한다.
MAX_MARKDOWN_CHARS = 200_000

_MD = MarkdownIt("commonmark", {"html": False, "linkify": False}).enable("table")


class ReportCreate(BaseModel):
    title: str = ""
    markdown: str


@router.post("/", status_code=201)
async def create_report(
    data: ReportCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if not data.markdown.strip():
        raise HTTPException(status_code=400, detail="markdown 이 비어 있습니다")
    if len(data.markdown) > MAX_MARKDOWN_CHARS:
        raise HTTPException(status_code=400, detail=f"보고서가 너무 깁니다({MAX_MARKDOWN_CHARS}자 이하)")
    report_id = secrets.token_hex(8)
    payload = {"title": data.title.strip(), "user_id": user.id, "markdown": data.markdown}
    db.add(AppSetting(key=f"{KEY_PREFIX}{report_id}", value=json.dumps(payload, ensure_ascii=False)))
    await db.commit()
    return {"id": report_id}


@router.get("/{report_id}", response_class=HTMLResponse)
async def view_report(report_id: str, db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    row = (await db.execute(
        select(AppSetting).where(AppSetting.key == f"{KEY_PREFIX}{report_id}")
    )).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="보고서를 찾을 수 없습니다")
    data = json.loads(row.value)
    return HTMLResponse(_render(str(data.get("title") or "보고서"), _MD.render(str(data.get("markdown") or ""))))


def _render(title: str, body: str) -> str:
    t = html.escape(title)
    return f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex">
<title>{t}</title>
<style>
:root {{ --bg:#ffffff; --fg:#1c1d1f; --muted:#6b6f76; --line:#e6e6e8; --head:#f6f6f7; --link:#3b5bdb; }}
@media (prefers-color-scheme: dark) {{
  :root {{ --bg:#111214; --fg:#e8e8ea; --muted:#9a9ca3; --line:#2a2c30; --head:#1b1c1f; --link:#8aa2ff; }}
}}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--bg); color:var(--fg);
  font:16px/1.7 -apple-system,BlinkMacSystemFont,"Pretendard","Apple SD Gothic Neo","Malgun Gothic",sans-serif; }}
main {{ max-width:860px; margin:0 auto; padding:32px 16px 64px; }}
h1.title {{ font-size:26px; margin:0 0 24px; }}
h1,h2,h3 {{ line-height:1.35; }}
h2 {{ margin-top:36px; font-size:20px; }}
a {{ color:var(--link); }}
table {{ display:block; overflow-x:auto; border-collapse:collapse; margin:16px 0; }}
th,td {{ border:1px solid var(--line); padding:8px 12px; text-align:left; vertical-align:top; }}
th {{ background:var(--head); white-space:nowrap; }}
code {{ background:var(--head); padding:1px 5px; border-radius:4px; font-size:14px; }}
pre {{ background:var(--head); padding:12px; border-radius:8px; overflow-x:auto; }}
pre code {{ padding:0; }}
blockquote {{ margin:16px 0; padding:4px 16px; border-left:3px solid var(--line); color:var(--muted); }}
img {{ max-width:100%; height:auto; border-radius:6px; }}
</style></head>
<body><main><h1 class="title">{t}</h1>
{body}
</main></body></html>"""
