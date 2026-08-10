"""낱장 숨김 상태 — 유저별로 app_settings 에 JSON 한 줄로 보관한다.

**왜 전용 테이블이 아닌가**: prod 는 Alembic 이 아니라 `Base.metadata.create_all`
로 스키마를 잡는다. 테이블을 늘리면 배포할 때 손으로 만들어 줘야 한다. 숨김 목록은
유저당 많아야 수십 건이라 키/값 한 줄이면 충분하므로, 스키마를 안 늘리는 쪽을 택했다.

**왜 settings_provider 를 안 쓰는가**: 그 모듈은 관리자용 전역 설정 전용이다.
전역 캐시를 들고 있고 값을 os.environ 으로 밀어넣는다 — 유저별 데이터가 거기 섞이면
안 된다. 그래서 AppSetting 테이블만 직접 쓴다.

**"숨김"의 의미**: 낱장 목록에서만 가린다. 템플릿 원본(layouts JSON)은 절대 바뀌지
않으므로, 숨긴 뒤에도 그 템플릿을 세트로 고르는 건 그대로 동작한다.
"""

from __future__ import annotations

import json
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.app_setting import AppSetting

logger = logging.getLogger(__name__)

# AppSetting.key 는 String(100) — "hidden_layouts:36" 정도라 여유롭다.
_KEY_PREFIX = "hidden_layouts:"

# 낱장 하나의 신원. layout_key 는 사용자가 자유 작명하므로 ":" 같은 구분자로 이어
# 붙이면 깨질 수 있다. 그래서 문자열 결합 대신 객체로 저장한다.
HiddenKey = tuple[int, str]


def _key(user_id: int) -> str:
    return f"{_KEY_PREFIX}{user_id}"


def _decode(raw: str) -> set[HiddenKey]:
    """저장된 JSON → {(template_id, layout_key)}. 깨진 값은 빈 집합으로 처리한다.

    숨김은 부가 기능이라, 값이 손상됐다고 목록 조회 자체가 실패하면 안 된다.
    """
    if not raw:
        return set()
    try:
        items = json.loads(raw)
    except (ValueError, TypeError):
        logger.warning("[hidden] 저장값 파싱 실패 — 빈 집합으로 처리")
        return set()
    out: set[HiddenKey] = set()
    if isinstance(items, list):
        for it in items:
            if isinstance(it, dict) and it.get("k") is not None:
                try:
                    out.add((int(it["t"]), str(it["k"])))
                except (TypeError, ValueError, KeyError):
                    continue
    return out


def _encode(keys: set[HiddenKey]) -> str:
    # 정렬해서 저장 — 같은 집합이면 항상 같은 문자열이라 불필요한 쓰기를 줄이고
    # 값을 눈으로 확인하기도 쉽다.
    return json.dumps(
        [{"t": t, "k": k} for t, k in sorted(keys)],
        ensure_ascii=False,
    )


async def get_hidden(db: AsyncSession, user_id: int) -> set[HiddenKey]:
    """이 유저가 숨긴 낱장 집합."""
    row = await db.get(AppSetting, _key(user_id))
    return _decode(row.value if row else "")


async def set_hidden(
    db: AsyncSession, user_id: int, template_id: int, layout_key: str, hidden: bool
) -> set[HiddenKey]:
    """낱장 하나의 숨김을 켜고 끈다. 갱신된 전체 집합을 돌려준다.

    읽고-고쳐-쓰기라 같은 유저가 동시에 여러 번 토글하면 마지막 쓰기가 이긴다.
    한 사람이 한 화면에서 누르는 용도라 실질적인 문제는 아니다.
    """
    row = await db.get(AppSetting, _key(user_id))
    keys = _decode(row.value if row else "")

    entry = (template_id, layout_key)
    if hidden:
        keys.add(entry)
    else:
        keys.discard(entry)

    encoded = _encode(keys)
    if row:
        row.value = encoded
    else:
        db.add(AppSetting(key=_key(user_id), value=encoded))
    await db.commit()
    return keys
