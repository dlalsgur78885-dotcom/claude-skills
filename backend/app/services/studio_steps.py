"""상황별 일본어 원클릭 대시보드 — 한 화면에서 6단계를 끝낸다.

요청서: `docs/process/개발요청_상황별일본어_원클릭대시보드.md` (2026-09-02).

## 제일 중요한 제약 — 규칙의 원본은 지침서 파일이다

여기에 프롬프트·톤·글자 수·개수 규칙을 **베껴 넣지 않는다.** 단계마다 `docs/process` 의
해당 파일을 읽어 **프롬프트에 통째로 실어 보낸다.** 베껴 두면 지침서를 고쳐도 화면은 옛
규칙으로 계속 돌고, 두 벌이 되는 순간 어느 쪽이 맞는지 알 수 없어진다.

이 파일이 아는 것은 **주고받는 JSON 모양**뿐이다(화면이 그려야 하니까). 내용 규칙은
전부 지침서가 정한다.

## 이것은 API 가 아니라 서비스다

한때 이 파일이 라우터였다. 지금은 아니다 — 화면은 **서버**의 `studio_sessions` 를 쓰고,
여기 있는 단계 로직은 codex 가 있는 이 PC 의 일꾼(`services/studio_worker.py`)이
**함수로 직접 부른다.** 그래서 인증도 열쇠도 여기 없다. 밖에서 닿는 문이 아니다.

## 도는 자리

문구는 `codex-sol`, 그림은 Codex CLI 내장 image_gen 이다. 둘 다 **이 기계의 로그인된
Codex 세션**을 쓰므로 codex 가 깔린 곳에서만 돈다(2026-09-02 사람 결정 — 대시보드는 이 PC).
"""

import logging
import re
from datetime import date
from pathlib import Path
from typing import Any

from fastapi import HTTPException
from pydantic import BaseModel


logger = logging.getLogger(__name__)


# backend/app/api/studio.py → 레포 루트 → docs/process
PROCESS_DIR = Path(__file__).resolve().parents[3] / "docs" / "process"

# ── 축 설정 ────────────────────────────────────────────────────────────────
#
# 축마다 지침서·템플릿·낱장 이름·본문 모양이 다르다. 코드에 흩뿌리지 않고 여기 모은다.
# 지도 축을 붙일 때도 여기에 한 줄 더 넣는 것이 먼저다.
#
# ⚠ 낱장 이름은 **글자 그대로** 써야 한다. 한 글자만 달라도 에러가 아니라
#   렌더러가 조용히 첫 낱장으로 폴백한다(캐러셀 419 가 12장 전부 표지로 나온 적이 있다).

COPY_MODEL = "codex-sol"

AXES: dict[str, dict[str, Any]] = {
    "상황별일본어": {
        "guides": {
            "topics":  ["상황별일본어_1단계_주제후보.md", "상황별일본어_2단계_주제선택.md"],
            "hooks":   ["상황별일본어_3-1단계_훅문구.md"],
            "images":  ["상황별일본어_3-2단계_썸네일이미지.md"],
            "body":    ["상황별일본어_3-3단계_본문.md"],
            "caption": ["상황별일본어_5단계_캐프션.md", "솔희_캐러셀기획.md"],
        },
        "history": "상황별일본어_이력.md",
        "keeps": "상황별일본어_보관함.md",
        "drops": "상황별일본어_제외.md",
        "template_id": 80,
        "body_layout": "본문(상황일본어)",
        # 본문 한 줄이 낱장의 어느 칸으로 가는지. 순서가 headline·subtext·body·tag 다.
        "body_fields": ["jp", "reading", "meaning", "situation"],
        "places": 0,          # 실제 장소를 다루지 않는다
        # 표지 배경 후보를 어떻게 뽑는지. 지침서가 정한 값이다.
        "cover_shots": {"person": 5, "scenery": 5},
    },
    "일본맛집": {
        "guides": {
            "topics":  ["일본맛집_1단계_주제후보.md", "일본맛집_2단계_주제선택.md"],
            "hooks":   ["일본맛집_3-1단계_훅문구.md"],
            "images":  ["일본맛집_3-2단계_썸네일이미지.md"],
            "body":    ["일본맛집_3-3단계_본문.md"],
            "caption": ["일본맛집_5단계_캡션.md", "솔희_캐러셀기획.md"],
        },
        "history": "일본맛집_이력.md",
        "keeps": "일본맛집_보관함.md",
        "drops": "일본맛집_제외.md",
        "template_id": 82,
        "body_layout": "본문(장소)",
        # 매장명 → headline / 위치 1줄 → subtext / 특징 4줄 → body. tag 는 안 쓴다.
        "body_fields": ["name", "where", "desc", ""],
        "places": 8,          # 실제 가게 8곳 — place_lookup 으로 확인한 뒤 쓴다
        # 인물 5 + 음식 5(2026-09-09 사람 지시 — 「인물 5장, 주제와 관련된 음식 5장」).
        #   풍경은 안 그린다. 본문 낱장 배경은 **구글 지도의 실제 가게 사진**이라 여기서 그릴 게 아니다.
        "cover_shots": {"person": 5, "food": 5},
        # 2026-09-03 사람 지시 — 「맛집은 하루 10개, 오전 4시에 돌려」. 상황별일본어와
        # 달리 이 축만 새벽 한 번이다(9시 전달까지 다섯 시간 여유 — 주제당 5~7분×10개).
        # 안 적으면 전역 STUDIO_PREPARE_AT 을 쓴다 — `studio_worker._maybe_start_nightly` 참고.
        "prepare_at": ["04:00"],
    },
    "지도": {
        "guides": {
            "topics":  ["지도_1단계_주제후보.md", "지도_2단계_주제선택.md"],
            "hooks":   ["지도_3-1단계_훅문구.md"],
            "images":  ["지도_3-2단계_썸네일이미지.md"],
            "body":    ["지도_3-3단계_본문.md"],
            "cta1":    ["지도_3-4단계_CTA1문구.md"],
            "caption": ["지도_5단계_캡션.md", "솔희_캐러셀기획.md"],
        },
        "history": "지도_이력.md",
        "keeps": "지도_보관함.md",
        "drops": "지도_제외.md",
        "template_id": 81,
        "body_layout": "본문_지도",
        # 훅이 2줄 고정이라 표지가 줄 수로 갈리지 않는다(지도_3-1단계).
        "cover_layout": "표지_지도",
        # 매장명 → headline / 📍위치 → subtext / 특징 3~4줄 → body. tag 는 안 쓴다.
        "body_fields": ["name", "where", "desc", ""],
        "places": 3,          # 지도_3-3단계 「매장 3곳」
        # ⚠ 이 축은 표지를 **그리지 않는다.** 트래블어시 가이드 화면의 진짜 지도를
        #   `capture_page` 로 찍어 쓴다(지도_3-2단계 2026-08-26 — generate_image 폐기).
        "cover_shots": {},
        # 이 축에만 있는 것 둘 —
        # ① 재료가 트래블어시 가이드에서 온다(주제도 장소도 지어내지 않는다).
        "guide_source": True,
        # ② 3-3 다음에 CTA1 문구 단계가 하나 더 있다(다른 두 축엔 없다).
        "cta1": True,
        # 2026-09-04 사람 지시 — 「작업은 전날 22:00 시에 진행해」.
        # 주제 10개에 20분이라 22:20 이면 끝난다. 상황별일본어(23:00)와 겹치지 않는다.
        "prepare_at": ["22:00"],
    },
}

DEFAULT_AXIS = "상황별일본어"


def axis_conf(axis: str | None) -> dict[str, Any]:
    conf = AXES.get((axis or "").strip() or DEFAULT_AXIS)
    if not conf:
        raise HTTPException(status_code=400, detail=f"모르는 축: {axis}")
    return conf




# ─── 지침서 읽기 ────────────────────────────────────────────────────────────

def _read_doc(name: str) -> str:
    path = PROCESS_DIR / name
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        logger.warning(f"[studio] 지침서를 찾지 못했습니다: {name}")
        return ""


# 회차 기록은 **규칙이 아니다.** 지침서를 통째로 실으면 그 안의 지난 회차 장면 목록이
# 프롬프트에서 제일 구체적인 예시가 되어, 모델이 그것을 베껴 **이전 주제의 그림**이
# 나온다(2026-09-08 사람 신고). 문서에는 사람이 보게 그대로 두고, 프롬프트에 실을 때만
# 이 표시 사이를 들어낸다. 끝 표시가 없으면 파일 끝까지다.
CUT_OPEN = "<!-- 기록: 프롬프트 제외 시작 -->"
CUT_CLOSE = "<!-- 기록: 프롬프트 제외 끝 -->"
_CUT = re.compile(f"{re.escape(CUT_OPEN)}.*?(?:{re.escape(CUT_CLOSE)}|\\Z)", re.S)


def _rules_for(step: str, axis: str = DEFAULT_AXIS) -> str:
    """그 단계의 규칙 원본을 이어 붙인다(회차 기록은 빼고 — `_CUT`)."""
    parts = []
    for name in axis_conf(axis)["guides"].get(step, []):
        text = _CUT.sub("", _read_doc(name))
        if text.strip():
            parts.append(f"===== 규칙 원본: {name} =====\n{text}")
    if not parts:
        raise HTTPException(status_code=500, detail=f"{step} 단계 지침서를 읽지 못했습니다")
    return "\n\n".join(parts)


# ─── 이력 · 보관함 ──────────────────────────────────────────────────────────

_ROW = re.compile(r"^\|\s*(\d+)\s*\|\s*([^|]*?)\s*\|\s*(.+?)\s*\|\s*(.*?)\s*\|\s*$")


def _history_topics(axis: str = DEFAULT_AXIS) -> list[str]:
    """제작 이력의 주제들. 후보에서 빼야 하는 목록이다."""
    out = []
    for line in _read_doc(axis_conf(axis)["history"]).splitlines():
        m = _ROW.match(line.strip())
        if m:
            out.append(m.group(3))
    return out


def _bullets(name: str) -> list[str]:
    """`- 주제` 줄만 뽑는다. 보관함과 제외 목록이 같은 모양이다."""
    out = []
    for line in _read_doc(name).splitlines():
        line = line.strip()
        if not line.startswith("- "):
            continue
        topic = line[2:].strip()
        # 예전에 빈 목록 표시로 적던 자리표시자. 읽어서 다시 쓰는 바람에 **진짜 주제처럼
        # 눌러앉아** 화면 목록에 떴다(2026-09-03). 이제 쓰지도 않고 읽지도 않는다.
        if not topic or topic == "(비어 있음)":
            continue
        out.append(topic)
    return out


def _write_bullets(name: str, header: list[str], topics: list[str]) -> None:
    # 자리표시자를 쓰지 않는다 — 다음에 읽을 때 주제로 섞인다(위 _bullets 주석).
    body = header + [f"- {t}" for t in topics]
    (PROCESS_DIR / name).write_text("\n".join(body) + "\n", encoding="utf-8")


def _keeps(axis: str = DEFAULT_AXIS) -> list[str]:
    """보관함 — 이번엔 안 쓰지만 버리지 않은 주제. 이력과 **별개**다
    (이력은 「실제로 만든 주제」만 쌓는 자리라 섞으면 안 된다)."""
    return _bullets(axis_conf(axis)["keeps"])


def _write_keeps(topics: list[str], axis: str = DEFAULT_AXIS) -> None:
    _write_bullets(axis_conf(axis)["keeps"], [
        f"# {axis} — 보관함",
        "",
        "1단계에서 **[보관]** 을 누른 주제. 이번 회차에 안 썼을 뿐 버린 것이 아니라,",
        "다음 회차 1단계에 **다시 나온다.** 실제로 만든 주제만 쌓는 제작 이력과는 별개다.",
        "",
        "화면(`/studio/ja-situations`)이 자동으로 갱신한다.",
        "",
    ], topics)


def _drops(axis: str = DEFAULT_AXIS) -> list[str]:
    """제외 목록 — 1단계에서 **[삭제]** 를 누른 주제. 보관함의 반대다.

    보관함이 「다음에도 보여 달라」면 이쪽은 「다음에는 보이지 마라」다. 이력과도 별개다
    (이력은 만든 주제, 이쪽은 안 만들기로 한 주제)."""
    return _bullets(axis_conf(axis)["drops"])


def _write_drops(topics: list[str], axis: str = DEFAULT_AXIS) -> None:
    _write_bullets(axis_conf(axis)["drops"], [
        f"# {axis} — 제외 목록",
        "",
        "1단계에서 **[삭제]** 를 누른 주제. 다음 회차 후보에서 **다시 나오지 않는다.**",
        "마음이 바뀌면 이 파일에서 그 줄을 지우면 그만이다.",
        "",
        "화면(`/studio/ja-situations`)이 자동으로 갱신한다.",
        "",
    ], topics)


def _norm(topic: str) -> str:
    """견줄 때 쓰는 납작한 문구 — 갯수·기호·띄어쓰기가 달라도 같은 주제로 본다.

    제외 목록을 **글자 그대로** 비교하면 샌다. 끝에 붙는 갯수는 가이드에서 오는 값이라
    회차마다 변해서, 지워 둔 「…디저트집 22곳」 이 다음 회차엔 「…디저트집 23곳」 으로
    와 다른 주제로 통과했다(2026-09-07 사람 신고 — 지운 주제가 다시 나온다).
    """
    return re.sub(r"[^0-9A-Za-z가-힣ぁ-んァ-ヶ一-龥]", "", re.sub(r"\d+\s*곳", "", topic))


# 주제 문구에서 뜻을 안 나르는 말. 낱말 하나가 통째로 이것이면 버린다
# (낱말 안쪽을 지우면 「할인」이 「인」이 되는 식으로 망가진다 — 반드시 토큰째 견준다).
_STOP = {
    "일본어", "일본말", "일본", "표현", "문장", "한마디", "말투", "회화",
    "때", "경우", "상황", "모음", "정리", "필요", "알아야", "알아두면", "알면",
    "자주", "바로", "정말", "진짜", "자연스러운", "유용한", "쓰는", "쓸", "하는",
    "듣는", "위한", "위해", "이런", "그런", "무조건", "꼭",
}
# 낱말 끝에 붙어 같은 말을 다르게 보이게 하는 조사·어미.
_TAIL = re.compile(r"(에서|에게|한테|으로|하고|이랑|까지|부터|보다|의|을|를|이|가|은|는|에|로|와|과|도|만|랑|할|한|하|되)$")


def _content_words(topic: str) -> frozenset[str]:
    """주제에서 **뜻을 나르는 낱말만** 남긴다.

    이 축은 모델이 회차마다 문구를 새로 지어서 어순·조사만 바뀐 같은 주제가 돌아온다.
    실제로 제외 목록에 「따로 계산할 때 필요한 일본어」와 「계산을 따로 할 때 쓰는 일본어」가
    함께 쌓였다(2026-09-07 사람 신고 — 지운 주제가 계속 생성된다). 둘 다 {따로, 계산} 이다.
    """
    words = set()
    for raw in re.split(r"[^0-9A-Za-z가-힣ぁ-んァ-ヶ一-龥]+", topic):
        w = raw
        # 꼬리가 겹쳐 붙는다 — 「참배하는」은 `는` 을 떼야 「참배하」, 한 번 더 떼야 「참배」다.
        for _ in range(2):
            cut = _TAIL.sub("", w)
            if len(cut) < 2:   # 떼서 한 글자가 되면 뗀 것이 조사가 아니었다(「따로」의 `로`)
                break
            w = cut
        if len(w) >= 2 and w not in _STOP:
            words.add(w)
    return frozenset(words)


def _same_words(a: frozenset[str], b: frozenset[str]) -> bool:
    """낱말이 같으면 같은 주제로 본다. 어순·조사만 다른 것을 여기서 잡는다."""
    if not a or not b:
        return False
    return a == b or (len(a & b) >= 2 and len(a & b) / len(a | b) >= 0.7)


def _not_dropped(items: list[Any], drops: list[str]) -> list[dict[str, Any]]:
    """제외 목록에 있는 주제를 뺀다. 프롬프트로 막아도 그대로 오는 일이 있다."""
    banned = {_norm(d) for d in drops}
    banned_words = [w for w in (_content_words(d) for d in drops) if w]
    out: list[dict[str, Any]] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        topic = str(it.get("topic") or "")
        if _norm(topic) in banned:
            continue
        if any(_same_words(_content_words(topic), w) for w in banned_words):
            logger.info(f"[studio] 지운 주제와 낱말이 같아 뺍니다: {topic}")
            continue
        out.append(it)
    return out


async def _drop_lookalikes(items: list[dict[str, Any]], seen: list[str],
                           axis: str) -> list[dict[str, Any]]:
    """말이 아예 달라도 **배우는 내용이 같은** 후보를 모델에게 물어 걸러낸다.

    낱말 비교(`_same_words`)는 어순·조사까지만 잡는다. 「옷가게에서 사이즈 묻는 일본어」와
    「옷 크기 물어볼 때 쓰는 표현」처럼 겹치는 낱말이 없는 같은 주제는 사람이 봐야 안다.
    이 축은 장소 조회가 없어 호출 하나가 더 붙어도 느려지지 않는다.

    ⚠ 판정에 실패하면 **후보를 그대로 돌려준다.** 여기서 던지면 지운 주제 하나 때문에
    회차 전체가 빈손이 된다 — 걸러지지 않는 쪽이 아무것도 안 나오는 쪽보다 낫다.
    """
    if not items or not seen:
        return items

    from app.agents.llm_client import llm_json

    prompt = "\n".join([
        "아래 「낸 후보」 중에서 「이미 있는 주제」와 **사실상 같은 주제**를 모두 골라라.",
        "말이 달라도 독자가 배우는 내용이 같으면 같은 주제다 —",
        "예) 「옷가게에서 사이즈 묻는 일본어」와 「옷 크기 물어볼 때 쓰는 표현」은 같다.",
        "겹치는 것이 없으면 빈 배열을 준다. 설명 없이 JSON 만 돌려준다.",
        "",
        "===== 이미 있는 주제 =====",
        *(f"- {t}" for t in seen),
        "",
        "===== 낸 후보 =====",
        *(f"- {str(it.get('topic') or '')}" for it in items),
        "",
        "===== 돌려줄 형식 =====",
        '{"duplicates": [{"topic": "낸 후보 문구 그대로", "same_as": "이미 있는 주제 문구"}]}',
    ])
    schema = _obj({"duplicates": _arr(_obj({"topic": {"type": "string"},
                                            "same_as": {"type": "string"}}))})
    try:
        data = await llm_json(model=COPY_MODEL,
                              messages=[{"role": "user", "content": prompt}],
                              json_schema=schema)
    except Exception as exc:
        logger.warning(f"[studio] 겹치는 주제 판정에 실패해 그냥 갑니다: {exc}")
        return items
    if isinstance(data, dict) and "raw" in data:
        logger.warning("[studio] 겹치는 주제 판정이 JSON 이 아니라 그냥 갑니다")
        return items

    dup = {}
    for d in _list_from(data, "duplicates", "items"):
        if isinstance(d, dict) and d.get("topic"):
            dup[_norm(str(d["topic"]))] = str(d.get("same_as") or "")
    if not dup:
        return items

    out = []
    for it in items:
        topic = str(it.get("topic") or "")
        hit = dup.get(_norm(topic))
        if hit is not None:
            logger.info(f"[studio] 이미 있는 주제와 같아 뺍니다: {topic} ← {hit}")
            continue
        out.append(it)
    return out


def _button_key(rows: list[dict[str, Any]], topic: str) -> tuple[str, str, str] | None:
    """주제 문구 → (가이드ID, 버튼, 지역). 못 찾으면 None.

    지도 축은 문구를 모델이 회차마다 새로 쓴다 — 같은 버튼이라도 글자가 달라지므로
    문구만 견주면 지운 주제가 그대로 돌아온다. 이 축에서 주제의 진짜 신원은 **버튼**이다.
    `_resolve_button` 의 되찾기 규칙과 같되, 없으면 던지지 않고 None 을 준다
    (제외 목록에는 가이드에서 사라진 옛 버튼이 섞여 있을 수 있다).
    """
    hits = [r for r in rows if r.get("button") and r["button"] in topic]
    if not hits:
        # 버튼 이름이 문구에 통째로 박히지 않는 일이 흔하다 — 「케이크·디저트」 버튼이
        # 「…케이크 하나 때문에 … 디저트집 22곳」 으로 풀어 쓰인다. 가운뎃점으로 쪼갠
        # 조각이 **전부** 들어 있으면 그 버튼으로 본다.
        hits = [r for r in rows if r.get("button")
                and all(p and p in topic for p in re.split(r"[·/,]", r["button"]))]
    if not hits:
        return None
    # 걸린 것 중 **가장 긴 버튼**을 고른다 — 「빵집」과 「동네 빵집」이 함께 걸리면 좁은 쪽이 맞다.
    row = max(hits, key=lambda r: len(r["button"]))
    region = next((x["name"] for x in (row.get("regions") or []) if x["name"] in topic), "")
    return (row["guide_id"], row["button"], region)


def _append_history(topic: str, carousel_id: int, axis: str = DEFAULT_AXIS) -> bool:
    """제작 이력에 한 줄 붙이고 카운트를 갱신한다.

    지금은 봇이 손으로 적는다. 화면이 대신 적어 줘야 다음 회차 1단계가 그대로 읽는다
    (요청서 「문구 생성에서 지켜야 할 것」).
    """
    path = PROCESS_DIR / axis_conf(axis)["history"]
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return False

    lines = text.splitlines()
    last_row = -1
    last_no = 0
    for i, line in enumerate(lines):
        m = _ROW.match(line.strip())
        if m:
            last_row = i
            last_no = int(m.group(1))
    if last_row < 0:
        return False

    lines.insert(
        last_row + 1,
        f"| {last_no + 1} | {date.today().isoformat()} | {topic} | {carousel_id} |",
    )
    # "## 제작 목록 (13 / 30)" 의 숫자도 같이 올린다.
    for i, line in enumerate(lines):
        if line.startswith("## 제작 목록"):
            lines[i] = re.sub(r"\(\s*\d+\s*/", f"({last_no + 1} /", line)
            break
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return True


# ─── codex sol 로 문구 짓기 ─────────────────────────────────────────────────

async def _ask(step: str, task: str, shape: str, extra: str = "",
               schema: dict | None = None, axis: str = DEFAULT_AXIS) -> Any:
    """그 단계 지침서 + 할 일 + 받을 JSON 모양을 함께 넘긴다.

    codex 는 지침서를 읽지 않는다 — 규칙을 프롬프트에 실어야 쓸 수 있는 것이 나온다.

    ⚠ `schema` 를 반드시 준다. 프롬프트로 "이 형식으로 줘" 라고만 하면 모델이 **지침서의
    대화 흐름을 따라가** 엉뚱한 것을 낸다 — 실제로 주제 10개 대신 「그중 추천 3개」가
    `{주제, 왜}` 라는 한글 칸으로 와서 화면이 텅 비었다(2026-09-02). 스키마는 CLI 가 강제한다.
    """
    from app.agents.llm_client import llm_json

    prompt = "\n\n".join(filter(None, [
        _rules_for(step, axis),
        "===== 할 일 =====",
        task,
        extra,
        "===== 돌려줄 형식 =====",
        shape,
        "위 규칙 원본의 개수·줄 수·글자 수·형식·톤을 그대로 지켜라. "
        "설명이나 인사말을 붙이지 말고 JSON 만 돌려준다.",
    ]))

    result = await llm_json(model=COPY_MODEL, messages=[{"role": "user", "content": prompt}],
                            json_schema=schema)
    if isinstance(result, dict) and "raw" in result:
        raise HTTPException(status_code=502, detail="문구를 JSON 으로 받지 못했습니다. 다시 시도해 주세요.")
    return result


def _list_from(data: Any, *names: str) -> list:
    """받은 JSON 에서 목록을 꺼낸다.

    모델은 형식을 알려줘도 **칸 이름을 바꿔 낼 때가 있다.** 실제로 `items` 대신 다른
    이름으로 와서 후보 10개가 통째로 버려졌다(2026-09-02, 화면에는 빈 목록만 떴다).
    이름이 어긋나도 목록이 하나뿐이면 그것을 쓴다 — 알맹이를 버리는 것보다 낫다.
    """
    if isinstance(data, list):
        return data
    if not isinstance(data, dict):
        return []
    for name in names:
        v = data.get(name)
        if isinstance(v, list):
            return v
    lists = [v for v in data.values() if isinstance(v, list)]
    if len(lists) == 1:
        logger.info(f"[studio] 기대한 칸({names[0]})이 없어 목록 하나를 대신 씁니다")
        return lists[0]
    return []


def _obj(props: dict) -> dict:
    """구조화 출력이 요구하는 모양으로 감싼다 — 모든 칸 required, 추가 칸 금지."""
    return {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}


def _arr(item: dict) -> dict:
    return {"type": "array", "items": item}


S_TOPICS = _obj({"items": _arr(_obj({"topic": {"type": "string"}, "why": {"type": "string"}}))})
S_HOOKS = _obj({
    "three": _arr(_obj({"lines": _arr({"type": "string"})})),
    "two": _arr(_obj({"lines": _arr({"type": "string"})})),
})
S_BODY = _obj({"items": _arr(_obj({
    "jp": {"type": "string"}, "reading": {"type": "string"},
    "meaning": {"type": "string"}, "situation": {"type": "string"},
}))})
S_CAPTION = _obj({"caption": {"type": "string"}})

# 일본맛집: 먼저 **가게 이름만** 받는다. 확인 전에 설명을 짓게 하면 그럴듯한 거짓이 섞인다.
S_PLACE_NAMES = _obj({"places": _arr({"type": "string"})})
# 실존 확인만으론 못 거른다 — 주제에 맞는 가게인지 한 번 더 가린다(`_screen_places`).
S_SCREEN = _obj({"items": _arr(_obj({
    "n": {"type": "string"},       # 아래 목록의 번호
    "fit": {"type": "boolean"},    # 주제에 맞나
    "why": {"type": "string"},     # 아니라면 왜
}))})
# 확인된 사실을 주고 나서 문구를 받는다.
S_PLACE_BODY = _obj({"items": _arr(_obj({
    "name": {"type": "string"},   # 매장명 → headline
    "where": {"type": "string"},  # 📍위치 1줄 → subtext
    "desc": {"type": "string"},   # 특징 4줄 → body
}))})
def s_image_prompts(kinds: list[str]) -> dict:
    """표지 사진 프롬프트 — 종류는 축마다 다르다(`AXES[축].cover_shots`).

    상황별일본어는 인물·풍경, 일본맛집은 인물·음식이다. 안 그리는 종류를 스키마에 두면
    `_obj` 가 전부 required 로 잡아 모델이 빈 칸을 억지로 채운다.
    """
    return _obj({k: _arr({"type": "string"}) for k in kinds})

# 지도: 주제는 **가이드 버튼에서만** 나온다. 그래서 모델에게 지어내게 하지 않고,
# 실제 버튼 목록을 주고 「어느 버튼을, 뭐라고 부를지」만 고르게 한다.
S_GUIDE_TOPICS = _obj({"items": _arr(_obj({
    "topic": {"type": "string"},      # 사람이 볼 주제 문구 (끝에 「…N곳」)
    "why": {"type": "string"},
    "guide_id": {"type": "string"},   # 어느 가이드의
    "button": {"type": "string"},     # 어느 상단 버튼인지 — 그대로 옮겨 적는다
    # 그 버튼 전체가 아니라 **한 지역만** 쓸 때 그 지역 이름. 안 좁히면 빈 문자열이다
    # (2026-09-04 사람 지시 — 「가이드 + 지역으로도 주제 생성 가능하도록」).
    "region": {"type": "string"},
}))})
# 지도 3-4 CTA1 — 세 칸이 각각 다른 슬롯으로 간다(지도_3-4단계 2026-08-26).
S_CTA1 = _obj({
    "headline": {"type": "string"},   # 2줄 강조
    "subtext": {"type": "string"},    # 1줄, **수량 필수**
    "body": {"type": "string"},       # 2줄 팔로우 유도, 틀 고정
})


# ─── 1단계 — 주제 후보 ──────────────────────────────────────────────────────

async def get_context(axis: str = DEFAULT_AXIS) -> dict[str, Any]:
    from app.services import codex_image
    conf = axis_conf(axis)
    return {
        "history": _history_topics(axis),
        "keeps": _keeps(axis),
        "codex_available": codex_image.is_available(),
        "template_id": conf["template_id"],
    }


async def _guide_topics(axis: str, history: list[str], keeps: list[str],
                        drops: list[str]) -> list[dict[str, Any]]:
    """지도 축의 주제 후보 — **트래블어시 가이드 버튼에서만** 만든다.

    `지도_1단계_주제후보.md` 가 정한 것을 그대로 지킨다:
      · 가이드 데이터를 읽어서 찾는다. **기억으로 짜지 않는다.**
      · 카테고리는 **상단 버튼**에 있는 것만 (= `composition`).
      · 여러 가이드를 가로질러 10개를 뽑는다.
      · 주제 문구 끝에 그 버튼의 장소 갯수를 넣는다 — 「…실내 놀이터 90곳」.

    그래서 모델은 **지어내지 않고** 아래 진짜 목록에서 고르고 문구만 다듬는다.
    30곳 미만인 버튼은 지침서가 「사람에게 언급한다」고 한 자리라 표시해 둔다.
    """
    from app.services import travel_guide

    rows = await travel_guide.all_buttons()
    if not rows:
        raise RuntimeError("트래블어시 가이드를 읽지 못했습니다.")

    # 사람이 [삭제] 한 주제는 **버튼째** 메뉴에서 뺀다. 문구로만 막으면 같은 버튼이
    # 다른 문장으로 돌아온다 — 이 축은 모델이 문구를 회차마다 새로 쓰기 때문이다.
    # 지역까지 좁혀 지운 주제는 그 지역만 뺀다(버튼 전체를 봉인할 일은 아니다).
    banned = {k for k in (_button_key(rows, d) for d in drops) if k}
    offer = [
        {**r, "regions": [x for x in (r.get("regions") or [])
                          if (r["guide_id"], r["button"], x["name"]) not in banned]}
        for r in rows
        if (r["guide_id"], r["button"], "") not in banned
    ]
    if not offer:
        raise RuntimeError("제외 목록이 가이드 버튼을 전부 덮었습니다 — 제외 목록을 손봐야 합니다.")

    menu = "\n".join(
        f"- guide_id={r['guide_id']} | 가이드「{r['guide_name']}」 | 버튼「{r['button']}」"
        f" | 지역={r.get('region') or '전국'} | {r['n']}곳"
        + ("  ⚠30곳 미만" if r["n"] < 30 else "")
        + ("\n    · 지역별: " + " · ".join(f"{x['name']} {x['n']}곳" for x in r["regions"])
           if r.get("regions") else "")
        for r in offer
    )
    data = await _ask(
        "topics",
        "이번 회차의 주제 후보를 지침서가 정한 개수만큼 고르라.",
        '{"items": [{"topic": "주제", "why": "왜", "guide_id": "가이드ID", "button": "버튼이름", '
        '"region": "지역(안 좁히면 빈 문자열)"}]}',
        extra="\n".join(filter(None, [
            "===== 고를 수 있는 것 — 트래블어시 가이드의 상단 버튼 =====",
            menu,
            "⚠ 이 목록에 **없는** 가이드·버튼을 만들어 내지 마라. `guide_id` 와 `button` 은 "
            "위 줄에서 **글자 그대로** 옮겨 적는다(한 글자라도 다르면 장소를 못 찾는다).",
            "⚠ 주제 문구 끝에 그 버튼의 장소 갯수를 넣어라 — 예) 「…실내 놀이터 90곳」. "
            "숫자는 위에 적힌 값 그대로 쓴다.",
            "⚠ 지역을 앞에 붙일 때는 **위 `지역=` 값만** 쓴다. 가이드 이름으로 짐작하지 마라 "
            "— 이름에 「busan」 이 들어가도 장소는 전국에 흩어져 있을 수 있다(실제로 그렇다). "
            "`지역=전국` 이면 「전국」이라고 쓰거나 지역을 아예 붙이지 않는다.",
            "⚠ **버튼을 한 지역으로 좁혀서 주제를 낼 수도 있다.** 그때는 `region` 에 위 "
            "「지역별:」 줄에 있는 이름을 **글자 그대로** 적고, 주제 문구의 숫자는 버튼 전체가 "
            "아니라 **그 지역 갯수**를 쓴다 — 예) 「지역별: 도쿄 24곳」 이면 「도쿄 — … 24곳」. "
            "일본 지역도 국내와 똑같이 쓸 수 있다. 「지역별:」 에 없는 지역은 만들어 내지 마라.",
            "좁히지 않을 때는 `region` 을 빈 문자열로 둔다. "
            "**어느 지역을 앞세울지는 위 지침서가 정한다** — 여기서 임의로 섞거나 몰지 마라.",
            "한 가이드에 몰지 말고 여러 가이드를 가로질러 고른다.",
            ("===== 이미 만든 주제 (제외) =====\n" + "\n".join(f"- {t}" for t in history)) if history else "",
            ("===== 사람이 [삭제] 한 주제 (다시 내지 마라) =====\n"
             + "\n".join(f"- {t}" for t in drops)) if drops else "",
            ("===== 보관한 주제 (겹치지 않게) =====\n" + "\n".join(f"- {t}" for t in keeps)) if keeps else "",
        ])),
        schema=S_GUIDE_TOPICS, axis=axis,
    )

    # 모델이 목록에 없는 것을 적었으면 버린다 — 그대로 두면 3-3 에서 장소가 0곳이 된다.
    ok = {(r["guide_id"], r["button"]): r for r in offer}
    items = []
    for it in _list_from(data, "items", "topics", "candidates"):
        if not isinstance(it, dict):
            continue
        key = (str(it.get("guide_id") or "").strip(), str(it.get("button") or "").strip())
        hit = ok.get(key)
        if not hit:
            logger.warning(f"[studio] 가이드에 없는 버튼이라 뺍니다: {key}")
            continue
        want = str(it.get("region") or "").strip()
        # 지운 것을 그래도 적어 왔으면 버린다. 지역만 지운 버튼이 여기서 걸린다
        # (메뉴에서 통째로 뺀 것은 버튼 전체를 지운 경우뿐이다).
        if (key[0], key[1], want) in banned:
            logger.warning(f"[studio] 사람이 [삭제] 한 주제라 뺍니다: {key} {want}")
            continue
        # 지역까지 좁힌 주제면 갯수도 **그 지역의 것**이다. 없는 지역을 적었으면
        # 버튼 전체로 되돌린다 — 주제만 지역을 말하고 장소는 전국이면 거짓이 된다.
        picked = _region_row(hit, want)
        items.append({**it, "guide_id": key[0], "button": key[1],
                      "guide_name": hit["guide_name"], **picked})
    return items


def _region_row(row: dict[str, Any], region: str) -> dict[str, Any]:
    """버튼 한 줄을 그 지역으로 좁힌 값 — `region`·`n`·`anchor`.

    지역을 안 좁혔거나(빈 문자열) 그 버튼에 없는 지역이면 **버튼 전체**를 그대로 쓴다.
    """
    for r in row.get("regions") or []:
        if region and r["name"] == region:
            return {"region": region, "n": int(r["n"]), "anchor": r.get("anchor") or ""}
    if region:
        logger.warning(f"[studio] 버튼 「{row.get('button')}」 에 없는 지역이라 뺍니다: {region}")
    return {"region": "", "n": int(row.get("n") or 0), "anchor": ""}


async def make_topics(axis: str = DEFAULT_AXIS, *, need: int = 0) -> dict[str, Any]:
    """주제 후보를 짓는다.

    `need` 를 주면 **보관해 둔 주제가 그만큼 있을 때 새로 짓지 않는다**
    (2026-09-09 사람 지시 — 「보관된 주제가 10개가 넘으면 후보 재생성 필요없어」).
    미리 만들기가 쓰는 길이다. 새 후보는 그날 쓰이지도 않으면서 주제마다 가게 8곳을
    조회해 **사진 API 하루 쿼터를 태운다** — 그래서 23개를 돌던 날 사진 후보가 전부
    한 장뿐이었다. 화면의 [다시 뽑기] 는 사람이 새 후보를 원해 누른 것이라 `need` 없이
    부른다(그때는 늘 짓는다).
    """
    history = _history_topics(axis)
    keeps = _keeps(axis)
    drops = _drops(axis)

    if need and len(keeps) >= need:
        logger.info(f"[studio] 보관 주제가 {len(keeps)}개 — 새 후보는 짓지 않습니다")
        return {"kept": keeps, "dropped": drops, "items": []}

    if axis_conf(axis).get("guide_source"):
        items = _not_dropped(await _guide_topics(axis, history, keeps, drops), drops)
        return {"kept": keeps, "dropped": drops, "items": items}

    data = await _ask(
        "topics",
        "이번 회차의 주제 후보를 지침서가 정한 개수만큼 지어라.",
        '{"items": [{"topic": "주제", "why": "왜 이 주제인지 한 줄"}]}',
        extra="\n".join(filter(None, [
            "===== 이미 만든 주제 (제외 대상) =====",
            "\n".join(f"- {t}" for t in history) or "- (없음)",
            "이 목록에 있는 주제는 후보에 넣지 마라. 결이 겹치는 것도 피한다.",
            ("===== 사람이 [삭제] 한 주제 (다시 내지 마라) =====\n"
             + "\n".join(f"- {t}" for t in drops)
             + "\n마음에 안 들어 뺀 주제다. 같은 것도, 결이 겹치는 것도 다시 내지 마라.") if drops else "",
            ("===== 보관한 주제 (다음 회차에 다시 보여줄 것) =====\n"
             + "\n".join(f"- {t}" for t in keeps)
             + "\n이 주제들과 겹치지 않게 새 후보를 뽑아라.") if keeps else "",
        ])),
        schema=S_TOPICS, axis=axis,
    )
    items = _list_from(data, "items", "topics", "candidates")
    # 프롬프트로 막아도 같은 주제가 그대로 오는 일이 있다. 두 번 거른다 —
    # ① 갯수·기호·띄어쓰기·어순·조사만 다른 것(`_norm`·`_content_words`)
    items = _not_dropped(items, drops)
    # ② 말은 다른데 내용이 같은 것. 지운 주제와 이미 만든 주제를 함께 견준다.
    items = await _drop_lookalikes(items, drops + history, axis)
    return {"kept": keeps, "dropped": drops, "items": items}


def exclude_topic(topic: str, axis: str = DEFAULT_AXIS) -> None:
    """그 주제를 **다시 내지 않는다** — 보관함에서 빼고 제외 목록에 올린다.

    2026-09-09 사람 지시 — 「식당 8곳을 못 찾으면 그 주제는 제외하고 다른 주제로 찾아라.
    나한테 주는 주제는 장소가 8개 이상인 것이어야 한다」. 미리 만들기가 부른다.

    ⚠ 되돌리는 법은 사람 손이다 — `docs/process/<축>_제외.md` 에서 그 줄을 지우면 다시 나온다.
    """
    t = (topic or "").strip()
    if not t:
        return
    keeps = _keeps(axis)
    if t in keeps:
        _write_keeps([k for k in keeps if k != t], axis)
    drops = _drops(axis)
    if t not in drops:
        _write_drops([*drops, t], axis)


class KeepBody(BaseModel):
    topic: str
    keep: bool  # True=[보관] 다시 보여준다 / False=[삭제] 제외 목록으로 보낸다


async def toggle_keep(body: KeepBody) -> dict[str, Any]:
    """[보관] 은 보관함에 남겨 다음 회차에 다시 나오게 한다.

    [삭제] 는 제외 목록에 쌓아 **다음 회차에도 안 나오게** 한다(2026-09-04 사람 요청).
    이력은 「실제로 만든 주제」만 쌓는 자리라 안 고른 후보를 적을 수 없어, 마음에 안 든
    주제가 회차마다 다시 올라왔다.
    """
    keeps = _keeps()
    drops = _drops()
    topic = body.topic.strip()
    if body.keep:
        if topic and topic not in keeps:
            keeps.append(topic)
    else:
        keeps = [t for t in keeps if t != topic]
        if topic and topic not in drops:
            drops.append(topic)
            _write_drops(drops)
    _write_keeps(keeps)
    return {"keeps": keeps, "drops": drops}


# ─── 2단계 — 훅 문구 ────────────────────────────────────────────────────────

class TopicBody(BaseModel):
    axis: str = DEFAULT_AXIS
    topic: str


async def make_hooks(body: TopicBody) -> dict[str, Any]:
    # 지도 축은 표지가 하나뿐이라 **2줄 고정**이다(지도_3-1단계 「HEADLINE 줄 수 = 2줄」).
    # 3줄을 내면 고를 수는 있는데 표지가 2줄짜리라 한 줄이 잘린다.
    two_only = bool(axis_conf(body.axis).get("cover_layout"))
    data = await _ask(
        "hooks",
        f"주제 「{body.topic}」 의 표지 훅 문구 후보를 지침서가 정한 대로 지어라. "
        + ("**2줄짜리만** 지침서가 정한 개수만큼 낸다. 3줄짜리는 내지 마라(three 는 빈 목록)."
           if two_only else "3줄짜리와 2줄짜리를 각각 지침서가 정한 개수만큼 낸다."),
        '{"three": [{"lines": ["1줄", "2줄", "3줄"]}], "two": [{"lines": ["1줄", "2줄"]}]}',
        schema=S_HOOKS, axis=body.axis,
    )
    d = data if isinstance(data, dict) else {}
    if two_only:
        d = {**d, "three": []}   # 모델이 그래도 냈으면 여기서 버린다
    return {
        "three": _list_from(d.get("three"), "items") or (d.get("three") if isinstance(d.get("three"), list) else []),
        "two": _list_from(d.get("two"), "items") or (d.get("two") if isinstance(d.get("two"), list) else []),
    }


# ─── 4단계 — 본문 ───────────────────────────────────────────────────────────

class BodyBody(BaseModel):
    axis: str = DEFAULT_AXIS
    topic: str
    hook: str = ""
    # 지도 축에서만 쓴다 — 어느 가이드의 어느 버튼에서 장소를 뽑을지.
    # 주제를 고를 때 화면이 함께 보내 준다. 못 받으면 `_resolve_button` 이 되찾는다.
    guide_id: str = ""
    button: str = ""
    # 지역까지 좁힌 주제면 그 지역. 장소도 그 지역에서만 뽑는다.
    region: str = ""


async def _resolve_button(topic: str, guide_id: str, button: str,
                          region: str = "") -> dict[str, Any]:
    """주제 → (가이드, 버튼, 지역). 화면이 알려 주면 그대로 쓰고, 아니면 주제 문구로 되찾는다.

    되찾기가 필요한 이유 — **보관해 둔 주제**는 보관함에 문구 한 줄로만 남는다
    (`지도_보관함.md`). 다음 회차에 그것을 고르면 guide_id·button 이 딸려 오지 않는다.
    주제 문구에는 버튼 이름이 그대로 들어 있으므로(「…실내 놀이터 90곳」) 글자로 찾는다.
    지역도 마찬가지다 — 「도쿄 — …」 처럼 주제 앞에 적혀 있어 글자로 되찾는다.
    """
    from app.services import travel_guide

    rows = await travel_guide.all_buttons()
    row = None
    if guide_id and button:
        for r in rows:
            if r["guide_id"] == guide_id and r["button"] == button:
                row = r
                break
    if row is None:
        # 되찾기는 제외 목록과 **같은 규칙**을 쓴다(`_button_key`). 두 곳이 다르게 찾으면
        # 「지운 주제는 걸러지는데 보관한 같은 주제는 못 찾는」 엇갈림이 생긴다.
        key = _button_key(rows, topic)
        if not key:
            raise RuntimeError(f"주제 「{topic}」 가 어느 가이드 버튼인지 찾지 못했습니다.")
        row = next(r for r in rows if (r["guide_id"], r["button"]) == key[:2])
        region = region or key[2]

    if not region:
        region = next((x["name"] for x in (row.get("regions") or []) if x["name"] in topic), "")
    return {**row, **_region_row(row, region)}


async def make_guide_body(body: "BodyBody") -> dict[str, Any]:
    """지도 축의 본문 — 가이드에 **이미 있는 장소 3곳**으로 짓는다.

    맛집 축과 달리 구글 지도를 따로 뒤지지 않는다. 가이드가 주소·사진·팁·후기를 다
    들고 있어서, 그대로 쓰면 사실 확인이 끝난 셈이다(`지도_1단계` 「가이드 데이터를
    읽어서 찾는다」). 장소는 그 버튼 안에서 무작위 3곳이다.
    """
    from app.services import travel_guide

    conf = axis_conf(body.axis)
    want = int(conf.get("places") or 3)

    hit = await _resolve_button(body.topic, body.guide_id, body.button, body.region)
    guide = await travel_guide.read_guide(hit["guide_id"])
    if not guide:
        raise RuntimeError(f"가이드 「{hit['guide_id']}」 를 읽지 못했습니다.")
    picked = travel_guide.places_in(guide, hit["button"], want, hit.get("region") or "")
    if not picked:
        where = f"버튼 「{hit['button']}」" + (f" 의 {hit['region']}" if hit.get("region") else "")
        raise RuntimeError(f"{where} 안에서 장소를 찾지 못했습니다.")

    facts = chr(10).join(
        f"- {p['name']} | 주소 {p.get('address') or '-'} | 분류 {p.get('category') or '-'}"
        f" | 평점 {p.get('rating') or '-'}"
        + (f" | 팁 {p['tip']}" if p.get("tip") else "")
        + (f" | 소개 {p['blurb']}" if p.get("blurb") else "")
        for p in picked
    )
    written = await _ask(
        "body",
        f"주제 「{body.topic}」 의 본문을 지침서 형식대로 지어라. 아래 **가이드에 있는 장소 {len(picked)}곳**만 쓴다.",
        '{"items": [{"name": "매장명", "where": "📍위치", "desc": "특징 3~4줄"}]}',
        extra=("===== 트래블어시 가이드의 장소 =====" + chr(10) + facts + chr(10) + chr(10) +
               "⚠ 이 목록에 없는 곳을 새로 만들지 마라. 「위치」는 위 주소를 **그대로** 옮긴다"
               "(우편번호 포함, 앞에 📍를 붙인다). 「특징」은 지침서가 정한 줄 수와 말투를 지킨다."),
        schema=S_PLACE_BODY, axis=body.axis,
    )
    items = _list_from(written, "items", "body")
    for it, p in zip(items, picked):
        if not isinstance(it, dict):
            continue
        it.setdefault("photo", p.get("photo") or "")
        it.setdefault("photos", p.get("photos") or [])
        it.setdefault("place_id", p.get("place_id") or "")
    # 뒤 단계(CTA1·캡처)가 어느 버튼·어느 지역이었는지 알아야 한다.
    return {"items": items, "guide_id": hit["guide_id"], "button": hit["button"],
            "region": hit.get("region") or "", "n": hit["n"]}


def _hours_line(hours: Any) -> str:
    """영업시간을 사람이 읽는 한 줄로. 벤더는 요일별 dict 로 준다."""
    if isinstance(hours, str):
        return hours[:60]
    week = (hours or {}).get("week") if isinstance(hours, dict) else None
    if not week:
        return ""
    parts = [f"{d.get('day')} {d.get('start')}~{d.get('end')}" for d in week[:7] if isinstance(d, dict)]
    return " · ".join(parts)[:90]


class TopicUnfit(RuntimeError):
    """**주제 탓**으로 본문을 못 지었다 — 그 주제로는 내일 다시 해도 같은 답이 나온다.

    미리 만들기는 이것만 보고 주제를 제외한다(`studio_worker._do_prepare`). 조회 실패·
    CLI 오류 같은 일시적인 실패까지 제외하면 멀쩡한 주제가 영영 사라진다 — 그쪽은
    그냥 RuntimeError 로 두고 다음 밤에 다시 시도한다.
    """


# 한 가게당 프롬프트에 싣는 리뷰 — 다 넣으면 프롬프트가 터지고, 적으면 다시 뭉뚱그린다.
REVIEW_CAP = 30         # 벤더에서 받아 오는 수
REVIEW_LINES = 12       # 그중 프롬프트에 싣는 수
REVIEW_CHARS = 200      # 한 리뷰에서 잘라 쓰는 길이
# 적합성 판정에 싣는 리뷰. 넉 줄이었다가 열두 줄로 늘렸다(2026-09-09) — 노도구로처럼
# 흔치 않은 메뉴는 넉 줄 안에 안 잡혀서, 실제로 파는 집까지 「리뷰에 안 나온다」로 떨어졌다
# (가나자와 노도구로 회차에서 여덟 곳이 전멸했다).
SCREEN_REVIEW_LINES = 12

# 모델에게 더 받아 두는 가게 수. 확인·판정에서 떨어지는 만큼을 메우려는 자리다
# (2026-09-09 사람 지시 — 「주제는 장소가 8곳 이상인 것만 달라」). 여덟만 받으면 한 곳만
# 떨어져도 여덟을 못 채운다.
PICK_EXTRA = 6


def _place_facts(g: dict[str, Any], revs: list[dict[str, Any]], lines: int = REVIEW_LINES) -> str:
    """한 가게의 재료를 프롬프트 한 덩이로 만든다.

    이름·주소·평점만 주면 여덟 곳이 전부 비슷한 문장으로 나온다 — 넉 줄에 채울 것이
    없어서다(2026-09-07 사람 신고 — 삿포로 징기스칸 8곳이 다 비슷했다).
    구글의 가게 소개와 리뷰 본문을 같이 실어, 그 집에만 있는 것(웨이팅·예약·자리·간판
    메뉴·값·내력)을 모델이 **골라 쓸 수 있게** 한다. 지침서의 「고유 정보를 반드시 하나
    넣는다」는 넣을 것이 손에 있어야 지킬 수 있다.
    """
    parts = [
        f"■ {g['name']} | 주소 {g.get('address') or '-'} | 평점 {g.get('rating') or '-'}"
        f" | 분류 {g.get('category') or '-'} | 영업 {_hours_line(g.get('hours')) or '-'}"
    ]
    if g.get("description"):
        parts.append(f"  · 구글 소개: {g['description']}")
    picked = [t for t in (str(r.get("text") or "").strip().replace(chr(10), " ")[:REVIEW_CHARS]
                          for r in revs[:lines]) if t]
    if picked:
        parts.append("  · 리뷰:")
        parts.extend(f"    - {t}" for t in picked)
    else:
        # 리뷰를 못 받았다고 지어내면 안 된다. 모델에게 그 사실을 알린다.
        parts.append("  · 리뷰: (받지 못했다 — 위에 적힌 것만 쓰고 나머지는 지어내지 마라)")
    return chr(10).join(parts)


async def _screen_places(topic: str, places: list[dict[str, Any]],
                         revs: list[list[dict[str, Any]]], axis: str
                         ) -> tuple[list[dict[str, Any]], list[list[dict[str, Any]]], list[str]]:
    """확인된 가게가 **그 주제의 가게인지** 가린다.

    `verify` 는 「구글 지도에 있나」만 본다. 지역 명소는 다 있으므로 전부 통과한다.
    그래서 모델이 갯수를 채우려고 아무 데나 적으면 그대로 본문이 된다.

    > 2026-09-08 사람 신고 — 「아타미 — 온천 마크 우유병에 담아주는 푸딩 8곳」 회차에
    > 아타미 선비치(해변)·라스카 아타미(쇼핑몰)·아타미 긴자 상점가·TKP 리조트(숙박)가
    > 본문 낱장으로 나갔다. 여덟 곳 중 푸딩집은 한 곳뿐이었다.

    걸러 낸 곳은 **채우지 않는다.** 모자라면 사람이 주제·장수를 고친다(1단계 지침서).
    """
    if not places:
        return places, revs, []

    menu = (chr(10) * 2).join(
        f"[{i}] " + _place_facts(g, r, lines=SCREEN_REVIEW_LINES)
        for i, (g, r) in enumerate(zip(places, revs), 1)
    )
    try:
        data = await _ask(
            "body",
            f"주제 「{topic}」 에 **정말로 맞는 가게만** 남기려 한다. 아래 각 곳이 이 주제의 "
            "가게인지 판정하라.",
            '{"items": [{"n": "번호", "fit": true, "why": "아니라면 왜"}]}',
            extra=("===== 구글 지도에서 확인한 곳 =====" + chr(10) + menu + chr(10) + chr(10) +
                   "판정 기준 — **주제가 말하는 그 음식·그 경험을 실제로 파는 곳인가.**" + chr(10) +
                   "· 해변·공원·상점가·쇼핑몰·역·숙박시설처럼 **가게가 아닌 곳**은 `fit=false` 다. "
                   "그 지역의 유명한 명소여도 마찬가지다." + chr(10) +
                   "· 분류·구글 소개·리뷰에 주제의 음식이 **한 번도 안 나오면** `fit=false` 다. "
                   "「근처에 있으니 겸사겸사」는 이유가 되지 않는다." + chr(10) +
                   "· 애매하면 `false` 로 둔다. 한 곳이 모자란 것보다 엉뚱한 한 곳이 나가는 것이 "
                   "훨씬 나쁘다." + chr(10) +
                   "· 모든 번호에 대해 한 줄씩 낸다. 번호는 위 대괄호 숫자 그대로 쓴다."),
            schema=S_SCREEN, axis=axis,
        )
    except Exception as e:
        # 판정을 못 받았다고 본문을 통째로 못 내면 더 나쁘다 — 그대로 진행하고 자취를 남긴다.
        logger.warning(f"[studio] 주제 적합성 판정 실패 — 그대로 진행합니다: {type(e).__name__} {e}")
        return places, revs, []

    bad: dict[int, str] = {}
    for it in _list_from(data, "items", "places"):
        if not isinstance(it, dict):
            continue
        try:
            n = int(str(it.get("n") or "").strip())
        except ValueError:
            continue
        if not it.get("fit"):
            bad[n] = str(it.get("why") or "주제와 맞지 않음")

    keep_g, keep_r, off = [], [], []
    for i, (g, r) in enumerate(zip(places, revs), 1):
        if i in bad:
            off.append(f"{g.get('name')} — {bad[i]}")
        else:
            keep_g.append(g)
            keep_r.append(r)
    if off:
        logger.info(f"[studio] 주제와 안 맞아 뺀 가게 {len(off)}곳: {off}")
    return keep_g, keep_r, off


async def make_place_body(body: "BodyBody") -> dict[str, Any]:
    """실제 가게를 다루는 축(일본맛집)의 본문 — **확인하고 나서 짓는다.**

    세 걸음이다:
      ① 모델에게 **가게 이름만** 받는다. 이때 설명까지 시키면 그럴듯한 거짓이 섞인다.
      ② `place_lookup` 으로 구글 지도에서 **실존·주소·영업시간·평점**을 확인한다.
         못 찾은 이름은 **버린다** — 지어낸 것일 수 있다.
      ③ 확인된 사실만 프롬프트에 넣고 문구를 받는다.

    `_공통.md` 의 「장소를 다룰 때는 place_info 로 확인한다」를 화면 쪽에서 지키는 자리다.
    """
    from app.services import place_lookup

    conf = axis_conf(body.axis)
    want = int(conf.get("places") or 8)

    picked = await _ask(
        "body",
        f"주제 「{body.topic}」 에 넣을 가게를 {want + PICK_EXTRA}곳 고르라. "
        "**실제로 있는 가게의 이름만** 낸다. 설명·주소·영업시간은 여기서 적지 마라 — "
        "그건 다음 단계에서 구글 지도로 확인해 채운다. "
        "찾기 쉽게 «가게 이름 + 지역» 형태로 쓴다(예: 이치란 시부야점).",
        '{"places": ["가게 이름", ...]}',
        extra=(f"⚠ **숫자를 채우려고 주제에서 벗어난 곳을 넣지 마라.** 주제가 「푸딩」이면 "
               "그 푸딩을 파는 집만, 「모쓰나베」면 모쓰나베를 내는 집만이다. 해변·상점가·"
               "쇼핑몰·역·숙박처럼 **그 지역의 명소이긴 하나 주제의 음식을 파는 곳이 아닌** 것은 "
               "한 곳도 넣지 않는다." + chr(10) +
               f"⚠ 낱장에 쓰는 것은 {want}곳이다. 확인·판정에서 떨어지는 곳이 있어 "
               f"{want + PICK_EXTRA}곳을 받는다 — **확실한 곳만** 대라. 모르면 아는 만큼만 내라. "
               "억지로 채운 한 곳이 캐러셀 전체를 망친다."),
        schema=S_PLACE_NAMES, axis=body.axis,
    )
    names = [str(n).strip() for n in _list_from(picked, "places", "items") if str(n).strip()]
    if not names:
        raise RuntimeError("가게 이름을 받지 못했습니다.")

    checked = await place_lookup.verify_many(names[: want + PICK_EXTRA])
    good = [c for c in checked if c.get("ok")]
    dropped = [c["name"] for c in checked if not c.get("ok")]
    if dropped:
        logger.info(f"[studio] 확인 못 한 가게 {len(dropped)}곳 제외: {dropped}")
    if not good:
        raise TopicUnfit("고른 가게를 구글 지도에서 하나도 찾지 못했습니다.")
    good = _dedupe_places(good)[: want + PICK_EXTRA]

    # 리뷰를 먼저 받는다 — 이름·주소·평점만으로는 여덟 곳이 전부 비슷해진다(`_place_facts`).
    revs = await place_lookup.reviews_many(good, cap=REVIEW_CAP)

    # 실존 확인을 통과했다고 주제에 맞는 것은 아니다 — 여기서 한 번 더 가린다.
    good, revs, off = await _screen_places(body.topic, good, revs, body.axis)
    dropped += off
    if not good:
        raise TopicUnfit("주제에 맞는 가게가 하나도 남지 않았습니다 — 주제를 좁히거나 바꿔야 합니다.")
    good, revs = good[:want], revs[:want]
    if len(good) < want:
        # 모자란 채로 낸다 — 억지로 채운 한 곳이 더 나쁘다. 그 뒤는 부르는 쪽이 정한다:
        # 미리 만들기는 **그 주제를 버리고 다음 후보로 넘어가고**(2026-09-09 사람 지시,
        # `일본맛집_1단계_주제후보.md`), 화면에서 사람이 고른 주제는 그대로 낸다.
        logger.warning(f"[studio] 주제 「{body.topic}」 — {want}곳 중 {len(good)}곳만 남았습니다.")

    facts = (chr(10) * 2).join(_place_facts(g, r) for g, r in zip(good, revs))
    written = await _ask(
        "body",
        f"주제 「{body.topic}」 의 본문을 지침서 형식대로 지어라. 아래 **확인된 가게 {len(good)}곳**만 쓴다.",
        '{"items": [{"name": "매장명", "where": "📍위치 1줄", "desc": "특징 4줄"}]}',
        extra=("===== 구글 지도에서 확인한 사실 =====" + chr(10) + facts + chr(10) + chr(10) +
               "⚠ 이 목록에 없는 가게를 새로 만들지 마라. 주소·영업시간·평점을 **여기 적힌 값에서만** 가져온다. "
               "「위치」는 위 주소를 한 줄로 옮긴다(줄바꿈 없이). 「특징」은 지침서가 정한 줄 수를 지킨다." + chr(10) +
               "⚠ 넉 줄을 **그 가게에만 해당하는 것**으로 채워라 — 위 「구글 소개」와 「리뷰」에서 "
               "간판 메뉴·먹는 방법·자리·웨이팅·예약·값·내력을 찾아 쓴다. 리뷰에 없는 것은 지어내지 마라. "
               "여러 리뷰가 함께 말하는 것만 사실로 본다(한 사람의 그날 기분은 사실이 아니다)." + chr(10) +
               f"⚠ **{len(good)}곳이 서로 달라야 한다.** 다른 가게에 그대로 옮겨도 말이 되는 문장은 다시 써라 "
               "— 같은 음식을 파는 회차일수록 부위·굽는 법·소스·자리·예약처럼 **갈리는 자리**를 찾아 쓴다."),
        schema=S_PLACE_BODY, axis=body.axis,
    )
    items = _list_from(written, "items", "body")
    # 사진은 사실 확인에서 같이 받아 둔다 — 4단계에서 낱장 배경으로 쓴다.
    #
    # 대표 한 장(`photo`)은 그대로 쓰되, **바꿀 수 있게** 후보(`photos`)도 같이 담는다.
    # 2026-09-03 사람 결정: 8곳을 다 고르게 하면 「한 번에 끝낸다」가 흐려진다. 기본은
    # 자동이고, 마음에 안 드는 것만 화면에서 눌러 바꾼다.
    shots = await place_lookup.photos_many(good, cap=6)
    for it, g, alts in zip(items, good, shots):
        if not isinstance(it, dict):
            continue
        rep = g.get("photo") or ""
        # 대표가 후보 안에 없으면 맨 앞에 끼워 넣는다 — 화면에서 「지금 것」이 보여야 한다.
        cands = ([rep] if rep and rep not in alts else []) + alts
        it.setdefault("photo", rep or (cands[0] if cands else ""))
        it.setdefault("photos", cands)
        it.setdefault("place_id", g.get("place_id") or "")
    return {"items": items, "dropped": dropped}


def _dedupe_places(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """같은 가게를 하나만 남긴다 — `place_id` 나 주소가 같으면 같은 곳이다.

    모델이 한 가게를 **한국어·영어·일본어 이름으로 각각** 내면 글자로는 셋 다 다르다.
    구글 지도로 확인한 뒤에야 같은 곳인 게 드러난다 — 그래서 여기서 거른다
    (2026-09-07 실측: 징기스칸 회차 8곳 중 2곳이 같은 `place_id` 였고, 낱장 두 장이
    같은 가게로 나갔다).
    """
    seen_id: set[str] = set()
    seen_addr: set[str] = set()
    out: list[dict[str, Any]] = []
    for r in rows:
        pid = str(r.get("place_id") or "")
        addr = re.sub(r"[\s,]+", "", str(r.get("address") or ""))
        if (pid and pid in seen_id) or (addr and addr in seen_addr):
            logger.info(f"[studio] 앞의 가게와 같은 곳이라 뺍니다: {r.get('name')}")
            continue
        seen_id.add(pid)
        seen_addr.add(addr)
        out.append(r)
    return out


async def make_body(body: BodyBody) -> dict[str, Any]:
    conf = axis_conf(body.axis)
    # 지도 축은 가이드에 이미 있는 장소를 쓴다 — 따로 확인할 것이 없다.
    if conf.get("guide_source"):
        return await make_guide_body(body)
    # 실제 장소를 다루는 축은 확인을 거쳐야 한다.
    if int(conf.get("places") or 0) > 0:
        return await make_place_body(body)
    data = await _ask(
        "body",
        f"주제 「{body.topic}」 · 확정 훅 「{body.hook}」 의 본문 후보를 "
        "지침서가 정한 개수·형식대로 지어라.",
        '{"items": [{"jp": "일본어", "reading": "읽는 방법", '
        '"meaning": "의미", "situation": "사용 가능한 상황"}]}',
        extra="「의미」는 지침서대로 큰따옴표를 포함해 적고, 「사용 가능한 상황」이 두 줄이면 "
              "줄바꿈(\\n)을 그대로 넣어라. 화면이 글자 그대로 옮긴다.",
        schema=S_BODY, axis=body.axis,
    )
    return {"items": _list_from(data, "items", "body", "rows")}


# ─── 5단계 — 캡션 ───────────────────────────────────────────────────────────

class Cta1Body(BaseModel):
    axis: str = DEFAULT_AXIS
    topic: str
    hook: str = ""
    items: list[dict] = []
    # 「N곳」 — 3-1 SUBHEADLINE 과 **같은 숫자**여야 한다(지도_3-4단계 2026-08-27).
    n: int = 0
    guide_id: str = ""
    button: str = ""
    region: str = ""


async def make_cta1(body: Cta1Body) -> dict[str, Any]:
    """지도 축에만 있는 3-4단계 — CTA1 낱장의 세 칸.

    강조(HEADLINE 2줄) · 공감+수량(SUBHEADLINE 1줄, **수량 필수**) · 팔로우 유도(BODY 2줄).
    셋을 한 칸에 뭉치지 않는다(지도_3-4단계 2026-08-26 — 전에는 몰아넣었다).
    """
    n = body.n
    if not n:
        # 화면이 숫자를 안 보냈으면 되찾는다 — 두 숫자가 어긋나면 사람이 알아채기 어렵다.
        hit = await _resolve_button(body.topic, body.guide_id, body.button, body.region)
        n = int(hit.get("n") or 0)

    names = ", ".join(str(i.get("name") or "") for i in body.items if i.get("name"))
    data = await _ask(
        "cta1",
        f"주제 「{body.topic}」 · 확정 훅 「{body.hook}」 의 CTA1 문구를 지침서 형식대로 지어라.",
        '{"headline": "강조 2줄", "subtext": "공감·수량 1줄", "body": "팔로우 유도 2줄"}',
        extra=(f"이 회차의 장소 수는 **{n}곳** 이다. `subtext` 에 이 숫자를 반드시 넣어라 "
               f"— 3-1 SUBHEADLINE 의 N 과 같은 값이어야 한다.\n"
               f"본문에 실린 곳: {names or '(없음)'}\n"
               "줄바꿈은 \\n 으로 넣어라. 화면이 글자 그대로 옮긴다."),
        schema=S_CTA1, axis=body.axis,
    )
    return {
        "headline": str(data.get("headline") or ""),
        "subtext": str(data.get("subtext") or ""),
        "body": str(data.get("body") or ""),
        "n": n,
    }


class CaptionBody(BaseModel):
    axis: str = DEFAULT_AXIS
    topic: str
    hook: str = ""
    items: list[dict] = []
    # 지도 축 캡션은 이걸 그대로 끌어다 쓴다(고정 틀).
    cta1: dict = {}


S_TAGS = _obj({"tags": _arr({"type": "string"})})


async def make_map_caption(body: "CaptionBody") -> dict[str, Any]:
    """지도 축 캡션 — **짓지 않고 조립한다.**

    `지도_5단계_캡션.md` 2026-08-26: 「**새로 작문하지 않는다.** 아래 틀에 그 회차 문구를
    끌어다 채우는 것이 전부다.」 재료는 3-1 확정 훅과 3-4 CTA1 이고, 봇이 새로 만드는
    것은 **해시태그 3개뿐**이다.

    ⚠ 이걸 모델에게 통째로 맡겼더니 「확정 훅 문구와 CTA1 문구를 그대로 보내주세요」
      라는 **요청문**을 캡션이랍시고 냈다(2026-09-04). 미리 만들 때는 훅이 아직
      안 정해져 재료가 비어 있기 때문이다. 그래서 이 축은 훅을 고른 **뒤에** 조립한다.
    """
    c = body.cta1 or {}
    hook = " ".join(l.strip() for l in body.hook.split("\n") if l.strip()) or body.hook.strip()

    tags: list[str] = []
    try:
        got = await _ask(
            "caption",
            f"주제 「{body.topic}」 에 어울리는 인스타 해시태그를 **3개만** 내라. "
            "한국어로, # 를 붙여서 낸다. 설명하지 마라.",
            '{"tags": ["#태그", "#태그", "#태그"]}',
            schema=S_TAGS, axis=body.axis,
        )
        tags = [str(t).strip() for t in (got.get("tags") or []) if str(t).strip()][:3]
    except Exception as e:
        # 해시태그가 없어도 캡션은 나와야 한다 — 사람이 화면에서 덧붙이면 된다.
        logger.warning(f"[studio] 해시태그를 받지 못했습니다: {e}")

    parts = ["[공유]", hook, "", str(c.get("headline") or ""), "", str(c.get("body") or "")]
    if tags:
        parts += ["", " ".join(t if t.startswith("#") else f"#{t}" for t in tags)]
    return {"caption": "\n".join(parts).strip()}


async def make_caption(body: CaptionBody) -> dict[str, Any]:
    # 지도 축은 고정 틀이라 조립한다(위 함수).
    if axis_conf(body.axis).get("cta1"):
        return await make_map_caption(body)
    lines = [f"- {i.get('jp','')} / {i.get('meaning','')}" for i in body.items]
    data = await _ask(
        "caption",
        f"주제 「{body.topic}」 · 확정 훅 「{body.hook}」 의 인스타 캐프션을 지침서대로 지어라.",
        '{"caption": "캐프션 전문"}',
        extra="===== 확정된 본문 =====\n" + ("\n".join(lines) or "(없음)"),
        schema=S_CAPTION, axis=body.axis,
    )
    return {"caption": (data or {}).get("caption") or ""}


# ─── 6단계 — 캐러셀 생성 + 편집 링크 ────────────────────────────────────────

class BuildBody(BaseModel):
    axis: str = DEFAULT_AXIS
    topic: str
    hook_lines: list[str] = []      # 고른 훅. 줄 수가 표지 낱장을 정한다
    image_url: str = ""             # 고른 사진 1장 — 표지·CTA 배경에 같이 들어간다
    items: list[dict] = []          # 제외하고 남은 본문
    caption: str = ""
    # 지도 축에만 있다 — {"headline","subtext","body"} 세 칸(지도_3-4단계).
    cta1: dict = {}


async def build(
    body: BuildBody,
) -> dict[str, Any]:
    """확정한 것들로 캐러셀을 만들고 편집 링크를 돌려준다.

    ⚠ 세 인자는 반드시 함께 간다(요청서 표). 하나라도 빠지면 **조용히** 망가진다 —
      slides 가 없으면 서버가 문구를 새로 지어내고, layout_overrides 가 없으면 전부
      표지로 렌더되며(한글 낱장 이름이 렌더러의 영문 키에 안 걸린다), user_image_urls 가
      없으면 표지·CTA 배경이 빈 채로 나온다.
    """
    from app.services import studio_remote

    conf = axis_conf(body.axis)
    if not body.items:
        raise HTTPException(status_code=400, detail="본문이 비어 있습니다")

    # 지도 축의 표지는 하나뿐이다(훅이 2줄 고정이라 줄 수로 갈리지 않는다).
    cover_layout = conf.get("cover_layout") or (
        "표지_3줄" if len(body.hook_lines) >= 3 else "표지_2줄")

    # 낱장: 0 표지 · 1~N 본문(상황일본어) · 마지막 CTA
    slides: list[dict[str, Any]] = [{
        "index": 0,
        "type": "cover",
        "headline": "\n".join(body.hook_lines),
        "subtext": "",
        "body": "",
        "tag": "",
    }]
    # 본문 네 칸 매핑 — 일본어→headline / 읽는 방법→subtext / 의미→body / 상황→tag.
    # 줄바꿈·큰따옴표까지 글자 그대로 넘긴다. 여기서 다듬지 않는다.
    for item in body.items:
        slides.append({
            "index": len(slides),
            "type": "content",
            # 어느 칸이 어디로 가는지는 축마다 다르다(axis_conf 의 body_fields).
            # 빈 이름("")은 그 칸을 안 쓴다는 뜻이다 — 일본맛집은 tag 를 쓰지 않는다.
            **{slot: str(item.get(field) or "") if field else ""
               for slot, field in zip(("headline", "subtext", "body", "tag"), conf["body_fields"])},
        })
    cta_index = len(slides)
    # 지도 축은 CTA 가 **둘**이다 — 문구가 든 CTA1, 지도만 있는 CTA2(지도_4단계 낱장 배치).
    # CTA2 는 문구가 없어도 자리를 채운다. 안 그러면 순번이 밀린다.
    if conf.get("cta1"):
        c = body.cta1 or {}
        slides.append({
            "index": cta_index, "type": "cta",
            "headline": str(c.get("headline") or ""),
            "subtext": str(c.get("subtext") or ""),
            "body": str(c.get("body") or ""),
            "tag": "",
        })
        cta2_index = len(slides)
        slides.append({"index": cta2_index, "type": "cta",
                       "headline": "", "subtext": "", "body": "", "tag": ""})
        layout_overrides: dict[int, str] = {0: cover_layout, cta_index: "CTA1", cta2_index: "CTA2"}
    else:
        slides.append({"index": cta_index, "type": "cta",
                       "headline": "", "subtext": "", "body": "", "tag": ""})
        cta2_index = cta_index
        layout_overrides = {0: cover_layout, cta_index: "CTA"}
    for i in range(1, cta_index):
        layout_overrides[i] = conf["body_layout"]

    # 표지·CTA 배경에 같은 사진 1장.
    user_image_urls: dict[int, str] = {}
    # 지도 축은 그 한 장(지도 캡처)이 **표지·CTA2 는 배경, CTA1 은 칸 1** 로 들어간다
    # (지도_4단계 낱장 배치 · 2026-08-26 「CTA1 지도를 봇이 넣는다 — items 의 칸 1 로」).
    user_item_image_urls: dict[int, dict[str, str]] = {}
    if body.image_url:
        if conf.get("cta1"):
            user_image_urls = {0: body.image_url, cta2_index: body.image_url}
            user_item_image_urls = {cta_index: {"1": body.image_url}}
        else:
            user_image_urls = {0: body.image_url, cta_index: body.image_url}
    # 실제 장소를 다루는 축은 **낱장마다 그 가게 사진**이 배경으로 들어간다
    # (일본맛집 4단계 지침서). 사진은 3-3 에서 장소를 확인할 때 함께 받아 뒀다.
    if int(conf.get("places") or 0) > 0:
        for i, item in enumerate(body.items, start=1):
            photo = str((item or {}).get("photo") or "")
            if photo:
                user_image_urls[i] = photo

    if not studio_remote.is_configured():
        raise HTTPException(
            status_code=503,
            detail="STUDIO_API_BASE / STUDIO_ACCOUNT 이 설정되지 않았습니다 (backend/.env).",
        )

    # 세 인자를 **함께** 넘긴다. 하나라도 빠지면 위 주석의 방식으로 조용히 망가진다.
    rendered = await studio_remote.call("/carousels/render", {
        "template_id": conf["template_id"],
        "slides": slides,
        "layout_overrides": {str(k): v for k, v in layout_overrides.items()},
        **({"user_image_urls": {str(k): v for k, v in user_image_urls.items()}} if user_image_urls else {}),
        **({"user_item_image_urls": {str(k): v for k, v in user_item_image_urls.items()}}
           if user_item_image_urls else {}),
    })
    canvas_slides = rendered.get("canvas_slides") or []
    if not canvas_slides:
        raise HTTPException(status_code=502, detail="템플릿 적용 결과가 비었습니다")

    created = await studio_remote.call("/carousels/", {
        "title": body.topic,
        "template_id": str(rendered.get("template_slug") or "minimal"),
        "canvas_data": {
            "canvas_slides": canvas_slides,
            "source_slides": slides,
            # ★ 편집기는 여기서 읽어 자동저장 때 그대로 되쓴다. 빼먹으면 편집기가 빈 값으로
            #   덮어써서 배경이 몇 분 뒤 DB 에서 사라진다(봇 tools.js 에 같은 사고 기록).
            "user_image_urls": {str(k): v for k, v in user_image_urls.items()},
            "user_item_image_urls": {str(k): v for k, v in user_item_image_urls.items()},
            "layout_overrides": {str(k): v for k, v in layout_overrides.items()},
            "template_db_id": conf["template_id"],
            "caption": body.caption,
            "hashtags": [],
        },
    })
    carousel_id = int(created.get("id") or 0)
    if not carousel_id:
        raise HTTPException(status_code=502, detail="캐러셀 생성 응답에 id 가 없습니다")

    recorded = _append_history(body.topic, carousel_id, body.axis)
    # 만든 주제는 보관함에서 뺀다 — 이제 이력이 막아 준다.
    _write_keeps([t for t in _keeps(body.axis) if t != body.topic.strip()], body.axis)

    return {
        "id": carousel_id,
        "url": studio_remote.editor_url(carousel_id),
        "slides": len(canvas_slides),
        "history_recorded": recorded,
    }
