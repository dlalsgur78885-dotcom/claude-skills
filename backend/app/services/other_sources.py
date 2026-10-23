"""X 밖 소재 경로 — Togetter · 일본 매체 RSS · 유튜브 · 스레드 · 한국 커뮤니티.

2026-10-23 트립앤라이프 「네 경로도 1단계에 꽂아둬 · 한국커뮤니티도 뽑아서 넣어」.
그 전까지 1단계는 **X 하나만** 긁었다(`_유형공통.md` — 그래서 ①이 X 가 아닌 유형은
후보가 잘 안 올라왔다).

⚠ **규칙을 여기 베껴 넣지 않는다.** 어디를 긁고 · 문턱이 얼마고 · 무엇을 빼는지는
`scripts/collect_sources.py` 와 `docs/process/_유형공통.md` 가 정한다. 이 모듈은 그
스크립트를 `--json` 으로 돌려 **1단계 후보 꼴로 바꾸기만** 한다. 소스를 늘리고 싶으면
스크립트의 목록(`TOGETTER`·`FEEDS`·`KR_FEEDS`·`KR_PAGES`)에 줄을 더하면 된다.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# backend/app/services/other_sources.py → 레포 뿌리
ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "collect_sources.py"

# 유튜브·스레드는 키워드마다 15~40초가 걸린다. 1단계는 이미 40분짜리라 함께 돌려도
# 되지만, 막히면 회차를 붙잡지 않게 **제한 시간을 둔다**(넘으면 그때까지 받은 것도 버린다).
TIMEOUT_SEC = 420


def _candidate(row: dict[str, Any]) -> dict[str, Any] | None:
    """수집 한 줄 → 1단계 후보 한 건. X 후보와 **같은 열**을 쓴다(`x_search._from_fx`)."""
    url = str(row.get("url") or "").strip()
    title = " ".join(str(row.get("title") or "").split())
    if not url or not title:
        return None
    num = row.get("num")
    num = int(num) if isinstance(num, int) else 0
    unit = str(row.get("unit") or "")
    return {
        # X 의 숫자 id 와 섞이지 않게 접두사를 붙인다 — 이력·중복 거르기도 이 값으로 돈다.
        "post_id": "src_" + hashlib.sha1(url.encode("utf-8")).hexdigest()[:14],
        "url": url,
        "topic": title,
        # 제목이 곧 본문이다. **본문·사진은 고른 뒤 연다**(수집 단계는 제목·수치만 본다).
        "text": title,
        "account": str(row.get("src") or ""),
        "author": str(row.get("src") or ""),
        "created_at": str(row.get("date") or ""),
        "photos": 0,
        "photo_urls": [],
        "views": num if unit in ("회", "pv") else 0,
        "likes": num if unit == "♥" else 0,
        "replies": 0,
        # 화면 꼬리표는 `studio_steps.source_label` 이 **주소**로 가린다. 이 두 값은
        # 수집 쪽 판정을 남겨 두는 자리다(등급 A/B · 접점 한국/여행접점).
        "src_grade": str(row.get("grade") or ""),
        "src_tag": str(row.get("tag") or ""),
    }


async def collect(limit: int = 20, *, deep: bool = True) -> list[dict[str, Any]]:
    """X 밖 경로를 한 번 돌려 후보를 돌려준다. 막히면 **빈 목록**이다(회차는 살린다).

    - `deep=True` — 유튜브·스레드까지(`--all`). 2~4분.
    - `deep=False` — Togetter·일본 매체 RSS·한국 커뮤니티만(`--korea`). 1분 안쪽.
    """
    if not SCRIPT.exists():
        logger.warning("[소재] 수집 스크립트가 없습니다 — %s", SCRIPT)
        return []
    args = [sys.executable, str(SCRIPT), "--json", "--n", str(limit),
            "--all" if deep else "--korea"]
    try:
        proc = await asyncio.create_subprocess_exec(
            *args, cwd=str(ROOT),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        out, err = await asyncio.wait_for(proc.communicate(), timeout=TIMEOUT_SEC)
    except asyncio.TimeoutError:
        logger.warning("[소재] 수집이 %d초를 넘겨 건너뜁니다", TIMEOUT_SEC)
        return []
    except Exception as e:
        logger.warning("[소재] 수집을 돌리지 못했습니다 — %s", str(e)[:200])
        return []

    rows: list[dict[str, Any]] = []
    for line in (out or b"").decode("utf-8", "replace").splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    items = [c for c in (_candidate(r) for r in rows) if c]
    tail = (err or b"").decode("utf-8", "replace").strip().splitlines()
    logger.info("[소재] X 밖 경로 %d건 — %s", len(items), tail[-1] if tail else "")
    return items
