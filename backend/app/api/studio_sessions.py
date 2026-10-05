"""원클릭 스튜디오 — 회차 상태 보관소 (서버 쪽).

## 왜 이런 모양인가

문구·그림은 **codex** 가 짓는데, codex 는 사람 PC 의 로그인 세션에 묶여 있어 서버로 못 옮긴다.
그렇다고 화면을 그 PC 에 두면 밖에서 주소로 닿을 수 없다(브라우저는 디스코드를 통과하지 못한다).

그래서 봇이 쓰는 수법을 그대로 쓴다 — **일하는 쪽이 먼저 연결을 건다.**

    사람  →  서버 화면에서 클릭
                ↓ 고른 것이 여기 쌓인다
            이 파일(회차 상태)
                ↑ PC 의 일꾼이 주기적으로 가져가 codex 로 처리하고 결과를 올린다

서버는 **아무것도 만들지 않는다.** 상태를 들고 있다가 양쪽에 넘겨줄 뿐이다.
`make_gallery` 가 이미 작게 하던 방식(사진을 서버에 올려 링크 하나로 발행)을 6단계로 키운 것이다.

## 저장 자리

새 테이블을 만들지 않고 `app_settings` 에 얹는다 — 갤러리와 같은 이유다(prod 는 create_all
로 스키마를 올리므로 테이블을 늘리면 배포 때 손이 더 간다).

## 규칙의 원본은 여전히 지침서다

여기에는 프롬프트도 톤 규칙도 없다. 그것은 일꾼(PC)이 `docs/process` 를 읽어 채운다.
이 파일이 아는 것은 **단계 번호와 주고받는 칸 이름**뿐이다.
"""

import json
import secrets
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.database import get_db
from app.models.app_setting import AppSetting
from app.models.user import User

router = APIRouter(prefix="/studio-sessions", tags=["studio"])

KEY_PREFIX = "studio:"

# 화면이 보여주는 6단계. 일꾼은 `pending` 을 보고 무엇을 지을지 안다.
# keep 은 화면에 보이는 단계가 아니라 「보관함에 적어 달라」는 잔심부름이다.
# prepare 는 **출근 전에 미리 다 만들어 두는** 일이다 — 주제 10개 각각의 훅·사진·
# 본문·캡션을 한꺼번에 짓는다. 사람은 아침에 고르기만 한다(2026-09-03 요구).
STEPS = ("topics", "hooks", "images", "body", "cta1", "caption", "build", "keep", "prepare")


def _blank(axis: str, owner: int, pending: str = "topics") -> dict[str, Any]:
    return {
        "axis": axis,
        "owner": owner,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        # 일꾼이 처리해야 할 일. 비어 있으면 사람이 고를 차례다.
        "pending": pending,
        "error": "",
        # 일꾼이 채우는 후보들
        "candidates": {},
        # 사람이 고른 것
        "chosen": {},
        # 6단계 결과
        "result": None,
        # 캐러셀을 만들어 **편집 링크까지 받은** 주제. 다른 주제를 고르면 result 는 지워지므로
        # 「이 주제는 이미 만들었다」는 화면 표시(=[완료] 버튼)는 여기서 본다.
        "built": [],
    }


async def _load(db: AsyncSession, session_id: str) -> tuple[AppSetting, dict[str, Any]]:
    row = (await db.execute(
        select(AppSetting).where(AppSetting.key == f"{KEY_PREFIX}{session_id}")
    )).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="그런 회차가 없습니다")
    try:
        return row, json.loads(row.value)
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="회차 기록이 깨졌습니다")


async def _save(db: AsyncSession, row: AppSetting, data: dict[str, Any]) -> None:
    row.value = json.dumps(data, ensure_ascii=False)
    # 값만 바꾸면 updated_at 이 안 움직이는 경우가 있어 명시한다 — 일꾼이 이걸로 순서를 본다.
    row.updated_at = datetime.now()
    await db.commit()


# 회차를 넘어 남는 「이미 만든 주제」 — 축마다 한 줄.
#
# ⚠ 회차 안의 `built` 만으로는 모자란다(2026-09-07 사람 신고 — 만든 주제가 [완료] 로
#   안 바뀐다). 밤 미리 만들기가 축마다 회차를 **여러 개** 열어 두고(23:00·06:00),
#   회차마다 같은 주제 목록을 들고 있다. 한 회차에서 만든 주제가 다른 회차에서는
#   그대로 [선택] 으로 보였다.
# 키 접두어가 회차(`studio:`)와 겹치지 않아야 한다 — `latest` 가 `studio:%` 로 훑는다.
BUILT_KEY = "studio-built:"
BUILT_MAX = 300


async def _built_shared(db: AsyncSession, axis: str) -> list[str]:
    row = (await db.execute(
        select(AppSetting).where(AppSetting.key == f"{BUILT_KEY}{axis}")
    )).scalar_one_or_none()
    if not row:
        return []
    try:
        got = json.loads(row.value)
    except json.JSONDecodeError:
        return []
    return [str(t) for t in got] if isinstance(got, list) else []


async def _mark_built(db: AsyncSession, axis: str, topic: str) -> None:
    """만든 주제를 축 단위로 적어 둔다 — 어느 회차에서 만들었든 [완료] 로 보이게."""
    made = await _built_shared(db, axis)
    if topic in made:
        return
    value = json.dumps([*made, topic][-BUILT_MAX:], ensure_ascii=False)
    row = (await db.execute(
        select(AppSetting).where(AppSetting.key == f"{BUILT_KEY}{axis}")
    )).scalar_one_or_none()
    if row:
        row.value = value
        row.updated_at = datetime.now()
    else:
        db.add(AppSetting(key=f"{BUILT_KEY}{axis}", value=value))
    await db.commit()


async def _out(db: AsyncSession, session_id: str, data: dict[str, Any]) -> dict[str, Any]:
    """화면에 주는 모양 — 이 회차의 `built` 에 **다른 회차에서 만든 것**까지 합쳐 준다.

    합치기만 하고 저장하지는 않는다. 회차 기록은 그 회차가 한 일만 담아 둔다.
    """
    built = list(data.get("built") or [])
    shared = await _built_shared(db, str(data.get("axis") or ""))
    return {"id": session_id, **data,
            "built": [*built, *(t for t in shared if t not in built)]}


class CreateBody(BaseModel):
    axis: str = "상황별일본어"
    # 밤에 미리 다 만들어 둘 때는 "prepare" 로 연다. 그러면 주제 목록과 각 주제의
    # 훅·사진·본문·캡션을 한꺼번에 짓는다.
    # ⚠ 기본값("topics")으로 열어 놓고 곧바로 prepare 로 바꾸면 **경합이 난다** —
    #   일꾼이 먼저 집은 topics 가 나중에 끝나면서 미리 만든 목록을 덮어썼다(2026-09-03).
    pending: str = "topics"
    # 여는 순간 함께 넣을 값. 만든 뒤 PATCH 로 넣으면 일꾼이 먼저 집어가 반영이 늦는다.
    chosen: dict[str, Any] = {}


@router.post("/", status_code=201)
async def create_session(
    body: CreateBody,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """새 회차를 연다. 여는 순간 1단계가 일꾼에게 넘어간다."""
    if body.pending and body.pending not in STEPS:
        raise HTTPException(status_code=400, detail=f"모르는 단계: {body.pending}")
    session_id = secrets.token_hex(8)
    data = _blank(body.axis, user.id, body.pending)
    if body.chosen:
        data["chosen"] = dict(body.chosen)
    db.add(AppSetting(key=f"{KEY_PREFIX}{session_id}", value=json.dumps(data, ensure_ascii=False)))
    await db.commit()
    return await _out(db, session_id, data)


@router.get("/pending")
async def list_pending(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """일꾼이 「무엇을 해야 하나」 물어보는 자리.

    자기 것만 본다 — 계정이 다르면 남의 회차를 집지 않는다.
    """
    rows = (await db.execute(
        select(AppSetting).where(AppSetting.key.like(f"{KEY_PREFIX}%"))
    )).scalars().all()
    jobs = []
    for row in rows:
        try:
            data = json.loads(row.value)
        except json.JSONDecodeError:
            continue
        if data.get("pending") and data.get("owner") == user.id:
            jobs.append({
                "id": row.key[len(KEY_PREFIX):],
                "step": data["pending"],
                "axis": data.get("axis", ""),
                "chosen": data.get("chosen", {}),
            })
    # 오래 기다린 것부터
    jobs.sort(key=lambda j: j["id"])
    return {"jobs": jobs}


@router.get("/latest")
async def latest_prepared(
    axis: str = "",
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """**이어서 열 수 있는** 회차 중 가장 최근 것. 밤에 미리 만들어 둔 것이 먼저다.

    화면을 열 때마다 새 회차를 만들면 그때마다 1단계가 일꾼에게 넘어가 **주제가 다시
    지어진다.** 주소에서 회차 번호가 빠진 채로 들어오면(메뉴·즐겨찾기) 그렇게 됐다
    (2026-09-07 사람 신고 — 새로고침할 때마다 주제가 재생성된다).
    그래서 미리 만들어 둔 것뿐 아니라 **주제 후보가 이미 있는 회차**도 돌려준다.

    **만든 뒤에도 그 회차를 돌려준다** (2026-09-08 사람 신고 — [다시 뽑기] 를 안 눌렀는데
    주제가 또 생성됐다). 전에는 캐러셀까지 만든 회차(`result`)를 빼고 줬는데, 그러면
    하나 만들고 화면을 다시 여는 순간 **더 오래된 회차**가 열려 주제 목록이 통째로
    바뀐 것처럼 보였다. 만든 주제는 `built` 로 [완료] 표시가 되고, 다른 주제를 고르면
    화면이 `reset_from` 으로 `result` 를 지우므로 이어서 쓰면 된다.

    없으면 `id` 가 없는 빈 답을 준다(화면이 그때 빈 회차를 연다).
    """
    rows = (await db.execute(
        select(AppSetting).where(AppSetting.key.like(f"{KEY_PREFIX}%"))
    )).scalars().all()
    best: tuple[str, dict[str, Any], tuple[int, str]] | None = None
    for row in rows:
        try:
            data = json.loads(row.value)
        except json.JSONDecodeError:
            continue
        if data.get("owner") != user.id:
            continue
        # ⚠ 축을 가려야 한다. 안 그러면 일본맛집 화면에 상황별 일본어 회차가 열린다.
        if axis and data.get("axis") != axis:
            continue
        cand = data.get("candidates") or {}
        if not (cand.get("prepared") or cand.get("topics")):
            continue
        # 미리 만들어 둔 것이 먼저, 그다음이 최근 것.
        rank = (1 if cand.get("prepared") else 0, str(data.get("created_at") or ""))
        if best is None or rank > best[2]:
            best = (row.key[len(KEY_PREFIX):], data, rank)
    if not best:
        return {}
    return await _out(db, best[0], best[1])


@router.delete("/old")
async def delete_old(
    axis: str = "",
    hours: int = 24,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """그 축의 **오래된 회차를 지운다**(기본 24시간).

    하루에 세 번 미리 만드는 축(X인용)은 회차가 매일 세 개씩 쌓인다. 지난 것을 놔두면
    화면이 무엇을 이어 열지 헷갈리고 목록도 불어난다 — 2026-09-18 사람 지시
    「각각 24시간 지나면 삭제되게 해놔」.

    ⚠ **자기 회차만** 지운다(`owner`). 남의 계정 것을 건드리면 안 된다.
    ⚠ 축을 비워 두면 **모든 축**이 대상이다. 일꾼은 축을 꼭 준다.

    `created_at` 은 이 파일이 `datetime.now()` 로 적은 **서버 시계**다. 읽을 수 없거나
    나이가 음수면(시계 어긋남) 지우지 않는다 — 잘못 지우는 쪽이 훨씬 나쁘다.
    """
    if hours < 1:
        raise HTTPException(status_code=400, detail="hours 는 1 이상이어야 합니다.")
    rows = (await db.execute(
        select(AppSetting).where(AppSetting.key.like(f"{KEY_PREFIX}%"))
    )).scalars().all()
    now = datetime.now()
    removed: list[str] = []
    for row in rows:
        try:
            data = json.loads(row.value)
        except json.JSONDecodeError:
            continue
        if data.get("owner") != user.id:
            continue
        if axis and data.get("axis") != axis:
            continue
        try:
            made = datetime.fromisoformat(str(data.get("created_at") or ""))
        except ValueError:
            continue
        age = (now - made).total_seconds() / 3600
        if age < 0 or age < hours:
            continue
        await db.delete(row)
        removed.append(row.key[len(KEY_PREFIX):])
    if removed:
        await db.commit()
    return {"removed": removed, "count": len(removed)}


@router.get("/{session_id}")
async def get_session(session_id: str, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """화면이 주기적으로 물어보는 자리.

    로그인을 요구하지 않는다 — id 가 64비트 난수라 주소를 모르면 닿을 수 없고,
    갤러리와 같은 방식이다. 만드는 일은 전부 아래 PATCH 를 거치고 그쪽은 로그인을 본다.
    """
    _, data = await _load(db, session_id)
    return await _out(db, session_id, data)


# 어떤 단계를 다시 고르면 **그 아래는 전부 무효**다. 단계별로 지울 칸을 적어 둔다.
#
# ⚠ 이게 없어서 사고가 났다(2026-09-03): 주제를 바꿔도 앞서 고른 훅이 그대로 남아,
#   「개찰구에서 막혔을 때」 주제에 「계산대가 안 무서워요」 훅이 붙었다. 그대로 만들면
#   표지와 본문이 따로 노는 캐러셀이 나온다. PATCH 는 합치기만 하므로 지우는 길이 필요하다.
# 어느 단계를 지우면 무엇이 날아가는지 — **단계 번호가 아니라 이름**으로 잡는다.
# 축마다 단계 수가 다르기 때문이다(지도 축은 3-3 과 캡션 사이에 CTA1 이 하나 더 있어
# 캡션이 5번이 아니라 6번이다). 번호로 두면 축 하나 늘릴 때마다 조용히 어긋난다.
RESET_BELOW: dict[str, tuple[list[str], list[str]]] = {
    #          지울 chosen 칸     지울 candidates 칸
    "hooks":   (["hook_lines"],   ["hooks"]),
    "images":  (["image_url"],    ["images"]),
    "body":    (["items"],        ["body"]),
    "cta1":    (["cta1"],         ["cta1"]),
    "caption": (["caption"],      ["caption"]),
    "build":   ([],               []),
}

# 화면에 보이는 순서. 1번(주제)은 지우는 대상이 없어 표에 없지만 자리는 지킨다.
STEP_ORDER: dict[str, list[str]] = {
    "지도": ["topics", "hooks", "images", "body", "cta1", "caption", "build"],
}
_DEFAULT_ORDER = ["topics", "hooks", "images", "body", "caption", "build"]


class PatchBody(BaseModel):
    # 사람이 고른 것 (화면이 보낸다)
    chosen: dict[str, Any] | None = None
    # 일꾼이 지은 후보 (PC 가 보낸다)
    candidates: dict[str, Any] | None = None
    # 다음에 일꾼이 할 일. 빈 문자열이면 「사람 차례」다.
    pending: str | None = None
    result: dict[str, Any] | None = None
    error: str | None = None
    # n 단계부터 아래를 무효로 만든다. 앞 단계를 다시 고를 때 함께 보낸다.
    reset_from: int | None = None


@router.patch("/{session_id}")
async def patch_session(
    session_id: str,
    body: PatchBody,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """양쪽이 쓰는 자리 — 화면은 고른 것을, 일꾼은 후보를 올린다.

    통째로 덮지 않고 **준 칸만** 합친다. 화면과 일꾼이 동시에 써도 서로를 지우지 않는다.
    """
    row, data = await _load(db, session_id)
    if data.get("owner") != user.id:
        raise HTTPException(status_code=403, detail="다른 계정의 회차입니다")

    if body.reset_from is not None:
        # 지우기가 먼저다 — 이번에 고른 값(chosen)까지 같이 날리면 안 된다.
        chosen = dict(data.get("chosen", {}))
        cands = dict(data.get("candidates", {}))
        # reset_from 은 화면의 단계 **번호**(1부터)다. 그 번호부터 끝까지 이름으로 바꿔 지운다.
        order = STEP_ORDER.get(str(data.get("axis") or ""), _DEFAULT_ORDER)
        for name in order[max(0, body.reset_from - 1):]:
            drop_chosen, drop_cands = RESET_BELOW.get(name, ([], []))
            for k in drop_chosen:
                chosen.pop(k, None)
            for k in drop_cands:
                cands.pop(k, None)
        data["chosen"] = chosen
        data["candidates"] = cands
        data["result"] = None

    if body.chosen is not None:
        data["chosen"] = {**data.get("chosen", {}), **body.chosen}
    if body.candidates is not None:
        data["candidates"] = {**data.get("candidates", {}), **body.candidates}
    if body.pending is not None:
        if body.pending and body.pending not in STEPS:
            raise HTTPException(status_code=400, detail=f"모르는 단계: {body.pending}")
        data["pending"] = body.pending
        if body.pending:
            data["error"] = ""      # 다시 시키면 지난 실패는 지운다
    made = ""
    if body.result is not None:
        data["result"] = body.result
        # 링크까지 받았으면 그 주제는 제작 완료다. reset_from 이 result 를 지워도 남는다.
        topic = str((data.get("chosen") or {}).get("topic") or "").strip()
        built = list(data.get("built") or [])
        if body.result.get("id") and topic:
            made = topic
            if topic not in built:
                data["built"] = [*built, topic]
    if body.error is not None:
        data["error"] = body.error
        data["pending"] = ""        # 실패했으면 일꾼이 다시 집지 않게 놓아준다

    await _save(db, row, data)
    if made:
        # 회차 밖에도 남긴다 — 밤에 열어 둔 **다른 회차**에서도 [완료] 로 보이게.
        await _mark_built(db, str(data.get("axis") or ""), made)
    return await _out(db, session_id, data)
