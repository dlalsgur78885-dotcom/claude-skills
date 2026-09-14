"""원클릭 스튜디오 일꾼 — 이 PC 에서 돌며 서버의 회차를 처리한다.

## 왜 이 방향인가

codex 는 이 PC 의 로그인 세션에 묶여 있어 서버로 못 옮긴다. 그렇다고 화면을 이 PC 에 두면
밖에서 주소로 닿을 수 없다. 그래서 **봇이 디스코드에 하는 것과 똑같이** — 일하는 쪽이
먼저 연결을 건다. 서버는 열려 있고, 이 일꾼이 주기적으로 「할 일 있나」 물어본다.

덕분에 이 PC 에는 들어오는 주소도, 터널도, 열쇠도 필요 없다.

## 무엇을 하나

`GET /studio-sessions/pending` → 할 일이 있으면 그 단계를 지어(`studio_steps._ask`, `codex_image`)
`PATCH` 로 후보를 올린다. 사람이 화면에서 고르면 다음 단계가 다시 `pending` 으로 올라온다.

규칙은 여기에 없다 — `studio_steps._ask` 가 `docs/process` 의 지침서를 읽어 프롬프트에 싣는다.
"""

import asyncio
import logging
from datetime import datetime
import secrets
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)

# 사람이 고르는 사이엔 할 일이 없다. 너무 자주 물으면 서버만 두드린다.
POLL_SECONDS = 5

_task: asyncio.Task | None = None


def axis_conf_shots(studio, axis: str) -> dict[str, int]:
    """그 축의 표지 사진 구성. 없으면 인물·풍경 5장씩(상황별 일본어 기본)."""
    conf = studio.axis_conf(axis)
    return dict(conf.get("cover_shots") or {"person": 5, "scenery": 5})


def is_enabled() -> bool:
    """원격 스택 설정 + codex 가 둘 다 있어야 일꾼이 의미가 있다."""
    from app.services import codex_image, studio_remote
    return studio_remote.is_configured() and codex_image.is_available()


async def _do_topics(chosen: dict[str, Any], axis: str) -> dict[str, Any]:
    from app.services import studio_steps as studio
    r = await studio.make_topics(axis)
    return {"topics": r["items"], "kept": r["kept"], "dropped": r["dropped"]}


async def _do_hooks(chosen: dict[str, Any], axis: str) -> dict[str, Any]:
    from app.services import studio_steps as studio
    r = await studio.make_hooks(studio.TopicBody(axis=axis, topic=chosen.get("topic", "")))
    return {"hooks": r}


# ── 사진의 결 — 코드가 프롬프트 뒤에 **그대로** 붙인다 ──────────────────────
#
# 지침서 `상황별일본어_3-2단계_썸네일이미지.md` 의 「사진의 결 — 인물·풍경」 문단이 원본이고,
# 아래는 그 영어판이다. 원본이 바뀌면 여기도 같이 고친다.
#
# ⚠ 왜 코드가 붙이나 — 「프롬프트마다 결을 함께 실어라」고 시켰는데 모델이 계속 흘렸다.
#   2026-09-07 실측: 인물 다섯 장이 전부 장면 묘사만 있고 결이 한 줄도 안 실려, 사람이
#   「인물 사진이 또 산으로 갔다」고 했다. 시켜서 될 일이 아니라 붙여야 할 일이다.
STYLE = {
    "person": (
        "Shoot it like an emotive Instagram travel-influencer snapshot. She looks like a real, "
        "natural person, yet noticeably more beautiful and appealing than an ordinary everyday "
        "photo: a photogenic face, refined styling, a natural expression and pose. Avoid overly "
        "documentary realism and plain, unremarkable looks; keep the balance between naturalness "
        "and idealized good looks. Natural light and emotive color as if shot on an iPhone, with "
        "a refined travel-photo mood."
    ),
    "scenery": (
        "Shoot it like a beautiful, emotive Instagram travel photo taken on location: natural "
        "light, a composition with depth, refined color, the mood of a travel magazine. If any "
        "text appears, render every character accurately and clearly — never include broken "
        "glyphs, fake characters, random letters, or distorted numbers and symbols. If accurate "
        "text is not possible, leave the space clean instead of generating unnecessary lettering."
    ),
    # 일본맛집 표지 후보의 절반(2026-09-09). 사람이 안 나오는 대신 음식이 주인공이라
    # 인물 결을 그대로 쓰면 「예쁜 사람 없는 여행 사진」이 된다.
    "food": (
        "Shoot it like an emotive Instagram food photo taken at the table: soft natural window "
        "light, a close and appetizing composition with shallow depth of field, visible texture "
        "and steam, refined color, the mood of a travel food feed. No people in the frame. Do "
        "not render any text, signage or logos — leave the space clean instead of generating "
        "lettering."
    ),
}

# 프롬프트에 「인물(person) 5장」처럼 적으려고 쓴다. 영어 키만 주면 무엇을 그리라는 건지
# 모델이 한 번 더 번역해야 한다.
KIND_KO = {"person": "인물", "scenery": "풍경", "food": "음식"}


async def _scene_context(session_id: str, topic: str) -> tuple[list[str], list[dict[str, Any]]]:
    """`(이 회차가 이미 쓴 무대, 이 주제에 지금 붙어 있는 그림)`.

    앞쪽은 겹치지 말라고 넘기고, 뒤쪽은 **인물만·풍경만 다시 그릴 때 나머지를 살리려고** 쓴다.

    그림은 주제마다 따로 만들어져서, 결이 가까운 두 주제가 같은 무대로 몰렸다
    (2026-09-07 사람 신고 — 「난처할 때」와 「사과」가 둘 다 개찰구·식당 테이블).
    읽지 못하면 빈 목록이다 — 겹치는 것이 아무것도 안 나오는 것보다 낫다.
    """
    from app.services import studio_remote
    try:
        s = await studio_remote.call(f"/studio-sessions/{session_id}", method="GET")
    except Exception as e:
        logger.warning(f"[studio-worker] 이미 쓴 무대를 못 읽었습니다: {e}")
        return [], []
    cand = (s or {}).get("candidates") or {}
    out: list[str] = []
    for name, v in (cand.get("prepared") or {}).items():
        # 지금 다시 뽑는 주제는 뺀다 — 곧 버릴 것과 겹치지 말라고 할 이유가 없다.
        if name == topic:
            continue
        out += [str(i.get("prompt") or "") for i in ((v or {}).get("images") or [])]
    # 화면이 보는 것과 같은 순서다 — [다시 뽑기] 로 만든 것이 있으면 그쪽이 밤에 만든 것을 덮는다.
    mine = cand.get("images")
    if mine is None:
        mine = ((cand.get("prepared") or {}).get(topic) or {}).get("images") or []
    return [x for x in out if x], [i for i in mine if isinstance(i, dict)]


# 프롬프트에 싣는 「이미 쓴 무대」 — 다 실으면 프롬프트가 터진다. 앞머리(장소)만 본다.
SCENE_KEEP = 40
SCENE_CHARS = 90


def _avoid_block(used: list[str]) -> str:
    if not used:
        return ""
    seen = list(dict.fromkeys(u.split(",")[0].strip()[:SCENE_CHARS] for u in used))[-SCENE_KEEP:]
    return ("===== 이 회차가 이미 쓴 무대 (다시 쓰지 마라) =====\n"
            + "\n".join(f"- {x}" for x in seen)
            + "\n⚠ 위와 **같은 장소·구도**를 다시 내지 마라. 주제가 비슷해도 무대는 달라야 한다 "
              "— 개찰구·라멘 카운터·료칸 이불·비 온 골목처럼 이미 나온 곳은 피하고 다른 자리를 찾는다.")


async def _do_images(chosen: dict[str, Any], axis: str,
                     used: list[str] | None = None,
                     keep: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """사진은 한 장에 1~4분이라 가장 오래 걸린다. 여기서 끝까지 기다렸다가 한 번에 올린다
    — 화면은 그동안 「만드는 중」만 보여주면 된다."""
    from app.services import studio_steps as studio
    from app.services import codex_image, studio_remote

    topic = chosen.get("topic", "")
    hook = " ".join(chosen.get("hook_lines", []))

    # 지도 축은 **그리지 않고 찍는다**(지도_3-2단계 2026-08-26 — generate_image 폐기).
    # 재료가 트래블어시 가이드라 프롬프트를 지을 것도 없다.
    if studio.axis_conf(axis).get("guide_source"):
        from app.services import map_capture, studio_remote

        hit = await studio._resolve_button(topic, chosen.get("guide_id", ""),
                                           chosen.get("button", ""), chosen.get("region", ""))
        # 지역까지 좁힌 주제면 그 지역 장소를 눌러 지도를 거기로 옮긴다(map_capture 참고).
        blobs = await map_capture.capture(hit["guide_id"], hit["button"],
                                          anchor=hit.get("anchor") or "")
        if not blobs:
            raise RuntimeError("지도를 한 장도 찍지 못했습니다.")
        where = f"{hit['guide_name']} · {hit['button']}" + (f" · {hit['region']}" if hit.get("region") else "")
        images = []
        for blob in blobs:
            url = await studio_remote.upload_image(blob, f"{secrets.token_hex(8)}.png")
            images.append({"kind": "map", "prompt": where, "url": url})
        return {"images": images}

    shots = axis_conf_shots(studio, axis)
    # 「인물만 다시」·「풍경만 다시」 — 고른 쪽만 그리고 나머지(`keep`)는 그대로 둔다.
    # 열 장을 다 다시 그리면 6분이 걸려서, 한쪽만 마음에 안 들 때 나머지까지 버리게 된다.
    kind = str(chosen.get("image_kind") or "").strip()
    if kind:
        shots = {k: (v if k == kind else 0) for k, v in shots.items()}
    # 그릴 종류만 남긴다 — 축마다 다르다(상황별일본어 인물·풍경 / 일본맛집 인물·음식).
    kinds = [k for k, v in shots.items() if v]
    want = " · ".join(f"{KIND_KO.get(k, k)}({k}) {shots[k]}장" for k in kinds)
    task = (
        f"주제 「{topic}」 · 확정 훅 「{hook}」 의 표지 배경 사진을 만들 "
        "이미지 생성 프롬프트를 지침서가 정한 대로 지어라. "
        # 장수·종류는 축마다 다르다. 일본맛집은 인물 5 + 음식 5 다(풍경은 안 쓴다 — 본문
        # 배경이 구글 지도의 실제 가게 사진이다). 장당 40~60초라 차이가 크다.
        f"{want} 를 낸다. 그보다 많이 내지 마라. 프롬프트는 영어로 쓴다.\n"
        # 아래 두 줄은 지침서에도 있지만 codex 가 긴 문서에서 흘린다. 실제로 「한국인」이
        # 한 번도 안 실려 일본인 남자 컷이 나갔다(2026-09-03). 여기서 다시 못박는다.
        "- 모든 컷은 그 주제의 장면이어야 한다. 주제와 무관한 일반 여행 사진을 내지 마라.\n"
        "- 인물이 따로 지정되지 않았으면 20대 한국인 여성으로 쓴다"
        "(프롬프트에 a Korean woman in her twenties 라고 적는다).\n"
        # 2026-09-07 되돌림 — 조명·소품 규칙을 여기서 따로 못박았다가 뺐다. 밝기를 밀면
        # 열 장이 다 `A bright…` 로 시작해 쇼룸이 됐고, 소품을 막으니 풍경 프롬프트가
        # 아예 0개가 나왔다. 그 자리는 지침서 「사진의 결」 문단이 맡는다.
        "- **「사진의 결」 문단은 네가 적지 않는다 — 화면이 프롬프트 뒤에 그대로 붙인다.** "
        "너는 장면만 쓴다. 사진의 결·화질·색감·분위기를 따로 적지 마라.\n"
        # 주제가 「멋있는 표현」이면 모델이 그 멋짐을 화면 연출로 번역한다. 대극장 계단에서
        # 팔 벌려 선언하는 컷, 스포트라이트 준 부채가 나왔다(2026-09-07 사람 신고 — 너무 과해).
        "- **과하게 연출하지 마라.** 인스타에 올리는 감성 스냅이지 화보나 영화 장면이 아니다. "
        "동작은 걷다가·앉아서·창밖을 보다가처럼 **작게** 하고, 극장·무대·스포트라이트처럼 "
        "한 컷을 위해 차린 배경을 만들지 마라. 프롬프트에 dramatic·cinematic·epic·heroic·"
        "grand·majestic·spotlight·staged·posing·sea of clouds 를 쓰지 마라. "
        "주제가 「멋있는·극적인」것이라도 그것을 화면 연출로 옮기지 않는다.\n"
        # 연출만 낮추라고 했더니 주제와 상관없는 조용한 컷으로 도망갔다 — 「쓸모없지만
        # 멋있는 표현」에 도서관·헌책방·버스 창가가 나왔다(2026-09-07 사람 신고).
        "- 차분하게 하되 **주제를 버리지 마라.** 인물 컷은 그 말을 실제로 쓰는 순간이라 "
        "**말이 오가는 자리**(친구와 마주 앉은 이자카야·점원 앞·역무원 앞·가라오케)를 고른다. "
        "도서관·헌책방·버스 창가처럼 혼자 조용히 있는 자리는 주제가 정말 혼잣말일 때만 쓴다. "
        "풍경 컷은 그 말을 쓰는 장소를 사람 없이 찍은 것이다 — 상관없는 명소·자연 풍경으로 빠지지 마라. "
        "각 컷마다 **왜 이 사진인지 주제와 한 줄로 이어지는지** 스스로 확인하고 안 이어지면 다시 짜라."
    )
    # 음식 컷은 이 축에만 있다(일본맛집). 안 적으면 「음식 든 사람」이 나와 인물 컷과 겹친다.
    if "food" in kinds:
        task += (
            "\n- **음식 컷에는 사람이 나오지 않는다.** 그 주제의 지역·메뉴에 실제로 있는 음식을 "
            "상 위에 놓인 그대로 잡는다. 가게 간판·메뉴판 글자를 그리지 마라. "
            "다섯 장을 같은 접시 클로즈업으로 채우지 말고 그릇·상차림·곁들이처럼 조금씩 다르게 잡는다."
        )
    plan = await studio._ask(
        "images", task,
        "{" + ", ".join(f'"{k}": ["prompt", ...]' for k in kinds) + "}",
        extra=_avoid_block(used or []),
        schema=studio.s_image_prompts(kinds),
        # 축을 안 넘기면 기본 축(상황별일본어) 지침서를 읽는다 — 맛집이 풍경 규칙을 받았다.
        axis=axis or studio.DEFAULT_AXIS,
    )
    # 지침서가 정한 장수까지만 자른다 — 모델이 더 내도 그리지 않는다(장당 40~60초).
    prompts = [(k, p) for k in kinds for p in (plan.get(k) or [])[: shots.get(k, 0)]]
    if not prompts:
        raise RuntimeError("이미지 프롬프트가 비었습니다.")

    # 결을 여기서 붙인다(`STYLE`). 모델이 쓴 것은 장면뿐이다.
    blobs = await codex_image.generate_images(
        [f"{p}\n\n{STYLE.get(kind, '')}".strip() for kind, p in prompts])
    images = []
    for (kind, prompt), blob in zip(prompts, blobs):
        if not blob:
            continue
        # 사진은 **화면이 있는 서버**에 올려야 보인다.
        url = await studio_remote.upload_image(blob, f"{secrets.token_hex(8)}.png")
        images.append({"kind": kind, "prompt": prompt, "url": url})
    if not images:
        raise RuntimeError("한 장도 만들지 못했습니다.")
    # 한쪽만 다시 그렸으면 다른 쪽을 앞에 붙여 되돌려준다 — 안 붙이면 화면에서 사라진다.
    return {"images": (keep or []) + images}


async def _do_body(chosen: dict[str, Any], axis: str) -> dict[str, Any]:
    from app.services import studio_steps as studio
    r = await studio.make_body(studio.BodyBody(
        axis=axis,
        topic=chosen.get("topic", ""),
        hook=" ".join(chosen.get("hook_lines", [])),
        guide_id=chosen.get("guide_id", ""),
        button=chosen.get("button", ""),
        region=chosen.get("region", ""),
    ))
    # 지도 축은 어느 버튼이었는지도 함께 올린다 — CTA1 의 수량이 그 버튼의 것이어야 한다.
    extra = {k: r[k] for k in ("guide_id", "button", "region", "n") if k in r}
    return {"body": r["items"], **extra}


async def _do_cta1(chosen: dict[str, Any], axis: str) -> dict[str, Any]:
    """지도 축에만 있는 3-4단계. 다른 축은 이 단계를 아예 거치지 않는다."""
    from app.services import studio_steps as studio
    r = await studio.make_cta1(studio.Cta1Body(
        axis=axis,
        topic=chosen.get("topic", ""),
        hook=" ".join(chosen.get("hook_lines", [])),
        items=chosen.get("items", []),
        n=int(chosen.get("n") or 0),
        guide_id=chosen.get("guide_id", ""),
        button=chosen.get("button", ""),
        region=chosen.get("region", ""),
    ))
    return {"cta1": r}


async def _do_caption(chosen: dict[str, Any], axis: str) -> dict[str, Any]:
    from app.services import studio_steps as studio
    r = await studio.make_caption(studio.CaptionBody(
        axis=axis,
        topic=chosen.get("topic", ""),
        # 지도 축 캡션은 **줄바꿈째로** 훅을 쓴다 — 한 줄로 펴는 일은 make_map_caption 이 한다.
        hook="\n".join(chosen.get("hook_lines", [])),
        items=chosen.get("items", []),
        cta1=chosen.get("cta1") or {},
    ))
    return {"caption": r["caption"]}


async def _do_build(chosen: dict[str, Any], axis: str) -> dict[str, Any]:
    from app.services import studio_steps as studio
    r = await studio.build(studio.BuildBody(
        axis=axis,
        topic=chosen.get("topic", ""),
        hook_lines=chosen.get("hook_lines", []),
        image_url=chosen.get("image_url", ""),
        items=chosen.get("items", []),
        caption=chosen.get("caption", ""),
        cta1=chosen.get("cta1") or {},
    ))
    return {"__result__": r}


async def _do_keep(chosen: dict[str, Any], axis: str) -> dict[str, Any]:
    """[보관] / [보관 해제] / [삭제] — 다음 회차 후보 목록을 손본다. 두 파일 모두 이 PC 에 있으므로
    화면이 직접 못 쓴다. 잔심부름으로 넘겨받아 여기서 처리한다."""
    from app.services import studio_steps as studio
    keeps = studio._keeps(axis)
    drops = studio._drops(axis)

    # [삭제] — 제외 목록에 쌓아 **다음 회차에도 안 나오게** 한다(2026-09-04 사람 지시).
    # 전에는 화면 안에서만 지워 다시 뽑기 한 번에 되살아났다.
    drop = str(chosen.get("drop_topic") or "").strip()
    if drop:
        if drop not in drops:
            drops.append(drop)
            studio._write_drops(drops, axis)
        if drop in keeps:
            # 보관해 둔 것을 지웠다면 보관함에서도 뺀다 — 안 그러면 그쪽에서 계속 올라온다.
            keeps = [k for k in keeps if k != drop]
            studio._write_keeps(keeps, axis)
        return {"kept": keeps, "dropped": drops}

    topic = str(chosen.get("keep_topic") or "").strip()
    if not topic:
        return {"kept": keeps, "dropped": drops}
    if chosen.get("keep_off"):
        # [보관 해제] — 목록에서만 뺀다. 이력과 무관하니 다시 후보로 나올 수 있다.
        keeps = [k for k in keeps if k != topic]
    elif topic not in keeps:
        keeps.append(topic)
    studio._write_keeps(keeps, axis)
    return {"kept": keeps, "dropped": drops}


async def _do_prepare(chosen: dict[str, Any], axis: str) -> dict[str, Any]:
    """출근 전에 **미리 다 만들어 둔다.**

    사람이 아침에 화면을 열면 주제 10개가 있고, 각 주제마다 훅·사진·본문·캡션이 이미
    만들어져 있어 **고르기만** 하면 된다. 지금까지는 누를 때마다 만들기 시작해 사진에서
    6분씩 기다려야 했다(2026-09-03 요구).

    ⚠ 사진·본문은 평소 「고른 훅」을 보고 짓지만, 여기서는 훅을 고르기 전이라 **주제만
      보고 짓는다.** 본문은 그 주제의 일본어 표현이라 훅과 거의 무관하고 사진도 마찬가지다.
      마음에 안 들면 화면에서 그 단계만 다시 뽑으면 된다.

    한 주제에 사진 10장이 붙어 제일 오래 걸린다(주제당 약 7분). 주제 수는 `prepare_count`
    로 줄일 수 있다 — 시험할 때 쓴다.
    """
    from app.services import studio_steps as studio

    count = int(chosen.get("prepare_count") or settings.STUDIO_PREPARE_COUNT or 10)
    # 보관해 둔 주제만으로 하루치가 차면 새 후보를 짓지 않는다(`make_topics` 의 `need`).
    first = await studio.make_topics(axis, need=count)

    # 보관해 둔 주제도 함께 미리 만든다. 사람이 [보관] 을 누른 것은 **다음 회차에 쓰려고**
    # 남긴 것이라, 정작 아침에 그것을 고르면 또 기다리게 된다(2026-09-03 실측 24초).
    # 미리 만드는 것은 **하루치(count)까지**다 — 보관해 둔 것이 먼저 자리를 잡고, 남은
    # 자리만 새 후보로 채운다(2026-09-09 사람 지시 — 「보관 중 앞의 10개까지만」).
    # 전에는 `count + len(kept)` 라 보관이 쌓일수록 밤마다 늘었다(19개면 29개까지).
    # 주제 하나가 가게 8곳을 조회하므로 그만큼 **사진 API 하루 쿼터가 마른다** —
    # 23개를 돈 날 사진 후보가 전부 한 장뿐이었다. 넘치는 보관 주제는 화면에서 고를 때
    # 그 자리에서 만든다.
    kept = first.get("kept") or []
    pool = ([{"topic": k, "why": "지난 회차에 보관해 둔 주제"} for k in kept]
            + list(first.get("items") or []))
    if not pool:
        raise RuntimeError("주제 후보가 비었습니다.")

    # 장소를 다루는 축은 **그 수를 채운 주제만** 사람에게 준다(2026-09-09 사람 지시 —
    # 「식당 8곳을 못 찾으면 그 주제는 제외하고 다른 주제로 찾아라」). 못 채운 주제는
    # 제외 목록으로 보내고 다음 후보로 넘어간다.
    need_places = int(studio.axis_conf(axis).get("places") or 0)
    # 다 떨어지는 밤에도 끝나야 한다 — 주제 하나에 5분쯤 걸리므로 시도는 두 배까지만.
    # 처음 후보(10개)가 모자라면 아래 반복에서 더 뽑아 이 횟수까지 채운다.
    max_tries = count * 2

    prepared: dict[str, Any] = {}
    topics: list[dict[str, Any]] = []       # 사람에게 보여줄 주제 = 자리를 채운 것만
    excluded: list[str] = []                # 8곳을 못 채워 제외한 주제
    # 앞 주제가 쓴 무대를 쌓아 뒤 주제에 넘긴다 — 안 그러면 결이 가까운 주제끼리 같은
    # 장면으로 몰린다(`_used_scenes`).
    used_scenes: list[str] = []
    tried: list[str] = []                   # 이미 시도한 주제 — 더 뽑은 후보와 겹치지 않게
    i = 0
    while i < max_tries and len(topics) < count:
        if i >= len(pool):
            # 후보가 떨어졌는데 하루치를 못 채웠다 — 새 후보를 더 뽑아 이어간다(2026-09-14
            # 사람 지시 — 「10개를 채울 때까지(최대 20번)」). 전에는 처음 뽑은 10개에서 멈춰
            # 일본맛집이 이틀 연달아 4개만 남았다. 제외한 주제는 이미 제외 목록에 올라 다시
            # 안 나오고, 살아남은 주제와 겹치는 것은 여기서 거른다.
            try:
                more = await studio.make_topics(axis)
                fresh = [m for m in (more.get("items") or [])
                         if str(m.get("topic") or "").strip() not in tried]
                fresh = await studio._drop_lookalikes(fresh, tried, axis)
            except Exception as e:
                # 여기서 던지면 이미 만든 주제까지 날아간다 — 만든 만큼만 주고 멈춘다.
                logger.warning(f"[studio-worker] 후보를 더 뽑지 못했습니다: {e}")
                break
            if not fresh:
                logger.warning("[studio-worker] 더 뽑은 후보가 전부 겹쳐 여기서 멈춥니다")
                break
            logger.info(f"[studio-worker] 후보가 떨어져 {len(fresh)}개를 더 뽑았습니다")
            pool += fresh
        t = pool[i]
        i += 1
        name = str(t.get("topic") or "").strip()
        if not name:
            continue
        tried.append(name)
        logger.info(f"[studio-worker] 미리 만들기 {len(topics) + 1}/{count} (후보 {i}) — {name}")
        try:
            # 훅부터. 사진·본문은 훅 없이 주제만 보고 짓는다(위 주석).
            # 지도 축은 주제가 곧 「어느 가이드의 어느 버튼」이다. 그 둘을 아래 단계로
            # 넘겨야 장소·지도·수량이 같은 버튼을 가리킨다.
            where = {k: t[k] for k in ("guide_id", "button", "region") if t.get(k)}

            hooks = await studio.make_hooks(studio.TopicBody(axis=axis, topic=name))
            body = await studio.make_body(studio.BodyBody(axis=axis, topic=name, hook="", **where))
            # 자리를 못 채웠으면 여기서 접는다 — 사진(6분)까지 짓고 버리면 그만큼 헛돈다.
            if need_places and len(body.get("items") or []) < need_places:
                logger.info(f"[studio-worker] {need_places}곳 중 {len(body.get('items') or [])}곳뿐 — "
                            f"주제를 제외합니다: {name}")
                studio.exclude_topic(name, axis)
                excluded.append(name)
                continue
            images = await _do_images({"topic": name, "hook_lines": [], **where}, axis, used_scenes)
            used_scenes += [str(i.get("prompt") or "") for i in (images.get("images") or [])]
            prepared[name] = {
                "hooks": hooks,
                "body": body.get("items") or [],
                "images": images.get("images") or [],
                **where,
                **({"n": body["n"]} if body.get("n") else {}),
            }
            # 지도 축에만 있는 3-4. 훅과 무관하게 주제·장소만 보고 지을 수 있어 미리 만든다.
            if studio.axis_conf(axis).get("cta1"):
                prepared[name]["cta1"] = await studio.make_cta1(studio.Cta1Body(
                    axis=axis, topic=name, hook="", items=body.get("items") or [],
                    n=int(body.get("n") or 0), **where))
                # ⚠ 캡션은 미리 만들지 않는다. 이 축 캡션은 **고른 훅을 그대로 끌어다 쓰는
                #   고정 틀**이라(지도_5단계) 훅이 정해지기 전에는 만들 수 없다. 억지로
                #   맡겼더니 「확정 훅 문구를 보내주세요」라는 요청문이 캡션으로 나왔다
                #   (2026-09-04). 조립이라 훅을 고른 뒤 몇 초면 끝난다.
            else:
                caption = await studio.make_caption(studio.CaptionBody(
                    axis=axis, topic=name, hook="", items=body.get("items") or []))
                prepared[name]["caption"] = caption.get("caption") or ""
            topics.append(t)
        except studio.TopicUnfit as e:
            # 「가게를 하나도 못 찾았다」 같은 **주제 탓**이다 — 내일도 같은 답이 나온다.
            logger.warning(f"[studio-worker] 주제를 제외합니다 — {name}: {e}")
            studio.exclude_topic(name, axis)
            excluded.append(name)
        except Exception as e:
            # 이쪽은 주제 탓이 아니다(codex CLI 오류·조회 실패). 제외하지 않고 넘어간다 —
            # 일시적인 실패로 멀쩡한 주제를 영영 지우면 안 된다.
            logger.warning(f"[studio-worker] 미리 만들기 실패 — {name}: {e}")

    logger.info(f"[studio-worker] 미리 만들기 끝 — {len(topics)}/{count} 주제"
                + (f" · 제외 {len(excluded)}개" if excluded else ""))
    return {"topics": topics,
            "kept": [k for k in kept if k not in excluded],
            "dropped": [*(first.get("dropped") or []), *excluded],
            "prepared": prepared}


HANDLERS = {
    "topics": _do_topics,
    "prepare": _do_prepare,
    "keep": _do_keep,
    "hooks": _do_hooks,
    "images": _do_images,
    "body": _do_body,
    "cta1": _do_cta1,          # 지도 축에만 있다
    "caption": _do_caption,
    "build": _do_build,
}


async def _handle(job: dict[str, Any]) -> None:
    from app.services import studio_remote

    session_id = job["id"]
    step = job["step"]
    handler = HANDLERS.get(step)
    if not handler:
        logger.warning(f"[studio-worker] 모르는 단계: {step}")
        return

    logger.info(f"[studio-worker] {session_id} · {step} 시작")
    chosen = job.get("chosen") or {}
    try:
        if step == "images":
            # 이 회차가 이미 쓴 무대를 피해서 그린다(밤에 만들 때는 `_do_prepare` 가 넘긴다).
            kind = str(chosen.get("image_kind") or "").strip()
            used, mine = await _scene_context(session_id, str(chosen.get("topic") or ""))
            # 한쪽만 다시 그릴 때 남겨 둘 것. 남기는 것도 무대가 겹치면 안 된다.
            keep = [i for i in mine if kind and i.get("kind") != kind]
            used += [str(i.get("prompt") or "") for i in keep]
            out = await _do_images(chosen, job.get("axis") or "", used, keep)
        else:
            out = await handler(chosen, job.get("axis") or "")
    except Exception as e:
        logger.exception(f"[studio-worker] {session_id} · {step} 실패")
        await studio_remote.call(f"/studio-sessions/{session_id}", {"error": str(e)}, method="PATCH")
        return

    body: dict[str, Any] = {"pending": ""}      # 이제 사람이 고를 차례
    if "__result__" in out:
        body["result"] = out["__result__"]
    else:
        body["candidates"] = out
    await studio_remote.call(f"/studio-sessions/{session_id}", body, method="PATCH")
    logger.info(f"[studio-worker] {session_id} · {step} 끝")


# 앞서 만들어 둔 것을 「아직 쓸 만하다」고 볼 시간. 23:00 → 06:00(7시간)은 안에 들고,
# 하루 뒤(24시간)는 밖으로 나간다.
FRESH_HOURS = 12


async def _has_fresh_batch(axis: str) -> bool:
    """그 축에 **손도 안 댄 미리 만들기 회차**가 아직 남아 있는지.

    전역 시각이 둘(23:00·06:00)인 것은 「한 번 실패해도 아침에 빈손이 되지 않게」 둔
    보험인데, 앞의 것이 멀쩡하면 뒤의 것이 회차를 하나 더 열어 **주제 목록이 통째로
    바뀌었다** (2026-09-08 사람 신고 — [다시 뽑기] 를 안 눌렀는데 주제가 또 생성됐다).
    앞의 것이 살아 있으면 뒤는 돌지 않는다.

    ⚠ `created_at` 은 **서버 시계**다(2026-09-08 확인 — 23:00 KST 회차가 14:00 으로
      적혀 있다. 서버는 UTC). 시계가 어긋나 나이가 음수거나 너무 크게 나오면 판단하지
      않고 **그냥 만든다** — 잘못 건너뛰어 아침에 빈손이 되는 쪽이 훨씬 나쁘다.
    """
    from datetime import timedelta, timezone
    from urllib.parse import quote

    from app.services import studio_remote
    try:
        got = await studio_remote.call(
            f"/studio-sessions/latest?axis={quote(axis)}", method="GET")
    except Exception as e:
        logger.warning(f"[studio-worker] 「{axis}」 지난 회차를 확인하지 못했습니다: {e}")
        return False
    if not (got or {}).get("id") or not (got.get("candidates") or {}).get("prepared"):
        return False
    try:
        made = datetime.fromisoformat(str(got.get("created_at") or ""))
    except ValueError:
        return False
    age = datetime.now(timezone.utc).replace(tzinfo=None) - made
    return timedelta(0) <= age < timedelta(hours=FRESH_HOURS)


async def _maybe_start_nightly(done: set[str]) -> None:
    """정해진 시각이 되면 축마다 **미리 만들기**를 스스로 연다.

    사람이 출근했을 때 이미 다 되어 있어야 한다는 요구(2026-09-03). 주제 10개면
    한 시간 넘게 걸리니 출근 몇 시간 전쯤으로 잡는다.

    시각은 **축마다 다를 수 있다.** `studio_steps.AXES[축]["prepare_at"]` 에 적으면 그
    축만 그 시각에 돈다 — 안 적은 축은 전역 `STUDIO_PREPARE_AT`("23:00,06:00" 처럼
    쉼표로 여러 개)을 그대로 쓴다. 한 축에 여러 시각을 주면, 한 번이 실패해도 아침에
    빈손이 되지 않게 두 번 도는 셈이다.
    (2026-09-03 — 일본맛집만 오전 4시 한 번으로 정했다. 9시에 사람에게 알리는 건 이
    파일이 아니라 **봇의 `studio-notify.js`** 가 한다 — Discord 로 보내려면 봇 토큰이
    있어야 하는데 그건 봇 프로세스에만 있다.)

    폴링이 5초마다 도므로 **날짜+시각+축**으로 잠가 한 번만 연다.
    """
    from app.services import studio_remote
    from app.services.studio_steps import AXES

    now = datetime.now()
    at = now.strftime("%H:%M")
    global_times = [t.strip() for t in (settings.STUDIO_PREPARE_AT or "").split(",") if t.strip()]

    for axis, conf in AXES.items():
        times = conf.get("prepare_at") or global_times
        if at not in times:
            continue
        stamp = f"{now:%Y-%m-%d} {at} {axis}"
        if stamp in done:
            continue
        done.add(stamp)
        # 이틀치만 기억하면 충분하다 — 무한정 쌓이지 않게 잘라 둔다.
        if len(done) > 16:
            for old in sorted(done)[:-8]:
                done.discard(old)

        if await _has_fresh_batch(axis):
            logger.info(f"[studio-worker] {at} — 「{axis}」 아직 안 쓴 회차가 있어 건너뜁니다")
            continue

        logger.info(f"[studio-worker] {at} — 「{axis}」 미리 만들기 시작 (주제 {settings.STUDIO_PREPARE_COUNT}개)")
        try:
            # 여는 순간 prepare 로 연다. 만든 뒤 바꾸면 그 사이에 다른 단계가 끼어든다.
            await studio_remote.call("/studio-sessions/", {"axis": axis, "pending": "prepare"})
        except Exception as e:
            logger.warning(f"[studio-worker] 「{axis}」 미리 만들기를 열지 못했습니다: {e}")


async def _loop() -> None:
    from app.services import studio_remote

    logger.info(f"[studio-worker] 시작 — {settings.STUDIO_API_BASE} 를 {POLL_SECONDS}초마다 봅니다")
    from app.services.studio_steps import AXES

    for axis, conf in AXES.items():
        at = ",".join(conf.get("prepare_at") or []) or settings.STUDIO_PREPARE_AT
        if at:
            logger.info(f"[studio-worker] 「{axis}」 매일 {at} 에 미리 만들기 예약됨")
    prepared_at: set[str] = set()
    # 같은 회차를 두 번 집지 않는다(한 단계가 몇 분씩 걸리므로 그 사이 폴링이 여러 번 돈다).
    busy: set[str] = set()

    while True:
        try:
            await _maybe_start_nightly(prepared_at)
            data = await studio_remote.call("/studio-sessions/pending", method="GET")
            for job in data.get("jobs", []):
                if job["id"] in busy:
                    continue
                busy.add(job["id"])

                async def run(j=job) -> None:
                    try:
                        await _handle(j)
                    finally:
                        busy.discard(j["id"])

                asyncio.create_task(run())
        except Exception as e:
            logger.warning(f"[studio-worker] 물어보기 실패: {e}")
        await asyncio.sleep(POLL_SECONDS)


def start() -> None:
    """앱이 뜰 때 부른다. 조건이 안 맞으면 조용히 넘어간다 (서버에서도 임포트되는 코드다)."""
    global _task
    if _task and not _task.done():
        return
    if not is_enabled():
        logger.info("[studio-worker] 켜지 않음 — codex 나 STUDIO_API_BASE 가 없습니다")
        return
    _task = asyncio.create_task(_loop())
