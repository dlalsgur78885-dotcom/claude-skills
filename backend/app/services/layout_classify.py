"""레이아웃 낱장 분류 — 키 이름이 아니라 **구조**로 판별한다.

키 이름은 신뢰할 수 없다. 같은 격자가 `2x2` 와 `grid_2x2` 로 갈려 있고, CTA 성격이
`CTA` 와 `phone_mockup` 두 이름으로 존재하며, 한글/영문이 섞여 있다. 사용자가 템플릿을
만들 때 키를 자유롭게 붙이므로 앞으로도 새 이름이 계속 생긴다.

반면 구조는 일관적이라, 구조로 분류하면 새 템플릿도 이름과 무관하게 자동으로 갈린다.

판별 근거 (prod DB 22개 템플릿 / 레이아웃 60개 인스턴스 실측):

  키                  n   background.type       grid    text_slot roles
  fullbg_overlay     10   image_keyword         null    headline,label,subheadline,tag
  썸네일               10   color,gradient        null    headline
  CTA                 9   color,image_keyword   null    (없음)
  phone_mockup        7   color,image_keyword   null    cta_button,headline,subheadline,tag
  single_image        6   image_keyword         null    (없음)
  grid_2x2            5   color,image_keyword   2x2/null cell_*_r0c0 …
  본문                 3   color                 null    body,headline
  cover               2   color                 null    (없음)
  2x2                 2   image_keyword         null    cell_*_r0c0 …
  grid_2x1            2   color                 2x1/null cell_*_r0c0 …
  photo_with_caption  1   image_keyword         null    description,headline
  2x1 / 2x3 / grid_3x3     image_keyword         null    cell_*_r0c0 …

`grid` 필드는 60개 중 **5개**에만 채워져 있어 격자 판별에 쓸 수 없다. 대신
`cell_<무엇>_r{행}c{열}` 역할명이 격자 6종 전부에 일관되게 있어 이것으로 판별하고,
행·열 최댓값에서 격자 크기까지 함께 뽑는다.
"""

from __future__ import annotations

import re
from typing import Any, Literal

Category = Literal["cover", "grid", "cta", "body"]

CATEGORY_LABELS: dict[Category, str] = {
    "cover": "표지",
    "grid": "격자",
    "cta": "CTA",
    "body": "본문·단일",
}

# cell_title_r0c1, cell_description_r2c0 …
_CELL_RE = re.compile(r"^cell_.+_r(\d+)c(\d+)$")

# 본문임을 드러내는 역할 — 표지(headline 만 있는 것)와 가르는 기준
_BODY_ROLES = frozenset({"body", "description"})


def _roles(spec: dict[str, Any]) -> list[str]:
    """레이아웃의 text_slot role 목록. 스키마가 어긋난 항목은 조용히 건너뛴다."""
    slots = spec.get("text_slots")
    if not isinstance(slots, list):
        return []
    return [str(s.get("role")) for s in slots if isinstance(s, dict) and s.get("role")]


def _has_background_image(spec: dict[str, Any]) -> bool:
    """배경이 '실제 사진'인가.

    type 만 보면 안 된다 — CTA 도 image_keyword 인 경우가 있는데 value 가 비어 있어
    배경이 실질적으로 없다. single_image 는 value 에 검색어("snowy train station")가
    들어 있다. 이 value 유무가 CTA 와 단일이미지를 가르는 유일한 구조적 신호다.
    """
    bg = spec.get("background")
    if not isinstance(bg, dict):
        return False
    if bg.get("type") not in ("image_keyword", "image_path"):
        return False
    return bool(str(bg.get("value") or "").strip())


def grid_size(spec: dict[str, Any]) -> tuple[int, int] | None:
    """(행, 열). 격자가 아니면 None.

    채워져 있으면 `grid` 필드를 우선 쓰고, 없으면 cell_*_r{행}c{열} 역할명의
    최댓값에서 뽑는다. 실측상 grid 필드는 60개 중 5개만 채워져 있어 대부분 후자로 간다.
    """
    g = spec.get("grid")
    if isinstance(g, dict) and g.get("rows") and g.get("cols"):
        try:
            return int(g["rows"]), int(g["cols"])
        except (TypeError, ValueError):
            pass

    max_r = max_c = -1
    for role in _roles(spec):
        m = _CELL_RE.match(role)
        if m:
            max_r = max(max_r, int(m.group(1)))
            max_c = max(max_c, int(m.group(2)))
    if max_r < 0:
        return None
    return max_r + 1, max_c + 1


def classify(spec: dict[str, Any]) -> Category:
    """레이아웃 하나를 네 갈래로 분류한다. 순서가 곧 우선순위다."""
    if not isinstance(spec, dict):
        return "body"

    roles = set(_roles(spec))

    # ② 격자 — 표현이 두 가지다. 정식형은 grid 스펙(rows/cols/item_box)에 담기고
    #    셀 텍스트칸이 없다. 펼친 형태는 grid=null 이고 cell_*_r{행}c{열} 텍스트칸을
    #    가진다. grid_size() 가 둘 다 처리하므로 그 결과로 판별한다. 한쪽만 보면
    #    정식형 격자가 "텍스트 없는 장면"으로 새어 CTA 로 오분류된다.
    if grid_size(spec) is not None:
        return "grid"

    # ③ CTA — 두 가지 형태가 있다.
    #    (a) cta_button 역할을 가진 것 (phone_mockup)
    #    (b) 편집할 텍스트가 없고 배경 사진도 없는 것 — 내용이 전부 데코 이미지인 장면
    #        (CTA, cover). 배경 사진이 있으면 그건 단일이미지이므로 ④로 간다.
    if "cta_button" in roles:
        return "cta"
    if not roles and not _has_background_image(spec):
        return "cta"

    # ④ 본문·단일 — 본문 텍스트를 가졌거나, 텍스트 없이 배경 사진만 있는 장면
    if roles & _BODY_ROLES:
        return "body"
    if not roles:
        return "body"  # 여기까지 왔으면 배경 사진이 있는 경우 = single_image

    # ① 표지 — 남은 것은 headline 중심 장면 (썸네일, fullbg_overlay)
    return "cover"


def describe(spec: dict[str, Any]) -> str:
    """UI 뱃지에 쓸 한글 라벨. 격자는 크기까지 붙인다.

    사용자는 격자를 가로×세로로 읽는다(프론트 displayLayoutName 과 같은 규칙).
    내부 저장은 행 우선이므로 표시할 때 뒤집는다.
    """
    cat = classify(spec)
    if cat == "grid":
        size = grid_size(spec)
        if size:
            rows, cols = size
            return f"격자 {cols}×{rows}"
    return CATEGORY_LABELS[cat]
