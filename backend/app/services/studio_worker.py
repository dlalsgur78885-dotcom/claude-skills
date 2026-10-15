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
import zlib
from datetime import datetime
import secrets
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)

# 사람이 고르는 사이엔 할 일이 없다. 너무 자주 물으면 서버만 두드린다.
POLL_SECONDS = 5

# X인용 후보 한 줄에 딸려 오는 **게시물 정보**. 주제를 고를 때 이것들이 함께 따라와야
# 표지가 원본 사진을 쓰고(`_do_images`) 본문에 캡처가 붙는다(`_do_body_x`).
# 화면은 고른 주제의 **제목 한 줄만** 넘기므로 일꾼이 후보를 되짚어 채운다.
X_CARRY = ("post_id", "url", "photos", "photo_urls", "text",
           "views", "likes", "replies", "author",
           # 「일본 반응」 장 재료(2026-09-21). 이게 안 따라오면 그 장이 조용히 사라진다.
           "reply_quotes")

_task: asyncio.Task | None = None


def _accounts() -> list[str]:
    """일꾼이 회차를 물어볼 계정들 — 기본 계정 + STUDIO_ACCOUNTS 에 적힌 계정.

    사람마다 자기 계정으로 화면을 쓰고, 만들어진 캐러셀도 그 사람 계정에 생긴다.
    축·지침서·단계는 한 벌을 같이 쓴다(계정별로 나누지 않는다).
    """
    names = [settings.STUDIO_ACCOUNT] if settings.STUDIO_ACCOUNT else []
    for pair in settings.STUDIO_ACCOUNTS.split(","):
        name = pair.strip().partition(":")[0].strip()
        if name and name not in names:
            names.append(name)
    return names


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


def _hook_source(t: dict[str, Any]) -> str:
    """X인용 훅에 함께 넘길 원문 — 작성자·본문. 원문이 없는 축은 빈 문자열이다."""
    text = str(t.get("text") or "").strip()
    if not text:
        return ""
    who = str(t.get("author") or "").strip()
    handle = str(t.get("account") or "").strip()
    byline = " ".join(x for x in (who, f"@{handle}" if handle else "") if x)
    return f"작성자: {byline or '알 수 없음'}\n원문: {text}"


async def _do_hooks(chosen: dict[str, Any], axis: str) -> dict[str, Any]:
    from app.services import studio_steps as studio
    r = await studio.make_hooks(studio.TopicBody(
        axis=axis, topic=chosen.get("topic", ""), source=_hook_source(chosen)))
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
        "Shoot it like an emotive Instagram travel-influencer snapshot. The person looks like a real, "
        "natural person, yet noticeably more beautiful and appealing than an ordinary everyday "
        "photo: a photogenic face, refined styling, a natural expression and pose. Avoid overly "
        "documentary realism and plain, unremarkable looks; keep the balance between naturalness "
        "and idealized good looks. Still, it should look like a snapshot a traveler took on a "
        "phone, with visible skin texture and stray flyaway hairs left as they are — "
        "the kind of photo that shows up in an Instagram feed. Natural light as if shot on an "
        "iPhone, with unedited phone-camera color (the iPhone photo look, no filter or color "
        "grading), and a refined travel-photo mood. Keep other people out of the frame as much "
        "as possible; if someone must appear, show only a small, out-of-focus part of them with "
        "no visible face."
    ),
    "scenery": (
        "Shoot it like a beautiful, emotive Instagram travel photo taken on location: natural "
        "light, a composition with depth, unedited phone-camera color (the iPhone photo look, "
        "no filter or color grading). If any "
        "text appears, render every character accurately and clearly — never include broken "
        "glyphs, fake characters, random letters, or distorted numbers and symbols. If accurate "
        "text is not possible, leave the space clean instead of generating unnecessary lettering."
    ),
    # 일본맛집 표지 후보(2026-09-09). 사람이 안 나오는 대신 음식이 주인공이라
    # 인물 결을 그대로 쓰면 「예쁜 사람 없는 여행 사진」이 된다.
    # 2026-09-22 사람 지시 — 「음식 사진을 좀 더 실제 후기 사진처럼」. 원본은
    # `일본맛집_3-2단계_썸네일이미지.md` 「음식 사진의 결」이다 — 한쪽을 고치면 같이 고친다.
    # 2026-10-07 사람 지시 — 「구겨진 휴지, 가루 흘린 것까지 너무 리얼하게 만들지 말고,
    # 사실적으로 찍은 이미지인데 정신없어 보이지 않고 깔끔하게」. 사진 결은 그대로 두고
    # 상 위의 생활감(쓴 물수건·부스러기·흘린 소스·잡동사니)만 걷어낸다.
    # 2026-10-07 사람 지시 — 「정갈한 건 좋은데 먹음직스럽지가 않아. 먹음직스럽게」.
    # 깔끔한 상은 그대로 두고 **음식 자체**를 갓 나온 상태(김·윤기·단면)로 당기고 더
    # 가까이 찍는다. 광고 사진으로 되돌리는 것이 아니다.
    # 2026-10-15 사람 지시 — 「좀 더 먹음직스러운 음식으로. 특히 디저트 주제라면 흔한 디저트
    # 말고 누구나 먹어보고 싶은 디저트로」. ① 2026-10-12 개정(그릇이 화면을 꽉 채우고
    # 가장자리가 잘려 나간다)을 여기도 반영했다 — 전엔 「짧은 변의 3분의 2 · 둘레를 비워」가
    # 남아 새 규칙과 어긋났다. ② 디저트 문단을 넣었다(흔한 것 금지 · 층·단면·흘러내림).
    "food": (
        "Make it look like a real customer review photo, not a styled advertisement or magazine "
        "food shot: taken on a phone by a diner sitting at the table, the kind of photo people "
        "post in a Google Maps or blog restaurant review. Shoot from the seat at eye level looking "
        "slightly down (about 45 degrees) or straight down over the table — no tight advertising "
        "macro. Keep the restaurant's real table setting in the frame: its own table, tray or "
        "wooden counter. No studio props — no white backdrop, marble or linen. Keep the table "
        "clean and uncluttered — the food is the only subject: no crumpled tissues, napkins or "
        "used wet towels, no crumbs, spilled sauce or stains on the table, no half-eaten dishes, "
        "empty plates or leftover glasses, no clutter such as condiment bottles, toothpick "
        "holders, menus or flyers, and no hands. At most one or two simple items that belong "
        "there, such as chopsticks or a water glass. "
        "Above all the food must look delicious: not a tidied-up plate but a dish just served "
        "that you want to eat right now. The hero dish fills the whole frame and its rim is "
        "cropped off by the frame's edge — never shoot it small with space left around it — "
        "close enough that its texture is visible: noodle strands, the grain of the meat, beads "
        "of oil. Keeping the table clean is about not looking cluttered, it is not a reason to "
        "shoot the food from far away. Keep the signs of food straight off "
        "the stove: steam rising from broth or noodles, the glossy sheen of sauce, oil and "
        "juices, char marks and a crisp crust where it was grilled, melting cheese or butter, a "
        "soft egg yolk about to break, condensation on the glass for cold dishes — but only what "
        "that dish really produces: no blown-in smoke, brushed-on oil or fake droplets. Show "
        "what is inside: bowls heaped so the toppings spill toward the rim, meat sliced to show "
        "the pink inside, bread or dessert cut so the layers show. If the dish is a dessert or a "
        "cafe menu, make it one worth travelling for, never the kind found in any ordinary cafe: "
        "the visible layers of a tall parfait glass, a souffle, pudding or fondant cut so the "
        "inside flows out, a tart or fruit sando piled high with fruit, a torched brulee top, "
        "cream or sauce running down the side, a portion too large for one hand, the local "
        "ingredient plainly visible (matcha, hojicha, Hokkaido milk, melon, chestnut, "
        "strawberry) — not a plain slice of cake, a standard tiramisu or cheesecake, a cup of "
        "soft serve, a few macarons or coffee with a cookie. For desserts the just-made signs "
        "are melting, dripping, gloss, condensation on the glass and freshly dusted powder "
        "rather than steam or char. The portion stays real, the "
        "dish is untouched, and nothing is rearranged or garnished for the photo. The "
        "restaurant's own lighting (ceiling lights, warm bulbs or window light) falling across "
        "the food from the side or slightly behind, so the sheen catches and the dish has depth "
        "— no flat, pale, direct-flash light; unedited "
        "phone-camera color (the iPhone photo look, no filter or color grading), and only a "
        "slightly soft background — no heavy portrait-mode blur. Ingredient colors stay fresh "
        "and true: no congealed fat, grey meat, dried-out rice or washed-out vegetables. No "
        "people in the frame, and never a hand lifting noodles or holding chopsticks. Do not "
        "render any text, signage or logos — leave the space clean instead of generating "
        "lettering."
    ),
}

# 셀카 결은 **이 축만** 쓴다 (2026-09-30 사람 지시 — 「일본 맛집2 캐러셀 인물 이미지만 셀카를
# 찍은 느낌으로 하고, 나머지 인물 사진은 원래대로 해줘」). 2026-09-29 에 모든 축에 넣었던 것을
# 한 축으로 좁힌 것이다 — 다른 축은 남이 찍어 준 스냅 결로 돌아갔다.
# 원본은 `일본맛집2_3-2단계_썸네일이미지.md` 「인물 5장은 셀카」다 — 한쪽을 고치면 같이 고친다.
SELFIE_AXIS = "일본맛집2"
PERSON_SELFIE = (
    "Make it a selfie the person took themselves: they hold the phone in their own hand at "
    "arm's length, so the camera is close and just above eye level looking slightly down, "
    "their face and upper body fill much of the frame, and the place is visible behind them. "
    "The arm or shoulder holding the phone may just catch the edge of the frame. It is not a "
    "photo someone else took from a distance and not a tripod shot. "
)

# 축마다 결이 다른 종류만 덮어쓴다. 없으면 위 `STYLE` 그대로다.
# 2026-09-22 사람 지시 — 「일본 영화 포스터 느낌이 나는 풍경. 지나가는 사람·그림자 같은 흔적은 있어도 된다」.
# 원본은 `상황별일본어_3-2단계_썸네일이미지.md` 「[풍경 이미지]」다 — 한쪽을 고치면 같이 고친다.
# ⚠ cinematic·dramatic 은 쓰지 않는다(「과하게 연출하지 않는다」). 조용한 일상 영화 포스터 쪽이다.
# 2026-09-22 사람 지시 — 「영화 포스터 색감은 지브리 같은 애니메이션 색감. 너무 화려하지 않게, 적당히
# 트인 풍경, 사진만 봐도 일본인 줄 알게」. 스튜디오 이름은 넣지 않고 색을 풀어 쓴다 — 이름을 넣으면
# 사진이 아니라 그림으로 그릴 수 있다. 「여백」도 쓰지 않는다(테두리를 그린다 — 지침서 「여백 금지」).
AXIS_STYLE = {
    SELFIE_AXIS: {"person": PERSON_SELFIE + STYLE["person"]},
    "상황별일본어": {
        "scenery": (
            "Make it feel like the key visual of a quiet Japanese slice-of-life film poster — the "
            "understated, everyday kind, not a blockbuster — while still being a real place "
            "photographed on location, not a set and not an illustration or painting. Give it the "
            "color of the hand-painted backgrounds in classic Japanese animated films: soft clear "
            "blue skies with white clouds, fresh greens, warm gentle sunlight, clean and gently "
            "saturated colors — fresh and lively but never flashy, neon or oversaturated. Soft "
            "natural light, a calm, open composition with depth "
            "and plenty of sky, street or wall around the subject so the frame feels airy and "
            "still. A fine film grain. Anyone should tell at a glance that this is Japan: show "
            "everyday Japanese details that fit the scene, such as {motifs}. Natural traces of "
            "people are welcome when they fit the scene — a small passerby in the distance, a "
            "figure seen from behind, a shadow falling on the ground — but no main character, no "
            "face in focus, never crowded. No poster title, credits or logos: the photo only. If "
            "any text appears in the scene, render every character accurately and clearly — never "
            "include broken glyphs, fake characters, random letters, or distorted numbers and "
            "symbols. If accurate text is not possible, leave the space clean instead of "
            "generating unnecessary lettering."
        ),
    },
}
# 풍경 컷 장면을 지을 때 사람을 어디까지 넣나(아래 task). 없으면 「사람 없이」.
# 2026-09-22 사람 지시 — 「사람이 막 떠난 빈자리」 표현을 지운다. 사람을 빼라고 하니 모델이
# 「대화가 끝난 뒤의 빈 테이블·빈 벤치」로 지어 50장 중 44장이 empty 였고, 전체가 칙칙해졌다.
SCENERY_PEOPLE = {
    "상황별일본어": (
        "주인공 인물 없이(멀리 지나가는 사람·뒷모습·그림자처럼 장면에 어울리는 흔적은 넣어도 된다. "
        "사람이 막 떠난 빈 테이블·빈 벤치처럼 「~한 뒤」의 빈자리로는 짓지 않는다)"
    ),
}
# 풍경 컷 자리를 고를 때 덧붙이는 말(아래 task). 없으면 비운다.
# 2026-09-22 사람 지시 — 「사진만 봐도 일본이라는 느낌」. 위로할 때 풍경이 병원 대기실·호텔 복도처럼
# 어느 나라인지 모를 실내로 나왔다.
# 2026-10-12 사람 신고 — 「풍경 이미지가 거의 다 비슷해보여」. 여기 적혀 있던 일본 요소 6개
# (전선 골목·기와지붕·자판기·건널목·노렌·역 플랫폼)가 영어 결(`AXIS_STYLE`)에도 같이 있어
# 두 번 실렸고, 모델이 그 여섯 개 밖으로 안 나갔다. 요소 목록은 `JAPAN_MOTIFS` 가 회차마다
# 섞어 붙이니 **여기서는 자리 고르는 기준만** 말한다.
SCENERY_PLACE = {
    "상황별일본어": (
        "사진만 봐도 일본인 줄 알게, 장면에 어울리는 일본 일상 요소가 보이는 자리를 고른다"
        "(어느 요소를 담을지는 화면이 회차마다 바꿔 붙인다 — 네가 못박지 마라). "
    ),
}

# 인물 컷마다 머리·시선을 **순서대로** 붙인다(2026-09-22 사람 지시 — 「단발머리가 하나도 없고
# 카메라를 보는 컷도 하나도 없다」). 안 적으면 모델이 다섯 장을 전부 긴 머리·딴 곳 보는 컷으로 낸다.
# 앞 세 장은 여성이라 머리 셋을 하나씩, 뒤 두 장은 여성이 아니라 머리는 비운다(아래 task 의 「마지막 2장」).
# 2026-09-29 사람 지시 — 인물은 셀카다. 렌즈를 보는 것이 기본이 되고, 딴 곳 보는 장이 2·5번째 두 장이다.
# 2026-09-30 사람 지시 — 셀카는 `SELFIE_AXIS`(일본맛집2) 한 축만이다. 다른 축은 되돌려,
#   딴 곳을 보는 것이 기본이고 카메라를 보는 장이 두 장(도는 여성 한 장·4번)이다.
# 지침서 「사진의 결」의 머리·시선 줄과 짝이다 — 한쪽을 고치면 같이 고친다.
_AWAY_SELFIE = ("While holding the phone out for the selfie the person turns their face away from the "
                "lens for a moment, looking off at the scene beside them — still an arm's-length "
                "selfie, just not looking into the lens.")
_TOWARD_SELFIE = ("The person looks straight into the lens of the phone they are holding, with a "
                  "relaxed, natural expression — not a fashion shoot.")
_AWAY = ("The person is not looking at the camera — their eyes are on the scene beside them "
         "(the view, the shop, the food), caught in the middle of the moment.")
_TOWARD = ("The person turns to look at the camera for a moment, as if a friend had just called "
           "their name, with a relaxed, natural expression — not a fashion shoot.")
_HAIRS = (
    "a short chin-length bob",
    "hair tied back in a ponytail or a loose bun",
    "long hair worn down",
)

# 셀카 축(`SELFIE_AXIS`)의 인물 5장이 **같은 사람·같은 각도**로 나왔다(2026-10-02 사람 신고 —
# 「왜 자꾸 같은 사람이 나와. 다른 사람, 다른 각도로」). 머리·시선만 나눠 붙이고 나머지가 다섯 장
# 다 같은 문장(20대 한국인 여성 · 팔 뻗어 든 폰)이라 모델이 같은 얼굴·같은 구도를 반복했다.
# 그래서 컷마다 **생김새·옷** 과 **폰을 든 자리(각도)** 를 하나씩 붙인다.
# 조합은 `_rotate` 로 돌린다. 돌리는 씨앗은 **뽑을 때마다 새로 만든다**(아래 `look_seed`)
# — 2026-10-02 사람 지시 「뽑을 때마다 사람, 각도 바뀌도록」. 전에는 주제로만 돌려
# 같은 주제로 다시 누르면 다섯 명이 그대로 다시 나왔다.
# 지침서 `일본맛집2_3-2단계_썸네일이미지.md` 「인물 5장은 셀카」와 짝이다 — 한쪽을 고치면 같이 고친다.
_DIFFERENT_PERSON = ("A different person from the other cuts — a new face, not the same model "
                     "photographed again.")
# 앞 세 장(여성)용. 머리 모양은 `_HAIRS` 가 맡으므로 여기엔 적지 않는다.
_FACES_W = (
    "a round face with soft full cheeks, petite, in a cream knit top",
    "a slim oval face with a clear jawline, tall and lean, in an oversized denim shirt",
    "a small face with light freckles over the nose, average build, in a black camisole and a thin cardigan",
    "monolid eyes and a wide easy smile, softly built, in a pale blue striped tee",
    "high cheekbones and bare-faced makeup, slender, in a white cotton shirt",
    "a heart-shaped face with round double-lidded eyes, short, in a pastel cardigan",
)
# 마지막 두 장용 — 여성이 아니라(20대 한국인 남성이나 주제에 어울리는 인물) 머리까지 여기서 적는다.
_FACES_X = (
    "a squarish face with a strong jaw and short cropped hair, broad-shouldered, in a plain black tee",
    "thin gold-rimmed glasses and a soft side-parted cut, lean, in a beige linen shirt",
    "a tanned face with thick brows and a buzz cut, sturdy, in a navy half-zip sweatshirt",
    "a round face with a gentle smile and slightly grown-out hair, average build, in a grey hoodie",
    "an angular face with a messy crop under a cap, lean, in an olive work jacket",
)
# 셀카라 각도는 「폰을 어디에 들었나」로 적는다. 시선(`_AWAY_SELFIE`·`_TOWARD_SELFIE`)과 겹치지
# 않게 **든 자리와 잡히는 범위만** 적는다 — 어디를 보는지는 여기서 적지 않는다.
# 2026-10-02 사람 신고 — 「각도가 다 비슷해. 왼쪽 사람, 오른쪽 음식 형식」. 폰을 든 자리만
# 적었더니 다섯 장이 전부 **사람 왼쪽·음식 오른쪽·눈높이**로 수렴했다(가로 캔버스라 더 그렇다).
# 그래서 한 줄마다 **사람이 화면 어디에 얼마나 크게 들어가고 음식·가게가 어디에 오는지**까지 박는다.
_SELFIE_ANGLES = (
    "Camera and framing: the phone is held high above the forehead and angled steeply down, so the "
    "shot looks down on both the person and the table — the person is low in the frame and the "
    "dishes spread out above and around them.",
    "Camera and framing: the phone is held very close, so the person's face fills most of the "
    "frame as a tight head-and-shoulders close-up; the food and the room are only a soft, partly "
    "cut-off sliver behind one shoulder.",
    "Camera and framing: the phone is held out to one side with the person standing on the RIGHT "
    "side of the frame, turned three-quarters toward it, while the left half opens onto the depth "
    "of the restaurant — the counter, other tables, the window.",
    "Camera and framing: the phone is held low, around chest height and tilted up, so the shot "
    "looks up at the person from below — they sit in the middle of the frame with the ceiling "
    "lights, noren or the upper wall of the restaurant behind them.",
    "Camera and framing: the phone is held far out with the elbow catching a corner, a loose wide "
    "crop — the person is small in the frame and the whole table and the room around them are "
    "visible, like a photo taken to show the place rather than the face.",
    "Camera and framing: the phone is held just over the food looking back at the person, so a "
    "dish sits large in the foreground at the center and the person appears smaller behind it, "
    "half-cut by the edge of the frame.",
)


# 풍경 5장이 서로 똑같아 보였다(2026-10-12 사람 신고 — 「상황별 일본어 캐러셀에 풍경 이미지가
# 거의 다 비슷해보여」). 인물은 컷마다 머리·시선을 돌려 붙이는데(`person_looks`) 풍경은 다섯 장에
# 같은 결 한 덩이만 붙어, 결에 박힌 「아침 햇살·역광」과 일본 요소 여섯 개로 수렴했다.
# 그래서 **시간대·빛**과 **거리감**을 컷마다 하나씩 붙인다(`scenery_looks`).
# ⚠ 「흐린 날·바랜 색」은 넣지 않는다 — 2026-09-22 사람 지시(「풍경이 칙칙하다」)로 지운 것이다.
#   맑고 산뜻한 쪽에서만 시간대를 나눈다.
_SCENERY_TIME = (
    "Time and light: early morning, the low sun coming in from the side so long soft shadows "
    "stretch across the ground and the air still looks cool and clear.",
    "Time and light: late morning under a bright clear sky with white clouds, open daylight, "
    "the colors fresh and the shadows short.",
    "Time and light: midday with the sun high, strong clean light and crisp shadows, the sky a "
    "deep clear blue over the scene.",
    "Time and light: mid-afternoon, warm sunlight slanting in from behind the scene so the edges "
    "catch the light and a gentle haze sits in the distance.",
    "Time and light: the golden hour just before sunset, warm amber light washing the walls and "
    "the sky turning soft orange and pink, still bright and clear — not dark.",
    "Time and light: right after rain on a bright day, the ground still wet and reflecting the "
    "sky while the clouds break open and sunlight returns.",
)
# 거리감은 「여백이 있는 트인 구도」(2026-09-22 사람 지시) 안에서 나눈다 — 꽉 찬 클로즈업은 없다.
_SCENERY_DISTANCE = (
    "Distance and framing: a wide view taken from far back across the street, the place small in "
    "the middle of a broad open frame.",
    "Distance and framing: eye level in the middle of the path looking straight ahead, the way "
    "opening into the distance with room on both sides.",
    "Distance and framing: one nearby thing (a wall, a post, a doorway, leaves) sitting large at "
    "the edge of the frame while the open space behind it carries the scene.",
    "Distance and framing: looking slightly down on the place from a little above, such as from "
    "steps, a slope or a bridge, so the ground and the road spread out below.",
    "Distance and framing: looking slightly up from low down, so the roofline, wires or the "
    "station canopy cut across a wide open sky.",
)
# 일본 요소는 **회차마다 섞어** 세 개만 싣는다. 여섯 개를 늘 같이 실으면 골목·건널목·플랫폼만 나온다.
JAPAN_MOTIFS = (
    "narrow streets running under overhead power lines",
    "tiled roofs over old wooden houses",
    "a vending machine standing at the roadside",
    "a railway crossing with its striped barrier",
    "noren curtains hanging in a shop doorway",
    "a local train platform with its station sign",
    "a covered shopping street with hanging banners",
    "a narrow canal lined with low houses and a small bridge",
    "a stone torii and steps at the edge of the neighborhood",
    "bicycles parked along a concrete block wall with potted plants",
    "a bus stop sign on a quiet road with fields behind it",
    "a small shrine's stone lanterns between the houses",
    "a river embankment path with cherry trees along it",
    "paper lanterns and a hand-painted shop sign under the eaves",
)


def _rotate(items: tuple[str, ...], seed: str, n: int) -> list[str]:
    """주제로 시작 자리를 밀어 `n` 개를 겹치지 않게 뽑는다. 회차가 바뀌면 조합도 바뀐다."""
    seed = (seed or "").strip()
    start = zlib.crc32(seed.encode("utf-8")) % len(items) if seed else 0
    return [items[(start + i) % len(items)] for i in range(n)]


def gaze_index(seed: str) -> int:
    """여성 3장 중 **시선이 나머지 두 장과 다른 자리**(0~2). 회차마다 돌아간다.

    셀카 축(`SELFIE_AXIS`)은 렌즈를 보는 것이 기본이라 이 자리가 **딴 곳을 보는 자리**고,
    다른 축은 반대로 이 자리가 **카메라를 보는 자리**다(2026-09-30 — 셀카를 한 축으로 좁혔다).

    2026-09-23 사람 지시 — 「왜 묶은 머리 여자만 매번 카메라를 응시하나」. 머리와 시선이
    같은 번호에 붙박여 있어 여성 카메라 컷이 늘 2번(묶은 머리)이었다. 자리는 씨앗으로 정한다.

    ⚠ 씨앗은 부르는 쪽이 준다(`look_seed`). 셀카 축은 **뽑을 때마다 바뀌는 씨앗**이고
    (2026-10-02 사람 지시), 다른 축은 주제 그대로다.
    """
    seed = (seed or "").strip()
    return zlib.crc32(seed.encode("utf-8")) % len(_HAIRS) if seed else 1


def scenery_looks(seed: str, n: int) -> list[str]:
    """풍경 컷마다 붙는 **시간대·빛**과 **거리감**. 컷마다 다르고 조합은 씨앗으로 돌아간다.

    2026-10-12 사람 지시로 넣었다 — 다섯 장이 다 아침 햇살·트인 골목이라 같은 사진처럼 보였다.
    지침서 `상황별일본어_3-2단계_썸네일이미지.md` 「[풍경 이미지]」와 짝이다 — 한쪽을 고치면 같이 고친다.
    """
    if n <= 0:
        return []
    times = _rotate(_SCENERY_TIME, seed, n)
    dists = _rotate(_SCENERY_DISTANCE, f"{seed}·d", n)
    return [f"{t} {d}" for t, d in zip(times, dists)]


def japan_motifs(seed: str, n: int = 3) -> str:
    """그 회차에 쓸 일본 일상 요소 `n` 개. 회차마다 섞인다(`JAPAN_MOTIFS`)."""
    return ", ".join(_rotate(JAPAN_MOTIFS, f"{seed}·m", n))


def person_looks(seed: str, axis: str = "") -> list[str]:
    """인물 5장의 머리·시선. 앞 세 장(여성)은 머리 셋을 하나씩, 뒤 두 장은 머리를 비운다.

    셀카 축(`SELFIE_AXIS`)은 렌즈를 보는 것이 기본이고 딴 곳을 보는 것이 두 장
    (여성 한 장 `gaze_index` · 5번째)이다. 다른 축은 그 반대로, 딴 곳이 기본이고
    카메라를 보는 것이 두 장(여성 한 장 `gaze_index` · 4번째)이다(2026-09-30).
    """
    selfie = axis == SELFIE_AXIS
    away, toward = (_AWAY_SELFIE, _TOWARD_SELFIE) if selfie else (_AWAY, _TOWARD)
    odd, rest = (away, toward) if selfie else (toward, away)
    n = gaze_index(seed)
    looks = [f"Hairstyle: {h}. {odd if i == n else rest}"
             for i, h in enumerate(_HAIRS)] + [toward, away]
    if not selfie:
        return looks
    # 2026-10-02 사람 지시 — 이 축은 컷마다 사람과 각도를 바꾼다(`_DIFFERENT_PERSON` 아래 묶음).
    faces = _rotate(_FACES_W, seed, len(_HAIRS)) + _rotate(_FACES_X, seed, len(looks) - len(_HAIRS))
    angles = _rotate(_SELFIE_ANGLES, seed, len(looks))
    return [f"{look} {_DIFFERENT_PERSON} The person: {face} {angle}"
            for look, face, angle in zip(looks, faces, angles)]

# 일본맛집 음식 컷 중 앞 3장만 한 접시 후기 사진이고, 4·5번은 **모둠 상차림**이다. 그 두 장엔
# `STYLE["food"]` 대신 아래를 붙인다. 원본은 `일본맛집_3-2단계_썸네일이미지.md` 「모둠 상차림」이다
# — 한쪽을 고치면 같이 고친다.
# 2026-09-22 사람 지시로 처음엔 **누끼 스티커 콜라주**였다(「5장 중 2장은 누끼 콜라주」).
# 2026-10-12 사람 지시로 **되돌렸다** — 「콜라주 이미지 왜 점점 더 이상해져?」 → 「바꿔줘」.
# 누끼가 제대로 먹힐수록 크기·원근이 제각각이라 음식이 공중에 뜬 그림이 됐고(갤러리
# 3b2ba86e26ccceee 4·5번), 팀이 좋다고 한 장들(9/22 홋케·베이커리)은 사실 누끼에 실패해
# **한 상 차림**으로 나온 것이었다. 2026-10-06 비교에서도 사람이 꽉 찬 상차림 쪽을 골랐다.
# ⚠ 다시 「오려 붙인 스티커」로 돌리지 마라 — 두 번 확인된 취향이다.
FOOD_REVIEW_SHOTS = 3
FOOD_COLLAGE = (
    "Make it a full-table spread cover for an Instagram restaurant roundup: ONE single real "
    "customer-review photo of one table loaded with many dishes, as if the signature dishes of "
    "several restaurants had all been brought to the same table. Every dish sits in its own real "
    "bowl, plate or tray resting on that table. This is one photograph, not a collage: do not "
    "cut out, paste or float any dish, and never give anything a cut-out edge or a drop shadow. "
    "One shared perspective and one shared light for everything in the frame, so the dishes stay "
    "true in size to each other. Shoot from the seat looking down at about 45 degrees, or "
    "straight down over the table. The hero dish sits large in the front and the other 6 to 8 "
    "dishes fill the space around it, overlapping and crowding the table all the way out to "
    "every edge so the plates at the border are cropped off by the frame — no bare table showing "
    "through, no gap left for a title. Keep the restaurant's real setting: its own table, tray or "
    "wooden counter, its own ceiling lights or warm bulbs, unedited phone-camera color (the "
    "iPhone photo look, no filter or color grading), and only a slightly soft background. The "
    "food must look freshly served and delicious — steam, the glossy sheen of sauce and juices, "
    "a crisp grilled crust, cut surfaces showing what is inside. The table itself stays clean: "
    "no crumpled tissues or napkins, no crumbs or spilled sauce, no half-eaten dishes, empty "
    "plates or leftover glasses, no condiment bottles, menus or flyers. No people and no hands "
    "in the frame. Do not render any text, signage or logos — leave the space clean instead of "
    "generating lettering."
)

# 프롬프트에 「인물(person) 5장」처럼 적으려고 쓴다. 영어 키만 주면 무엇을 그리라는 건지
# 모델이 한 번 더 번역해야 한다.
KIND_KO = {"person": "인물", "scenery": "풍경", "food": "음식"}


async def _scene_context(session_id: str,
                         topic: str) -> tuple[list[str], list[dict[str, Any]], list[Any]]:
    """`(이 회차가 이미 쓴 무대, 이 주제에 지금 붙어 있는 그림, 이 주제의 본문)`.

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
        return [], [], []
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
    # 본문도 같이 돌려준다 — 사진이 그 줄을 보고 장면을 잡는다(`_lines_block`).
    items = cand.get("body")
    if items is None:
        items = ((cand.get("prepared") or {}).get(topic) or {}).get("body") or []
    return ([x for x in out if x], [i for i in mine if isinstance(i, dict)],
            list(items or []))


# 프롬프트에 싣는 「이미 쓴 무대」 — 다 실으면 프롬프트가 터진다. 앞머리(장소)만 본다.
SCENE_KEEP = 40
SCENE_CHARS = 90


def _avoid_block(used: list[str]) -> str:
    if not used:
        return ""
    seen = list(dict.fromkeys(u.split(",")[0].strip()[:SCENE_CHARS] for u in used))[-SCENE_KEEP:]
    # 2026-09-15 사람 신고 — 「주제랑 관련없는 게 생긴다」. 겹침을 막는다고 이미 쓴 장소를 통째로
    # 금지하니 뒤쪽 주제가 대표 장소를 뺏기고 페리 터미널·시청 ATM·신발장으로 밀려났다.
    # 이제 겹침은 **같은 장소 안에서** 자리·각도·순간을 바꿔 피하고, 주제가 먼저다.
    return ("===== 이 회차 다른 주제가 이미 쓴 장면 (구도만 겹치지 않게) =====\n"
            + "\n".join(f"- {x}" for x in seen)
            + "\n⚠ **주제와의 관련이 겹침 피하기보다 먼저다.** 이 주제의 대표 장소가 위에 있어도 그 장소를 "
              "그대로 쓴다. 대신 같은 구도를 베끼지 말고 자리·각도·시간대·순간을 바꾼다. "
              "겹침을 피하려고 주제와 먼 장소로 옮기지 마라.")


# 본문 줄은 열 개까지, 한 줄은 이 길이까지만 싣는다 — 다 실으면 프롬프트가 장면보다 길어진다.
LINES_KEEP = 10
LINES_CHARS = 110


def _lines_block(items: list[Any]) -> str:
    """이 주제의 **본문 줄**을 사진 단계에 함께 싣는다.

    2026-09-23 사람 신고 — 「인물 사진에 주제와 관련없는 사진이 자꾸 생성돼」.
    주제 한 줄(「자신감을 북돋는 일본어 표현」)만으로는 찍을 장면이 안 나와서, 모델이
    게임센터 크레인·가챠처럼 **아무 여행 사진**으로 도망갔다(그 회차 인물 50장 중 15장이
    게임센터 계열이었고, 「자신감」 컷은 인형뽑기 앞에서 웃는 사진이었다).

    본문은 사진보다 **먼저** 지어져 있고(`_do_prepare` 가 body → images 순서로 부른다),
    줄마다 「그 말을 쓰는 상황」이 적혀 있다. 그걸 안 넘기고 있었다.
    """
    def one(it: Any) -> str:
        if not isinstance(it, dict):
            return str(it or "").strip()[:LINES_CHARS]
        # 축마다 줄의 생김새가 다르다 — 상황별일본어는 뜻+상황, 장소 축은 이름.
        head = next((str(it[k]).strip().strip('"') for k in ("meaning", "jp", "name", "title")
                     if str(it.get(k) or "").strip()), "")
        when = str(it.get("situation") or "").strip().splitlines()
        return " — ".join(x for x in (head, when[0] if when else "") if x)[:LINES_CHARS]

    lines = [x for x in (one(i) for i in items[:LINES_KEEP]) if x]
    if not lines:
        return ""
    return ("\n- **아래는 이 캐러셀 본문에 실제로 들어갈 줄이다. 인물 컷은 이 줄들 중 "
            "서로 다른 것을 실제로 쓰는 순간으로 짜라.** 컷마다 어느 줄을 찍은 것인지 정하고, "
            "그 줄의 상황이 사진에 보이게 해라. 본문에 없는 상황을 새로 지어내지 마라.\n"
            # 2026-10-06 사람 신고 — 본문 줄의 자리를 그대로 옮겨 사무실 휴게실·어학원 교실이 나왔다.
            # 본문 상황은 「직장 동료에게」·「처음 맡은 일」처럼 여행 밖 자리를 자주 가리킨다.
            "  ⚠ 줄에 적힌 자리가 **직장·학교·집처럼 여행 중이 아닌 곳**이면, 가져올 것은 "
            "**그 말을 쓰는 순간(누구에게·어떤 마음으로)**이고 **자리는 여행객이 실제로 있는 곳"
            "(카페·가게·역·거리·숙소 앞)으로 옮긴다.** 사무실 휴게실·교실로 짓지 마라.\n"
            + "\n".join(f"  · {x}" for x in lines))


# 인물 컷의 장면을 **본문 줄이 아니라 주제·훅 문구**에서 뽑는 축 (2026-10-06 사람 지시 —
# 「표지 이미지는 본문 내용보다 주제, 훅 문구와 관련 이미지로 생성하도록」).
# 이 단계가 내는 열 장은 모두 **표지(와 CTA) 배경 한 장**을 고르기 위한 것이고 표지에는 훅이
# 올라간다 — 그래서 본문 표현 하나하나의 상황보다 훅이 약속한 장면이 맞아야 한다.
# 원본은 `상황별일본어_3-2단계_썸네일이미지.md` 「장면은 주제와 훅 문구에서 뽑는다」다
# — 한쪽을 고치면 같이 고친다.
HOOK_SCENE_AXES = {"상황별일본어"}
# 미리 만들 때 사진 단계에 실어 주는 훅 후보 수. 열 개를 다 실으면 장면보다 목록이 길어진다.
HOOK_CANDS_KEEP = 6


def _hook_candidates(hooks: dict[str, Any]) -> list[str]:
    """훅 후보를 한 줄짜리 문장으로 펴서 돌려준다(`make_hooks` 는 three·two 로 나눠 준다)."""
    out: list[str] = []
    for group in ("three", "two"):
        for c in (hooks.get(group) or []):
            lines = c.get("lines") if isinstance(c, dict) else None
            text = " ".join(str(x).strip() for x in (lines or []) if str(x).strip())
            if text:
                out.append(text)
    return out


def _hook_scene_block(hook: str, cands: list[str]) -> str:
    """표지 사진의 장면을 **주제와 훅 문구**에서 뽑게 한다 (2026-10-06 사람 지시).

    전에는 본문 줄을 실었다(`_lines_block`). 줄마다 「그 말을 쓰는 상황」이 적혀 있어 장면은
    나왔지만, 적힌 자리를 그대로 옮겨 사무실 휴게실·어학원 교실이 나왔고(2026-10-06 신고)
    표지 한 장이 본문 한 줄짜리 장면이 됐다.
    """
    block = (
        "\n- **이 열 장은 표지(와 CTA) 배경 한 장을 고르기 위한 것이다. 장면은 본문 표현이 "
        "아니라 주제와 훅 문구에서 뽑아라.** 훅을 읽은 사람이 표지에서 보기를 기대할 장면, "
        "주제를 한 장으로 말해 주는 장면으로 짠다. 본문 표현 하나하나의 상황을 찍지 마라.\n"
        "  · 훅에 적힌 **누가·언제·어디서를 그대로 장면으로 옮긴다** — 「혼자 있을 때」면 "
        "혼자 있는 자리, 「식당에서」면 식당.\n"
        "  · 훅에 자리가 없으면 그 주제를 들으면 누구나 먼저 떠올리는 **여행 중의 자리**로 짠다. "
        "주제와 안 이어지는 일반 여행 사진으로 도망가지 마라.\n"
    )
    if not hook.strip() and cands:
        # 밤에 미리 만들 때다 — 훅을 고르기 전이라 후보 전체를 싣는다. 한 후보만 박으면
        # 사람이 다른 것을 골랐을 때 표지 사진이 어긋난다.
        block += (
            "- **아래는 이 주제의 훅 후보다**(아직 고르기 전이다). 한 후보만 따라가지 말고 "
            "후보들이 **공통으로 약속하는 것**을 장면으로 잡아라.\n"
            + "\n".join(f"  · {x}" for x in cands[:HOOK_CANDS_KEEP])
        )
    return block


async def _do_images(chosen: dict[str, Any], axis: str,
                     used: list[str] | None = None,
                     keep: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """사진은 한 장에 1~4분이라 가장 오래 걸린다. 여기서 끝까지 기다렸다가 한 번에 올린다
    — 화면은 그동안 「만드는 중」만 보여주면 된다."""
    from app.services import studio_steps as studio
    from app.services import codex_image, studio_remote

    topic = chosen.get("topic", "")
    hook = " ".join(chosen.get("hook_lines", []))

    # X인용 축은 **원본 게시물 사진을 쓴다**(X인용_3-2단계 2026-09-16 사람 지시 —
    # 「이미지가 있는데 왜 썸네일, CTA 이미지가 또 생성된거야?」). 사진이 없을 때만 아래로 내려가 그린다.
    post_images: list[dict[str, Any]] = []
    if studio.axis_conf(axis).get("x_source"):
        from app.services import x_search

        urls = [u for u in (chosen.get("photo_urls") or []) if u]
        if urls:
            blobs = await x_search.cover_images(urls)
            for blob in blobs:
                url = await studio_remote.upload_image(blob, f"{secrets.token_hex(8)}.png")
                # 그린 것이 아니라 원본이라는 표시 — 화면이 「생성」과 따로 보여준다.
                post_images.append({"kind": "post", "prompt": "원본 게시물 사진", "url": url})
            if not post_images:
                logger.warning("[studio-worker] 원본 사진을 한 장도 못 받았습니다.")
        # ⚠ 원문 사진이 있어도 **생성분을 건너뛰지 않는다** (2026-09-18 피드백 1번 —
        #   「생성 사진 5장 + 원문 사진 중 택 1 가능하도록」). 전에는 원문이 있으면
        #   그것만 돌려줘서 고를 것이 하나뿐이었다. 아래로 내려가 그리고, 끝에 합친다.

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
            # 사진도 축 주인 계정으로 올린다 — 캐러셀과 같은 계정에 모여야 나중에 찾기 쉽다.
            url = await studio_remote.upload_image(blob, f"{secrets.token_hex(8)}.png")
            images.append({"kind": "map", "prompt": where, "url": url})
        return {"images": images}

    shots = axis_conf_shots(studio, axis)
    # 「인물만 다시」·「풍경만 다시」 — 고른 쪽만 그리고 나머지(`keep`)는 그대로 둔다.
    # 열 장을 다 다시 그리면 6분이 걸려서, 한쪽만 마음에 안 들 때 나머지까지 버리게 된다.
    kind = str(chosen.get("image_kind") or "").strip()
    if kind:
        shots = {k: (v if k == kind else 0) for k, v in shots.items()}
    else:
        # 버튼으로만 그리는 종류는 기본 묶음에서 뺀다(`AXES[축].cover_on_demand` — 일본맛집 인물).
        on_demand = studio.axis_conf(axis).get("cover_on_demand") or []
        shots = {k: (0 if k in on_demand else v) for k, v in shots.items()}
    # 그릴 종류만 남긴다 — 축마다 다르다(상황별일본어 인물·풍경 / 일본맛집 인물·음식).
    kinds = [k for k, v in shots.items() if v]
    want = " · ".join(f"{KIND_KO.get(k, k)}({k}) {shots[k]}장" for k in kinds)
    # 생김새·각도·시선 자리를 돌리는 씨앗. 셀카 축은 **누를 때마다 새로** 만든다
    # (2026-10-02 사람 지시 — 「뽑을 때마다 사람, 각도 바뀌도록」. 주제로만 돌리면 같은
    # 주제로 다시 눌렀을 때 다섯 명이 그대로 다시 나왔다). 다른 축은 주제 그대로다 —
    # 그쪽은 생김새를 붙이지 않아 바꿀 것이 시선 자리뿐이다.
    # ⚠ 아래 `gaze_task`(장면을 짓는 쪽)와 `person_looks`(결을 붙이는 쪽)가 **같은 씨앗**을
    #   써야 몇 번째 컷이 렌즈를 보는지 둘의 말이 맞는다.
    look_seed = (f"{topic}·{secrets.token_hex(4)}"
                 if (axis or studio.DEFAULT_AXIS) == SELFIE_AXIS else topic)
    # 인물 컷의 시선 규칙 — 셀카 축과 그 밖의 축이 서로 뒤집혀 있다(`person_looks`).
    gaze_task = (
        # 2026-10-02 사람 신고 — 「각도가 다 비슷해」. 여기서 「얼굴과 상반신이 크게 잡히고」로
        # 크롭까지 못박아, 컷마다 다른 구도를 붙여도(`_SELFIE_ANGLES`) 다섯 장이 같은 틀이 됐다.
        "- **인물 컷은 본인이 폰을 들고 찍은 셀카다.** 팔을 뻗어 든 폰으로 찍은 장면으로 짜고, "
        "남이 찍어 준 전신 스냅으로 짜지 마라. **얼마나 크게 잡히는지(크롭)는 적지 마라 — "
        "화면이 컷마다 다르게 붙인다.**\n"
        "- **머리 모양과 시선은 네가 적지 마라 — 화면이 인물 컷마다 순서대로 붙인다.** "
        f"1번 단발·2번 묶은 머리·3번 긴 머리이고, **{gaze_index(look_seed) + 1}번과 5번은 렌즈에서 눈을 떼고 "
        "옆을 보는 컷**이다. 그 두 장은 셀카를 찍다 옆의 풍경·가게·음식 쪽으로 고개를 돌릴 만한 장면으로 "
        "짜고, 나머지는 렌즈를 보는 셀카로 짠다.\n"
        # 2026-10-02 사람 신고 — 「왜 자꾸 같은 사람이 나와」. 생김새·옷·각도를 아무도 적지 않아
        # 다섯 장이 같은 얼굴·같은 구도로 나왔다. 컷마다 다른 것을 붙이는 쪽은 화면(`person_looks`)이다.
        "- **생김새·옷·카메라 각도도 네가 적지 마라 — 화면이 컷마다 다른 것을 붙인다.** "
        "다섯 장은 **서로 다른 사람**이다. 너는 그 사람이 어디서 무엇을 하는 순간인지만 쓰고, "
        "얼굴·머리·옷·체형·카메라 위치는 비워 둔다.\n"
    ) if (axis or studio.DEFAULT_AXIS) == SELFIE_AXIS else (
        "- **머리 모양과 시선은 네가 적지 마라 — 화면이 인물 컷마다 순서대로 붙인다.** "
        f"1번 단발·2번 묶은 머리·3번 긴 머리이고, **{gaze_index(look_seed) + 1}번과 4번만 카메라를 보는 "
        "컷**이다. 그 두 장은 친구가 불러 돌아볼 만한 장면으로 짜고, 나머지는 옆의 풍경·가게·음식을 "
        "보는 컷으로 짠다.\n"
    )
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
        # 2026-09-17 사람 지시 — 「인물 5장이 모두 20대 한국인 여자인데, 그중 2장은 20대 한국인
        # 남자 또는 주제와 어울리는 인물로」.
        "- **단, 인물 컷 중 마지막 2장은 여성이 아니다** — 20대 한국인 남성"
        "(a Korean man in his twenties)이나, 주제에 더 어울리는 다른 인물로 쓴다. "
        "나머지는 위 기본(20대 한국인 여성) 그대로다.\n"
        # 2026-09-22 사람 지시 — 머리·시선이 다섯 장 다 같았다. 붙이는 것은 화면(`person_looks`)이고,
        # 여기서는 카메라 쪽 컷이 그럴 만한 장면이 되게만 알린다.
        # 2026-09-23 사람 지시 — 도는 자리는 회차마다 바뀐다(`gaze_index`).
        #   그래서 번호를 박지 않고 그 회차의 자리를 적어 넣는다.
        # 2026-09-29 사람 지시 — 인물은 셀카다. 렌즈를 보는 것이 기본이 되고, 딴 곳 보는 장이 두 장이다.
        # 2026-09-30 사람 지시 — 셀카는 `SELFIE_AXIS` 한 축만이다. 다른 축은 스냅으로 되돌렸다.
        f"{gaze_task}"
        # 2026-09-17 사람 지시 — 「인물 사진이면 뒤에 나오는 사람은 최대한 안 나오도록」.
        "- **인물 컷에는 주인공 말고 다른 사람을 최대한 넣지 마라.** 점원·친구가 꼭 필요하면 "
        "손·어깨·뒷모습처럼 얼굴이 안 보이는 일부만 쓴다. crowded·bustling·busy 처럼 "
        "사람이 붐비는 말을 쓰지 마라.\n"
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
        "**말이 오가는 자리**(점원 앞·역무원 앞·호텔 프런트·카페·게임센터)를 고른다. "
        "도서관·헌책방·버스 창가처럼 혼자 조용히 있는 자리는 주제가 정말 혼잣말일 때만 쓴다. "
        # 2026-09-22 사람 지시 — 「이자카야, 가라오케 주제로는 인물 이미지 생성하지 않도록」.
        # 위 예시 첫머리에 이자카야가 있어 상황별일본어 한 회차 인물 52장 중 5장이 이자카야였다.
        "**인물 컷의 장소로 이자카야·술집·바·가라오케를 쓰지 마라** — 주제가 이자카야·술이어도 "
        "가게 안 술자리 대신 가게 밖 골목·거리에서 짓는다. 프롬프트에 izakaya·bar·pub·karaoke 를 쓰지 마라. "
        f"풍경 컷은 그 말을 쓰는 장소를 {SCENERY_PEOPLE.get(axis or studio.DEFAULT_AXIS, '사람 없이')} 찍은 것이다 — "
        f"{SCENERY_PLACE.get(axis or studio.DEFAULT_AXIS, '')}"
        "상관없는 명소·자연 풍경으로 빠지지 마라. "
        "각 컷마다 **왜 이 사진인지 주제와 한 줄로 이어지는지** 스스로 확인하고 안 이어지면 다시 짜라.\n"
        # 2026-09-15 사람 신고 — 「주제랑 관련없는 게 생긴다」. 실제로 「현금인출기 앞」이 페리 터미널·
        # 고속도로 휴게소·시청 별관 ATM 으로, 「동의할 때」가 꽃집·스티커 사진 부스로 나왔다.
        # 2026-09-23 사람 지시 — 「인물 사진에 자꾸 폰 화면·계산대·컴퓨터 화면이 나온다」.
        # 위 「말이 오가는 자리(점원 앞…)」 줄과 본문 줄 따라 짓기가 겹쳐 계산대·발권기·폰 화면이
        # 반복됐다(실측: 한 회차 인물 컷이 편의점 계산대·역 발권기·프런트 폰 확인으로 채워졌다).
        "- **화면을 주인공으로 쓰지 마라** — 폰 화면·계산대(금전등록기)·모니터·PC 화면이 "
        "컷의 중심이 되거나 화면 속 내용이 보이게 짓지 마라. 본문 줄이 채팅·예약 확인처럼 "
        "화면을 보는 상황이어도, 사람의 표정과 그 자리가 보이는 장면으로 옮겨 짠다.\n"
        "- **장소는 그 주제를 들으면 누구나 먼저 떠올리는 곳, 한국 여행객이 실제로 가는 곳**으로 한다 "
        "(ATM 이면 편의점·역 ATM, 막차면 역 개찰구·택시 승강장). 페리 터미널·고속도로 휴게소·관공서·"
        "공방처럼 여행객이 잘 안 가는 곳으로 옮기지 마라. "
        # 2026-10-06 사람 신고 — 「주제와 관련 없는 이미지가 자꾸 나온다」. 실측: 「가족 호칭」
        # 10장 중 4장이 **일본 사무실 휴게실**, 「자신감을 북돋는 표현」은 10장 중 7장이
        # **어학원 교실·면접실**이었다. 본문 줄의 상황(「직장 동료에게」·「처음 맡은 일」)을
        # 자리까지 그대로 옮긴 탓이다(`_lines_block`).
        "**사무실·회사 휴게실·교실·어학원·면접장·병원·집 안처럼 여행 중에 있을 수 없는 자리도 "
        "쓰지 마라** — 이 캐러셀을 보는 사람은 일본을 여행하는 사람이다. "
        "다섯 장이 모두 다른 장소일 필요는 없다 — 대표 장소 한두 곳에서 순간·각도를 바꿔도 된다."
    )
    # 2026-10-12 사람 신고 — 「풍경 이미지가 거의 다 비슷해보여」. 위 「다섯 장이 모두 다른
    # 장소일 필요는 없다」(2026-09-15 · 인물 컷 이야기)가 풍경에도 걸려 다섯 장이 같은 골목으로
    # 모였다. 풍경은 반대로 **자리를 나누게** 하고, 시간대·거리감·일본 요소는 화면이 붙인다
    # (`scenery_looks` · `japan_motifs`).
    if "scenery" in kinds:
        task += (
            "\n- **풍경 5장은 서로 다른 자리로 짜라.** 같은 골목·같은 역을 각도만 바꿔 "
            "다섯 번 내지 마라(위 「다섯 장이 모두 다른 장소일 필요는 없다」는 인물 컷 "
            "이야기다). 다섯 장 모두 주제·훅과 이어지는 자리여야 하는 것은 그대로다.\n"
            "- **풍경 컷의 시간대·빛·거리감은 네가 적지 마라 — 화면이 컷마다 순서대로 "
            "붙인다.** 아침·낮·해 질 참, 멀리서·눈높이·올려다본 구도 같은 것을 쓰지 말고 "
            "**그 자리와 무엇이 보이는지만** 쓴다. 담을 일본 일상 요소도 화면이 회차마다 "
            "바꿔 붙이니 골목·자판기·건널목으로 못박지 마라."
        )
    # 음식 컷은 이 축에만 있다(일본맛집). 안 적으면 「음식 든 사람」이 나와 인물 컷과 겹친다.
    if "food" in kinds:
        task += (
            "\n- **음식 컷에는 사람이 나오지 않는다.** 그 주제의 지역·메뉴에 실제로 있는 음식을 "
            "손님이 자리에 앉아 폰으로 찍은 **후기 사진** 장면으로 잡는다 — 그 가게 테이블·쟁반·"
            "젓가락·물컵이 함께 보이게. 가게 간판·메뉴판 글자를 그리지 마라. "
            f"앞 {FOOD_REVIEW_SHOTS}장은 같은 접시 클로즈업으로 채우지 말고 위에서 본 상차림·45° 대표 메뉴·"
            "가른 단면·곁들이까지 담은 자리처럼 시점을 나눈다."
            # 2026-10-12 사람 지시 — 누끼 스티커를 버리고 **모둠 상차림**으로. 모양은 화면이 붙인다(`FOOD_COLLAGE`).
            f"\n- **음식 컷 중 {FOOD_REVIEW_SHOTS + 1}번째부터는 모둠 상차림이다.** 앞에 크게 놓을 대표 메뉴 "
            "한 가지와, 같은 상에 함께 깔 **그 주제의 다른 메뉴 6~8가지**를 이름으로 적는다. "
            "여러 가게를 돌며 먹은 것을 한 상에 모은 것처럼 메뉴가 겹치지 않게 하고, 두 장은 대표 메뉴와 "
            "곁들이 구성을 서로 다르게 한다. 오려 붙이기·배치·그림자 같은 모양은 적지 마라 — 화면이 붙인다."
            # 2026-10-08 사람 지시 — 「주제가 삿포로 풍경 예쁜 카페라면 디저트를 메인으로 하고
            # 뒤에 삿포로 풍경이 보이는 창가 자리 사진으로」. 메뉴만 맞추고 주제의 조건(풍경·창가)을
            # 버리면 아무 주제에나 쓸 수 있는 음식 컷이 된다. 지침서에도 있지만 codex 가 흘린다.
            "\n- **주제에 자리 조건(풍경·창가·야경·노포·골목·루프탑 같은 것)이 들어 있으면 그 조건이 "
            "배경에 보이게 짜라.** 주인공은 여전히 그 주제의 메뉴이고, 조건은 창밖·뒤쪽 자리로 보여준다 "
            "— 「삿포로 풍경 예쁜 카페」면 디저트·커피가 상 앞에 크고 창밖으로 삿포로 거리가 보이는 "
            "창가 자리다. 모둠 상차림 장도 그 상이 놓인 자리가 그 조건을 들고 있게 한다. "
            "지역·메뉴만 있는 주제면 조건을 억지로 만들지 마라."
            # 2026-10-15 사람 지시 — 「좀 더 먹음직스러운 음식으로. 특히 디저트 주제라면 흔한
            # 디저트 말고 누구나 먹어보고 싶은 디저트로」. 결(`STYLE["food"]`)로는 안 되는
            # 일이다 — **무슨 메뉴를 적느냐**가 여기서 갈린다.
            "\n- **메뉴는 그 주제에서 제일 그림이 되는 간판 메뉴로 적는다.** 어느 가게에나 있는 "
            "평범한 것보다 속이 터질 듯한 것·크기가 눈에 띄는 것·그 지역 재료가 보이는 것 쪽이다."
            "\n- **디저트·카페 주제면 흔한 디저트를 적지 마라.** 조각 케이크 한 접시·평범한 "
            "티라미수·치즈케이크·컵 소프트아이스크림·마카롱·커피+쿠키는 쓰지 않는다. 층이 보이는 "
            "유리잔 파르페, 가르면 속이 흐르는 수플레·푸딩·폰당, 과일이 수북한 타르트·후르츠산도, "
            "브륄레, 크림·소스가 흘러내리는 것, 한 손에 안 들어오는 크기, 그 지역 재료(말차·호지차·"
            "홋카이도 우유·멜론·밤·딸기)가 눈에 보이는 것처럼 **누구나 먹어보고 싶은 간판 디저트**를 "
            "이름으로 적는다."
        )
    # 인물 컷의 장면을 어디서 뽑나 — 축마다 다르다. 상황별일본어는 **주제·훅 문구**
    # (`_hook_scene_block`, 2026-10-06), 그 밖의 축은 **본문 줄**(`_lines_block`)이다.
    if "person" in kinds:
        if (axis or studio.DEFAULT_AXIS) in HOOK_SCENE_AXES:
            task += _hook_scene_block(
                hook, [x for x in (chosen.get("hook_candidates") or []) if x])
        else:
            task += _lines_block(list(chosen.get("items") or []))
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
        # 모델이 장면을 한 줄도 안 냈다는 뜻이다. 무엇을 받았는지 남겨야 다음에 볼 수 있다.
        logger.warning("[studio-worker] 이미지 프롬프트 0건 — 받은 것: %s", str(plan)[:400])
        raise RuntimeError(
            f"그릴 장면을 한 줄도 받지 못했습니다(요청한 묶음: {', '.join(kinds) or '없음'}). "
            "다시 눌러 주세요."
        )

    # 결을 여기서 붙인다(`STYLE`). 모델이 쓴 것은 장면뿐이다. 인물은 컷마다 머리·시선도(`person_looks`).
    style = {**STYLE, **AXIS_STYLE.get(axis or studio.DEFAULT_AXIS, {})}
    looks = person_looks(look_seed, axis or studio.DEFAULT_AXIS)
    # 풍경은 **누를 때마다** 시간대·요소가 바뀌어야 한다(2026-10-12) — 주제로만 돌리면
    # 「풍경만 다시」를 눌러도 같은 아침 햇살·같은 요소가 다시 나온다.
    scenery_seed = f"{topic}·{secrets.token_hex(4)}"
    scenery = scenery_looks(scenery_seed, shots.get("scenery", 0))
    motifs = japan_motifs(scenery_seed)
    texts = []
    nth: dict[str, int] = {}
    for kind, p in prompts:
        n = nth[kind] = nth.get(kind, -1) + 1
        look = looks[n] if kind == "person" and n < len(looks) else ""
        if kind == "scenery" and n < len(scenery):
            look = scenery[n]
        kind_style = FOOD_COLLAGE if kind == "food" and n >= FOOD_REVIEW_SHOTS else style.get(kind, "")
        # 결에 비워 둔 일본 요소 자리를 그 회차 것으로 채운다(`JAPAN_MOTIFS`).
        kind_style = kind_style.replace("{motifs}", motifs)
        texts.append("\n\n".join(x for x in (p, look, kind_style) if x))
    # 가로로 그리는 축이 있다(`AXES[축].cover_size` — 일본맛집2). 없으면 codex 기본값(세로)이다.
    size = studio.axis_conf(axis or studio.DEFAULT_AXIS).get("cover_size")
    blobs = await codex_image.generate_images(texts, **({"size": size} if size else {}))
    images = []
    drawn = 0          # codex 가 실제로 그려 준 장수
    upload_failed = 0  # 그림은 왔는데 서버에 못 올린 장수
    for (kind, prompt), blob in zip(prompts, blobs):
        if not blob:
            continue
        drawn += 1
        try:
            # 사진은 **화면이 있는 서버**에 올려야 보인다. 계정은 축 주인 것으로.
            url = await studio_remote.upload_image(blob, f"{secrets.token_hex(8)}.png")
        except Exception as e:
            # 한 장 못 올렸다고 나머지를 버리지 않는다. 몇 장이 왜 빠졌는지만 남긴다.
            upload_failed += 1
            logger.warning("[studio-worker] 사진 업로드 실패(%s): %s", kind, str(e)[:200])
            continue
        images.append({"kind": kind, "prompt": prompt, "url": url})

    if not images and not post_images:
        # ⚠ 예전엔 이유가 뭐든 「한 장도 만들지 못했습니다」 하나였다
        #   (2026-09-18 피드백 3번). 셋은 고치는 방법이 전혀 다르다.
        logger.warning(
            "[studio-worker] 사진 0장 — 요청 %d장 · codex 가 준 것 %d장 · 업로드 실패 %d장",
            len(prompts), drawn, upload_failed)
        if drawn == 0:
            detail = (f"codex 가 {len(prompts)}장을 한 장도 그리지 못했습니다. "
                      "이 PC 의 codex 가 켜져 있는지 확인하고 다시 눌러 주세요.")
        elif upload_failed:
            detail = (f"{drawn}장을 그렸지만 서버에 올리지 못했습니다"
                      f"(실패 {upload_failed}장). 잠시 뒤 다시 눌러 주세요.")
        else:
            detail = "사진을 만들지 못했습니다. 다시 눌러 주세요."
        raise RuntimeError(detail)

    if upload_failed:
        logger.warning("[studio-worker] %d장은 올리지 못해 빠졌습니다(나머지 %d장은 정상).",
                       upload_failed, len(images))
    # 한쪽만 다시 그렸으면 다른 쪽을 앞에 붙여 되돌려준다 — 안 붙이면 화면에서 사라진다.
    # 원문 사진은 **맨 앞**에 둔다. 고를 때 먼저 보이는 편이 낫다(피드백 1번).
    return {"images": post_images + (keep or []) + images}


async def _do_body_x(chosen: dict[str, Any], axis: str) -> dict[str, Any]:
    """X인용 본문 — 문구는 codex(지침서 규칙), 이미지 칸은 **X 화면 캡처**.

    `X인용_3-3단계_본문.md` 가 정한 것:
      · 장수는 사진 수가 아니라 **이야기**가 정한다. 같은 말을 하는 사진은 한 장만.
      · 이미지 칸은 그린 카드가 아니라 **X 화면 그대로**(계정 줄은 블러).
      · 원문이 일본어면 그 글만 한국어로 갈아 끼운다.
    """
    from app.services import studio_steps as studio
    from app.services import studio_remote, x_search

    post_id = str(chosen.get("post_id") or "")
    if not post_id:
        raise RuntimeError("게시물 id 가 없습니다 — 1단계 후보를 다시 고르세요.")

    # 1) 문구 — 지침서를 실어 codex 에게 맡긴다(형식만 여기서 정한다).
    r = await studio.make_body(studio.BodyBody(
        axis=axis,
        topic=chosen.get("topic", ""),
        hook=" ".join(chosen.get("hook_lines", [])),
    ))
    items = list(r.get("items") or [])

    # 2) 이미지 — 게시물 카드를 한 장 찍어 **첫 장**에 붙인다.
    #    ⚠ 캡처 안 글자를 **한국어로 갈아 끼운다**(X인용_3-3단계 「원문을 그대로 한국어로」).
    #    전에는 이 번역을 아무도 만들어 주지 않아 **일본어 그대로 찍혔다**
    #    (2026-09-18 피드백 4번 · 캐러셀 556 에서 확인).
    korean = str(chosen.get("body_korean") or "")
    if not korean:
        korean = await studio.translate_post(str(chosen.get("text") or ""), axis)
    shot = await x_search.capture_card(post_id, korean)
    url = await studio_remote.upload_image(shot, f"{secrets.token_hex(8)}.png")
    if items:
        items[0] = {**items[0], "photo": url}
    else:
        items = [{"text": "", "photo": url}]

    # 3) 「일본 반응」 장 — 답글 **1개 = 1장**으로 2~3장을 맨 뒤에 붙인다(3-3 지침서 2026-10-13).
    #    2026-09-21~10-12 은 답글 3개를 손으로 그려 **한 장**에 몰았다. 사람 지시로 폐기 —
    #    「지금 캡처하는 건 1장밖에 없어 … 그것보다 더 선택지가 많아야 해」.
    #
    #    답글은 **이 자리에서 받는다**(2026-09-23 사람 지시 ①). 1단계에서 후보마다 찾게
    #    했더니 그 무게로 grok 이 제한 시간 안에 결론을 못 냈다.
    #    ⚠ 1단계가 grok 으로 받아 둔 답글(`reply_quotes`)에는 **id 가 없다** — 캡처를 못
    #      띄우므로 그건 버리고 FxTwitter 로 다시 받는다.
    quotes = [q for q in (chosen.get("reply_quotes") or []) if (q or {}).get("id")]
    if not quotes:
        quotes = await x_search.fetch_replies(str(chosen.get("url") or ""), post_id)
    if x_search.replies_ready(quotes):
        try:
            slides = await _reply_slides(quotes, chosen, axis)
        except Exception as e:
            # 반응 장은 **있으면 좋은 것**이다. 여기서 죽으면 본문 전체가 날아간다.
            logger.warning(f"[studio-worker] 일본 반응 장을 만들지 못했습니다: {str(e)[:200]}")
            slides = []
        if slides:
            # 본문은 **5장 안쪽** — 반응을 3장 쓰면 글·사진 장은 2장까지다(3-3 「장수」).
            # 겹치는 사진 장을 사람이 고르는 자리가 아니므로 **뒤에서부터** 뺀다.
            #   첫 장은 원문 캡처라 반드시 남긴다.
            keep = max(1, x_search.BODY_SLIDES_MAX - len(slides))
            if len(items) > keep:
                logger.info(f"[studio-worker] 반응 {len(slides)}장 — 글·사진 장을 {len(items)}→{keep}장으로 줄입니다")
            items = items[:keep] + slides
    else:
        logger.info(f"[studio-worker] 찍을 수 있는 답글이 {len(quotes)}개 — 일본 반응 장은 건너뜁니다")
    return {"body": items}


async def _reply_slides(quotes: list[dict[str, Any]], chosen: dict[str, Any],
                        axis: str) -> list[dict[str, Any]]:
    """답글을 **1개 = 1장**으로 찍어 반응 장을 2~3장 만든다 (3-3 지침서 2026-10-13).

    `quotes` 는 수치로 줄이 서 있고(`x_search._rank_replies` — 좋아요 바닥 5 →
    좋아요÷조회수), 그중 **쓸 것만** 모델이 고른다(`studio.pick_replies` — 못 알아들을 것·
    결 겹침·글이 안 되는 것·공격·혐오). 고른 것만 번역·캡처해 **3장까지** 채운다.

    답글 글이 일본어로만 와 있으면 **먼저 한국어로 옮긴다**(3-3 「번역 — 우리가 옮긴다」).
    캡처에는 한국어만 들어간다 — 읽을 사람은 한국인이다.
    한 장이 실패해도 나머지는 살린다. 한 장도 못 찍으면 그때 올려 보낸다.
    """
    from app.services import studio_steps as studio
    from app.services import studio_remote, x_search

    # 수치만으로는 「한국 비하」·「일본 내부 밈」·「한 글자」가 그대로 1순위로 올라온다
    # (2026-10-13 실측 — 원글 4건에서 상위 3개 중 4장이 못 쓸 것이었다). 거기서 한 번 거른다.
    picked = await studio.pick_replies(
        chosen.get("topic", ""), quotes, x_search.REPLY_SLIDES_MAX, axis)
    if not picked:
        logger.info("[studio-worker] 쓸 만한 답글이 없어 일본 반응 장은 건너뜁니다")
        return []

    out: list[dict[str, Any]] = []
    for q in picked:
        korean = str((q or {}).get("korean") or "").strip()
        if not korean:
            korean = await studio.translate_post(str((q or {}).get("text") or ""), axis)
        if not korean:
            continue
        try:
            shot = await x_search.capture_reply({**q, "korean": korean})
        except Exception as e:
            logger.warning(f"[studio-worker] 답글 캡처 실패({(q or {}).get('id')}): {str(e)[:200]}")
            continue
        url = await studio_remote.upload_image(shot, f"{secrets.token_hex(8)}.png")
        # 문구는 **그 답글 한 개**를 여는 한 줄이다 — 장마다 따로 짓는다.
        text = await studio.make_reply_line(chosen.get("topic", ""), [{"korean": korean}], axis)
        out.append({"text": text, "photo": url})
    if not out:
        raise RuntimeError("답글 캡처를 한 장도 만들지 못했습니다.")
    return out


async def _do_body(chosen: dict[str, Any], axis: str) -> dict[str, Any]:
    from app.services import studio_steps as studio

    # X인용 축은 본문 이미지가 **그림이 아니라 X 화면 캡처**다(X인용_3-3단계).
    # 문구는 다른 축과 같이 codex 가 짓고, 그 아래 칸에 캡처를 붙인다.
    if studio.axis_conf(axis).get("x_source"):
        return await _do_body_x(chosen, axis)

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
        # 표지가 네 칸인 축(일본맛집2) — 고른 표지 후보가 함께 들고 온 소개 3줄·해시태그.
        cover_intro=chosen.get("cover_intro") or [],
        cover_tags=str(chosen.get("cover_tags") or ""),
        # 이력의 URL 칸 — 이게 비면 다음 회차가 같은 게시물을 또 고른다(X인용).
        source_url=str(chosen.get("url") or ""),
    ))
    return {"__result__": r}


# 링크 한 건으로 만들 때 본문에 쓸 원문 사진 수 상한. 본문은 5장 안쪽이라(3-3 지침서)
# 그보다 많이 받아도 쓸 자리가 없다.
LINK_PHOTO_LIMIT = 4


async def _do_link(chosen: dict[str, Any], axis: str) -> dict[str, Any]:
    """**링크 하나로 캐러셀까지** 만든다 (2026-10-13 트립앤라이프 지시).

    X·인스타·한국 커뮤니티(루리웹·디시) 주소를 받아 `link_ingest` 로 글·사진을 뽑고,
    그 뒤는 이 축의 평소 단계를 그대로 쓴다 — 훅 → 본문 문구 → 캡션 → 캐러셀 생성.
    사람이 고를 자리를 건너뛰고 **첫 안(A)** 으로 만든다. 마음에 안 들면 화면에서
    그 단계만 다시 뽑으면 된다.

    ⚠ 본문 사진은 **이 PC 가 받아 서버로 올린다** — 루리웹 이미지 호스트가 서버(AWS)에서
      응답하지 않고, 디시는 레퍼러를 요구한다(`link_ingest.download_photos`).
    ⚠ X 링크라도 `_do_body_x`(캡처+답글)를 타지 않는다. 트립초초처럼 **원문 사진·글만**
      쓰는 길이다(2026-10-13 사람 승인).
    """
    from app.services import link_ingest, studio_remote, x_search
    from app.services import studio_steps as studio

    url = str(chosen.get("link_url") or "").strip()
    if not url:
        raise RuntimeError("링크가 없습니다 — link_url 을 넣어 주세요.")

    rec = await link_ingest.fetch(url)
    topic = str(rec.get("topic") or "").strip()
    # X·인스타는 제목 자리에 **원문 첫 줄**이 들어온다 — 일본어 글이면 그대로 일본어다
    # (2026-10-13 시험에서 캐러셀 이름이 「初！マムズタッチ…」가 됐다). 1단계가 쓰는
    # 제목 채우기를 그대로 빌려 한국어 한 줄로 만든다. 커뮤니티 글은 페이지 제목이 곧 제목이다.
    if rec.get("source") != link_ingest.SOURCE_WEB and rec.get("text"):
        filled = await studio._fill_titles([{**rec, "topic": ""}], axis)
        topic = str((filled[0] if filled else {}).get("topic") or "").strip() or topic
    if not topic:
        raise RuntimeError("링크에서 제목을 찾지 못했습니다 — 주소를 확인해 주세요.")
    logger.info(f"[studio-worker] 링크({rec.get('source')}) — 「{topic[:40]}」 사진 {rec.get('photos')}장")

    # 1) 사진 — 원문 것을 받아 서버로 옮긴다. 표지는 4:5 로 잘라 따로 올린다.
    blobs = await link_ingest.download_photos(list(rec.get("photo_urls") or []), LINK_PHOTO_LIMIT)
    body_photos: list[str] = []
    for blob in blobs:
        body_photos.append(await studio_remote.upload_image(blob, f"{secrets.token_hex(8)}.jpg"))
    cover_url = ""
    if blobs:
        # 표지 자르기는 X인용이 쓰던 것을 그대로 쓴다 — 비율·여백 규칙이 같다.
        cover = await asyncio.to_thread(x_search._crop_cover, blobs[0])
        cover_url = await studio_remote.upload_image(cover, f"{secrets.token_hex(8)}.png")

    # 2) 훅 — 원문을 함께 넘긴다(그래야 훅이 글 내용을 짚는다).
    hooks = await studio.make_hooks(studio.TopicBody(
        axis=axis, topic=topic, source=_hook_source(rec)))
    first = next((c for group in ("two", "three") for c in (hooks.get(group) or [])
                  if (c or {}).get("lines")), None)
    hook_lines = [str(x).strip() for x in ((first or {}).get("lines") or []) if str(x).strip()]
    if not hook_lines:
        raise RuntimeError("훅 문구를 받지 못했습니다 — 잠시 뒤 다시 눌러 주세요.")

    # 3) 본문 문구 — 지침서대로 codex 가 짓고, 장마다 원문 사진을 앞에서부터 붙인다.
    got = await studio.make_body(studio.BodyBody(
        axis=axis, topic=topic, hook=" ".join(hook_lines)))
    items: list[dict[str, Any]] = []
    for i, item in enumerate(list(got.get("items") or [])):
        items.append({**item, "photo": body_photos[i]} if i < len(body_photos) else dict(item))
    # 사진이 글보다 많으면 남은 사진만으로 장을 더 붙인다 — 원문 사진을 버리지 않는다.
    for extra in body_photos[len(items):]:
        items.append({"text": "", "photo": extra})

    # 4) 캡션
    caption = await studio.make_caption(studio.CaptionBody(
        axis=axis, topic=topic, hook=" ".join(hook_lines), items=items))

    # 5) 화면이 같은 것을 보게 올려 두고(사람이 단계별로 다시 뽑을 수 있다) 캐러셀을 만든다.
    picked = {
        "topic": topic,
        "hook_lines": hook_lines,
        "image_url": cover_url or (body_photos[0] if body_photos else ""),
        "items": items,
        "caption": caption.get("caption") or "",
        **{k: rec[k] for k in ("url", "text", "account", "author", "post_id", "source")
           if rec.get(k) not in (None, "", [])},
    }
    return {"__chosen__": picked, **await _do_build({**chosen, **picked}, axis)}


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


# 한 번에 **겹쳐서** 만들 주제 수. 이미지가 프로세스 전체에서 동시 24 로 묶여 있는데
# (codex_image.MAX_CONCURRENT) 한 주제는 10장뿐이라, 순차로 돌리면 14칸이 놀았다.
# 5개를 겹치면 50장이 밀려들어 24칸이 계속 찬다 — 2026-09-23 사람 지시.
# ⚠ 올리려면 codex 동시 장수와 같이 본다. 주제만 늘리면 이미지 대기줄만 길어진다.
PREPARE_BATCH = 5


async def _prepare_one(t: dict[str, Any], axis: str, need_places: int,
                       used_scenes: list[str]) -> tuple[str, dict[str, Any] | None, str, str]:
    """주제 하나를 통째로 만든다 — 훅·본문·사진·캡션.

    `(이름, 만든 것, 상태, 설명)` 을 돌려준다. 상태는 셋이다:
      ok     — 다 만들었다
      unfit  — **주제 탓**이라 다음에도 같은 결과다(제외 목록으로 보낸다)
      fail   — 일시적 실패(codex 오류 등). 제외하지 않는다.

    묶음으로 겹쳐 돌리므로 **여기서 예외를 밖으로 내보내지 않는다** — 하나가 터지면
    `asyncio.gather` 가 같은 묶음의 나머지까지 취소해 버린다.
    """
    from app.services import studio_steps as studio

    name = str(t.get("topic") or "").strip()
    try:
        # 지도 축은 주제가 곧 「어느 가이드의 어느 버튼」이다. 그 둘을 아래 단계로
        # 넘겨야 장소·지도·수량이 같은 버튼을 가리킨다.
        where = {k: t[k] for k in ("guide_id", "button", "region") if t.get(k)}
        # X인용은 주제가 곧 X 게시물이다. 게시물 정보를 아래 단계로 **함께 넘겨야**
        # 표지가 원본 사진을 쓰고 본문에 캡처가 붙는다(2026-09-18).
        carry = {k: t[k] for k in X_CARRY if t.get(k) not in (None, "", [])}
        lower = {"topic": name, "hook_lines": [], **where, **carry}

        hooks = await studio.make_hooks(studio.TopicBody(axis=axis, topic=name, source=_hook_source(t)))
        # ⚠ `studio.make_body` 를 바로 부르면 **축 분기를 건너뛴다** — X인용은
        #   `_do_body_x`(캡처 + 번역)를 타야 한다. 단계 함수를 그대로 쓴다.
        got = await _do_body(lower, axis)
        items = list(got.get("body") or [])
        # 자리를 못 채웠으면 여기서 접는다 — 사진까지 짓고 버리면 그만큼 헛돈다.
        if need_places and len(items) < need_places:
            return name, None, "unfit", f"{need_places}곳 중 {len(items)}곳뿐"

        # 본문을 함께 넘긴다 — 인물 컷이 그 줄을 쓰는 순간이어야 한다(`_lines_block`).
        # 훅으로 장면을 잡는 축(`HOOK_SCENE_AXES`)은 훅이 아직 안 골라졌으니 **후보 전체**를
        # 넘긴다 — 한 후보만 박으면 사람이 다른 것을 골랐을 때 어긋난다(2026-10-06).
        images = await _do_images(
            {**lower, "items": items, "hook_candidates": _hook_candidates(hooks)},
            axis, used_scenes)
        entry: dict[str, Any] = {
            "hooks": hooks,
            "body": items,
            "images": images.get("images") or [],
            **where,
            **({"n": got["n"]} if got.get("n") else {}),
        }
        # 지도 축에만 있는 3-4. 훅과 무관하게 주제·장소만 보고 지을 수 있어 미리 만든다.
        if studio.axis_conf(axis).get("cta1"):
            entry["cta1"] = await studio.make_cta1(studio.Cta1Body(
                axis=axis, topic=name, hook="", items=items,
                n=int(got.get("n") or 0), **where))
            # ⚠ 캡션은 미리 만들지 않는다. 이 축 캡션은 **고른 훅을 그대로 끌어다 쓰는
            #   고정 틀**이라(지도_5단계) 훅이 정해지기 전에는 만들 수 없다(2026-09-04).
        else:
            caption = await studio.make_caption(studio.CaptionBody(
                axis=axis, topic=name, hook="", items=items))
            entry["caption"] = caption.get("caption") or ""
        return name, entry, "ok", ""
    except studio.TopicUnfit as e:
        # 「가게를 하나도 못 찾았다」 같은 **주제 탓**이다 — 내일도 같은 답이 나온다.
        return name, None, "unfit", str(e)[:200]
    except Exception as e:
        # 이쪽은 주제 탓이 아니다(codex CLI 오류·조회 실패). 제외하지 않고 넘어간다 —
        # 일시적인 실패로 멀쩡한 주제를 영영 지우면 안 된다.
        return name, None, "fail", str(e)[:200]


async def _do_prepare(chosen: dict[str, Any], axis: str) -> dict[str, Any]:
    """출근 전에 **미리 다 만들어 둔다.**

    사람이 아침에 화면을 열면 주제 10개가 있고, 각 주제마다 훅·사진·본문·캡션이 이미
    만들어져 있어 **고르기만** 하면 된다. 지금까지는 누를 때마다 만들기 시작해 사진에서
    6분씩 기다려야 했다(2026-09-03 요구).

    ⚠ 본문은 평소 「고른 훅」을 보고 짓지만 여기서는 훅을 고르기 전이라 **주제만 보고
      짓는다** — 그 주제의 일본어 표현이라 훅과 거의 무관하다. 사진은 주제·훅을 보고 짓는
      축이 있어(`HOOK_SCENE_AXES`) **훅 후보 전체**를 실어 준다(2026-10-06).
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
    fresh = list(first.get("items") or [])
    # ⚠ 보관함에는 **주제 이름만** 남는다. X인용처럼 주제가 곧 X 게시물인 축은 이름만으로
    #   아무것도 못 만든다 — post_id 가 없어 본문 단계가 「게시물 id 가 없습니다」로 죽는다
    #   (2026-09-21 실측 — 보관 주제 둘이 연달아 실패해 미리 만들기가 제자리걸음 했다).
    #   이번 회차 후보에 같은 주제가 있으면 그 줄을 쓰고, 없으면 그 축에서는 건너뛴다.
    by_topic = {str(i.get("topic") or "").strip(): i for i in fresh}
    needs_source = bool(studio.axis_conf(axis).get("x_source"))
    kept_rows: list[dict[str, Any]] = []
    for name in kept:
        row = by_topic.get(str(name).strip())
        if row is not None:
            kept_rows.append(row)
        elif needs_source:
            logger.info(f"[studio-worker] 보관 주제 「{name}」 는 이번 후보에 없어 "
                        "미리 만들지 않습니다(게시물 정보가 남아 있지 않다)")
        else:
            kept_rows.append({"topic": name, "why": "지난 회차에 보관해 둔 주제"})
    kept_names = {str(r.get("topic") or "").strip() for r in kept_rows}
    pool = kept_rows + [i for i in fresh
                        if str(i.get("topic") or "").strip() not in kept_names]
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

        # 이번에 **겹쳐서** 만들 주제를 모은다(남은 자리만큼만).
        chunk: list[dict[str, Any]] = []
        while (len(chunk) < PREPARE_BATCH and i < len(pool)
               and i < max_tries and len(topics) + len(chunk) < count):
            t = pool[i]
            i += 1
            name = str(t.get("topic") or "").strip()
            if not name:
                continue
            tried.append(name)
            chunk.append(t)
        if not chunk:
            break

        logger.info(f"[studio-worker] 미리 만들기 {len(topics) + 1}~{len(topics) + len(chunk)}/{count} "
                    f"— {len(chunk)}개를 겹쳐서: "
                    + " · ".join(str(t.get("topic") or "")[:16] for t in chunk))
        # ⚠ `used_scenes` 는 **묶음 시작 시점의 것**을 모두에게 같이 준다. 묶음 안에서는
        #   서로의 장면을 모르므로 그 안끼리는 겹칠 수 있다 — 묶음이 끝날 때 한꺼번에
        #   쌓아 다음 묶음에 넘긴다. 순차로 돌리면 겹침은 덜하지만 주제당 4~6분이 그대로다.
        snapshot = list(used_scenes)
        results = await asyncio.gather(
            *(_prepare_one(t, axis, need_places, snapshot) for t in chunk))

        for t, (name, entry, status, detail) in zip(chunk, results):
            if status == "ok" and entry:
                prepared[name] = entry
                topics.append(t)
                used_scenes += [str(x.get("prompt") or "") for x in (entry.get("images") or [])]
            elif status == "unfit":
                # 제외 목록에 넣지 않는다 — 이 회차에서만 버린다(2026-10-08 사람 지시 ·
                # `studio_steps._verify_topics` 와 같은 규칙).
                logger.warning(f"[studio-worker] 주제를 이번 회차에서 뺍니다 — {name}: {detail}")
                excluded.append(name)
            else:
                logger.warning(f"[studio-worker] 미리 만들기 실패 — {name}: {detail}")

    # X인용처럼 **모아 온 게시물이 곧 후보**인 축은 미리 만든 `count` 개 말고 **받은 것을 전부**
    # 화면에 올린다 (2026-10-14 트립앤라이프 — 「후보 10개만 올라와 있다」). 1단계가 지침서대로
    # 40개를 모아도 화면에는 미리 만든 10개만 보여, 나머지를 보려면 [다시 뽑기] 로 32분을 또
    # 기다려야 했다. 미리 만들지 않은 줄은 고르는 순간 그 자리에서 만들어진다(보관 주제와 같다).
    # ⚠ 장소를 확인하는 축(일본맛집·지도)은 그대로 둔다 — 「자리를 채운 주제만 사람에게 준다」
    #   (2026-09-09 사람 지시). 확인 안 한 주제를 끼워 주면 그 규칙이 깨진다.
    shown = list(topics)
    if needs_source:
        seen_names = {str(t.get("topic") or "").strip() for t in topics} | set(excluded)
        for t in pool:
            name = str(t.get("topic") or "").strip()
            if not name or name in seen_names:
                continue
            seen_names.add(name)
            shown.append(t)

    logger.info(f"[studio-worker] 미리 만들기 끝 — {len(topics)}/{count} 주제"
                + (f" · 후보 {len(shown)}개" if len(shown) != len(topics) else "")
                + (f" · 제외 {len(excluded)}개" if excluded else ""))
    return {"topics": shown,
            "kept": [k for k in kept if k not in excluded],
            "dropped": [*(first.get("dropped") or []), *excluded],
            "prepared": prepared}


HANDLERS = {
    "topics": _do_topics,
    "link": _do_link,          # 링크 한 건 → 캐러셀까지
    "prepare": _do_prepare,
    "keep": _do_keep,
    "hooks": _do_hooks,
    "images": _do_images,
    "body": _do_body,
    "cta1": _do_cta1,          # 지도 축에만 있다
    "caption": _do_caption,
    "build": _do_build,
}


async def _fill_x_source(session_id: str, axis: str, chosen: dict[str, Any]) -> dict[str, Any]:
    """고른 주제의 **게시물 정보를 후보에서 되짚어 채운다** (X인용 전용).

    후보 한 줄에는 post_id·사진 주소·원문이 다 실려 있는데, 화면은 주제를 고를 때
    **제목 한 줄만** `chosen` 에 넣는다. 그러면
      · 사진 단계가 원본 사진을 못 보고 전부 그려 버리고(캐러셀 558·559 가 그랬다),
      · 본문 단계는 「게시물 id 가 없습니다」로 죽는다
        (2026-09-18 — 회차 d52510892687a507 이 그 상태로 멈춰 있었다).

    화면을 고치는 게 원칙이지만, 화면이 무엇을 넘기든 굴러가야 한다. 채운 값은 서버에도
    올려 둔다 — 다음 단계와 화면이 같은 것을 보게.
    """
    from app.services import studio_remote
    from app.services import studio_steps as studio

    if not studio.axis_conf(axis).get("x_source"):
        return chosen
    topic = str(chosen.get("topic") or "").strip()
    if not topic:
        return chosen

    try:
        s = await studio_remote.call(f"/studio-sessions/{session_id}", method="GET", timeout=60)
    except Exception as e:
        logger.warning(f"[studio-worker] 후보를 되짚지 못했습니다: {str(e)[:200]}")
        return chosen

    found = next((t for t in ((s.get("candidates") or {}).get("topics") or [])
                  if str((t or {}).get("topic") or "").strip() == topic), None)
    if not found:
        if not chosen.get("post_id"):
            logger.warning(f"[studio-worker] 고른 주제를 후보에서 못 찾았습니다: {topic[:40]}")
        return chosen

    add = {k: found[k] for k in X_CARRY if found.get(k) not in (None, "", [])}
    if not add:
        return chosen

    # ⚠ **이미 들어 있는 post_id 를 믿으면 안 된다.** 화면은 주제를 바꿀 때 제목만 덮어쓰고
    #   앞 주제의 게시물 정보는 `chosen` 에 그대로 남긴다(PATCH 가 합치기라서). 그대로 두면
    #   **고른 주제와 다른 글이 본문에 찍힌다** — 2026-09-22 트립앤라이프 피드백에서
    #   「지정석은 양보할 의무가 없다」를 골랐는데 삼계탕 글이 찍혔다.
    #   그래서 **주제에 딸린 post_id 와 다르면 갈아 끼운다.**
    old = str(chosen.get("post_id") or "")
    new = str(add.get("post_id") or "")
    if old and new and old == new:
        return chosen
    if old and new:
        logger.warning("[studio-worker] 고른 주제와 게시물이 어긋나 바로잡습니다 — "
                       f"「{topic[:26]}」 {old} → {new}")
        # 앞 주제에서 남은 것까지 지운다. 새 주제에 없는 칸(사진·답글)이 남으면
        # 그것도 엉뚱한 글의 것이다.
        chosen = {k: v for k, v in chosen.items() if k not in X_CARRY}
    try:
        await studio_remote.call(f"/studio-sessions/{session_id}", {"chosen": add},
                                 method="PATCH", timeout=60)
    except Exception as e:
        logger.warning(f"[studio-worker] 채운 게시물 정보를 못 올렸습니다: {str(e)[:200]}")
    logger.info(f"[studio-worker] X 게시물 정보를 후보에서 채웠습니다 — {', '.join(add)}")
    return {**chosen, **add}


async def _handle(job: dict[str, Any]) -> None:
    from app.services import studio_remote

    session_id = job["id"]
    step = job["step"]
    # 이 아래 모든 원격 호출이 **이 회차를 연 사람 계정**으로 나간다(studio_remote.CURRENT_ACCOUNT).
    # 안 걸면 세션을 읽지도 못한다 — 서버가 자기 회차만 돌려주기 때문이다.
    if job.get("account"):
        studio_remote.CURRENT_ACCOUNT.set(job["account"])
    handler = HANDLERS.get(step)
    if not handler:
        logger.warning(f"[studio-worker] 모르는 단계: {step}")
        return

    logger.info(f"[studio-worker] {session_id} · {step} 시작")
    chosen = await _fill_x_source(session_id, job.get("axis") or "", job.get("chosen") or {})
    try:
        if step == "images":
            # 이 회차가 이미 쓴 무대를 피해서 그린다(밤에 만들 때는 `_do_prepare` 가 넘긴다).
            kind = str(chosen.get("image_kind") or "").strip()
            used, mine, items = await _scene_context(session_id,
                                                     str(chosen.get("topic") or ""))
            # 한쪽만 다시 그릴 때 남겨 둘 것. 남기는 것도 무대가 겹치면 안 된다.
            keep = [i for i in mine if kind and i.get("kind") != kind]
            used += [str(i.get("prompt") or "") for i in keep]
            # [다시 뽑기] 때도 본문을 실어 준다 — 화면은 `chosen` 에 본문을 담지 않는다.
            out = await _do_images({**chosen, "items": chosen.get("items") or items},
                                   job.get("axis") or "", used, keep)
        else:
            out = await handler(chosen, job.get("axis") or "")
    except Exception as e:
        logger.exception(f"[studio-worker] {session_id} · {step} 실패")
        await studio_remote.call(f"/studio-sessions/{session_id}", {"error": str(e)}, method="PATCH")
        return

    body: dict[str, Any] = {"pending": ""}      # 이제 사람이 고를 차례
    # 링크로 만드는 단계는 고른 것까지 스스로 채운다 — 화면이 같은 것을 보게 함께 올린다.
    if "__chosen__" in out:
        body["chosen"] = out.pop("__chosen__")
    if "__result__" in out:
        body["result"] = out["__result__"]
    else:
        body["candidates"] = out
    await studio_remote.call(f"/studio-sessions/{session_id}", body, method="PATCH")
    logger.info(f"[studio-worker] {session_id} · {step} 끝")


# 앞서 만들어 둔 것을 「아직 쓸 만하다」고 볼 시간. 23:00 → 06:00(7시간)은 안에 들고,
# 하루 뒤(24시간)는 밖으로 나간다.
FRESH_HOURS = 12


async def _has_fresh_batch(axis: str, account: str | None = None) -> bool:
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
            f"/studio-sessions/latest?axis={quote(axis)}", method="GET", account=account)
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
        # ⚠ `or` 로 쓰면 **빈 목록이 전역값으로 되살아난다.** 축이 「미리 만들지 않는다」고
        #   적어 둔 것(`"prepare_at": []`)을 존중하려면 키가 있는지로 갈라야 한다.
        times = conf["prepare_at"] if "prepare_at" in conf else global_times
        if at not in times:
            continue
        # ⚠ 잠금(stamp)을 **요일 확인보다 먼저** 건다. 거꾸로 두면 쉬는 날에도 그 1분 동안 5초마다
        #   「오늘은 쉽니다」 가 12번씩 찍혔다(2026-10-04 일요일 09:00 로그).
        stamp = f"{now:%Y-%m-%d} {at} {axis}"
        if stamp in done:
            continue
        done.add(stamp)
        # 이틀치만 기억하면 충분하다 — 무한정 쌓이지 않게 잘라 둔다.
        if len(done) > 16:
            for old in sorted(done)[:-8]:
                done.discard(old)
        # 시각마다 도는 요일이 다를 수 있다(`prepare_days`). 안 적은 시각은 매일 돈다 —
        # X인용만 주말을 쉰다(월=0 … 일=6).
        days = (conf.get("prepare_days") or {}).get(at)
        if days is not None and now.weekday() not in days:
            logger.info(f"[studio-worker] {at} — 「{axis}」 오늘({_DAYS_KO[now.weekday()]})은 쉽니다")
            continue

        # `prepare_always` 인 축은 **정해진 시각마다 무조건 새로 뽑는다** — 그때그때
        # 반응이 큰 것을 잡는 게 목적이라(X인용) 앞 회차가 멀쩡해도 건너뛰면 안 된다.
        # 축 주인 계정으로 연다 — 회차도 캐러셀도 그 계정에 생겨야 그 사람 화면에 보인다.
        account = conf.get("account")
        if not conf.get("prepare_always") and await _has_fresh_batch(axis, account):
            logger.info(f"[studio-worker] {at} — 「{axis}」 아직 안 쓴 회차가 있어 건너뜁니다")
            continue

        logger.info(f"[studio-worker] {at} — 「{axis}」 미리 만들기 시작 (주제 {settings.STUDIO_PREPARE_COUNT}개)")
        try:
            # 여는 순간 prepare 로 연다. 만든 뒤 바꾸면 그 사이에 다른 단계가 끼어든다.
            await studio_remote.call("/studio-sessions/", {"axis": axis, "pending": "prepare"},
                                     account=account)
        except Exception as e:
            logger.warning(f"[studio-worker] 「{axis}」 미리 만들기를 열지 못했습니다: {e}")


async def _sweep_old_sessions() -> None:
    """수명이 정해진 축의 **지난 회차를 지운다** (`AXES[축]["session_ttl_hours"]`).

    하루 세 번 미리 만드는 축(X인용)은 회차가 매일 세 개씩 쌓인다. 놔두면 화면이 무엇을
    이어 열지 헷갈리고 목록도 불어난다 — 2026-09-18 사람 지시 「각각 24시간 지나면
    삭제되게 해놔」.

    ⚠ **계정마다 따로** 부른다. 서버는 자기 회차만 지우므로(남의 것을 건드리면 안 된다)
      한 계정으로만 부르면 다른 사람 것이 영영 남는다.
    """
    from urllib.parse import quote

    from app.services import studio_remote
    from app.services.studio_steps import AXES

    for axis, conf in AXES.items():
        hours = int(conf.get("session_ttl_hours") or 0)
        if hours <= 0:
            continue
        for account in _accounts():
            try:
                got = await studio_remote.call(
                    f"/studio-sessions/old?axis={quote(axis)}&hours={hours}",
                    method="DELETE", account=account)
            except Exception as e:
                logger.warning(f"[studio-worker] 「{axis}」 지난 회차 정리 실패({account}): {str(e)[:200]}")
                continue
            count = int((got or {}).get("count") or 0)
            if count:
                logger.info(f"[studio-worker] 「{axis}」 {hours}시간 지난 회차 {count}개를 "
                            f"지웠습니다({account})")


# 정리는 한 시간에 한 번이면 충분하다 — 수명이 시간 단위다.
SWEEP_EVERY_SECONDS = 3600

# 훅 창고는 천천히 채운다(2026-09-29 사람 — 「속도 천천히 해도 된다」). 한 번에 몇십 건씩,
# 여섯 시간마다. 수집 게시물은 5일 뒤 목록에서 빠지니 그 안에 한 번은 돈다.
HOOK_BANK_EVERY_SECONDS = 6 * 3600


async def _refresh_hook_bank() -> None:
    """축마다 훅 창고를 조금씩 채운다. 폴링을 막지 않게 따로 띄워 부른다."""
    from app.services import hook_bank
    from app.services.studio_steps import AXES

    seen: set[str] = set()
    for conf in AXES.values():
        category = conf.get("hook_category") or ""
        if not category or category in seen:
            continue
        seen.add(category)
        try:
            await hook_bank.refresh(category, account=conf.get("account"))
        except Exception as e:
            logger.warning(f"[studio-worker] 훅 창고 「{category}」 채우기 실패: {str(e)[:200]}")

# 로그에 요일을 한글로 적는다. `datetime.weekday()` 와 같은 순서(월=0).
_DAYS_KO = "월화수목금토일"


def _days_label(days: list[int] | None) -> str:
    """`[0,1,2,3,6]` → `"월화수목일"`. 요일을 안 가리면 「매일」."""
    if days is None:
        return "매일"
    return "".join(_DAYS_KO[d] for d in sorted(days)) or "안 돎"


async def _loop() -> None:
    from app.services import studio_remote

    logger.info(f"[studio-worker] 시작 — {settings.STUDIO_API_BASE} 를 {POLL_SECONDS}초마다 봅니다")
    from app.services.studio_steps import AXES

    for axis, conf in AXES.items():
        times = (conf["prepare_at"] if "prepare_at" in conf else
                 ([settings.STUDIO_PREPARE_AT] if settings.STUDIO_PREPARE_AT else []))
        if not times:
            continue
        days = conf.get("prepare_days") or {}
        at = " · ".join(f"{t}({_days_label(days.get(t))})" for t in times)
        logger.info(f"[studio-worker] 「{axis}」 {at} 에 미리 만들기 예약됨")
    prepared_at: set[str] = set()
    # 같은 회차를 두 번 집지 않는다(한 단계가 몇 분씩 걸리므로 그 사이 폴링이 여러 번 돈다).
    busy: set[str] = set()

    logger.info(f"[studio-worker] 도는 계정: {', '.join(_accounts())}")

    last_sweep = datetime.min
    last_hook_bank = datetime.min
    hook_bank_task: asyncio.Task | None = None
    while True:
        try:
            if (datetime.now() - last_sweep).total_seconds() >= SWEEP_EVERY_SECONDS:
                last_sweep = datetime.now()
                await _sweep_old_sessions()
            if ((hook_bank_task is None or hook_bank_task.done())
                    and (datetime.now() - last_hook_bank).total_seconds() >= HOOK_BANK_EVERY_SECONDS):
                last_hook_bank = datetime.now()
                hook_bank_task = asyncio.create_task(_refresh_hook_bank())
            await _maybe_start_nightly(prepared_at)
            # ⚠ 계정마다 따로 물어본다. 서버의 `/pending` 은 **자기 회차만** 돌려주므로
            #   (studio_sessions.list_pending 의 `owner == user.id`), 한 계정으로만 물으면
            #   다른 사람이 화면에서 연 회차는 일꾼에게 영영 안 보인다 — 눌러도 아무 일이
            #   안 일어나는 것처럼 보인다. 서버는 그대로 두고 여기서 계정을 돈다.
            for account in _accounts():
                try:
                    data = await studio_remote.call(
                        "/studio-sessions/pending", method="GET", account=account)
                except Exception as e:
                    logger.warning(f"[studio-worker] {account} 물어보기 실패: {e}")
                    continue
                for job in data.get("jobs", []):
                    if job["id"] in busy:
                        continue
                    busy.add(job["id"])
                    # 이 회차를 연 사람의 계정 — 결과물이 그 계정에 생겨야 한다.
                    job["account"] = account

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
