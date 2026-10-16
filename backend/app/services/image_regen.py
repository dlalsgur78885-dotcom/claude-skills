"""실사 사진을 **레퍼런스로** 다시 그린다 — fal.ai `nano-banana-2/edit`.

일본맛집 축 본문 배경이 이 길로 간다(2026-10-15 사람 지시 — 「원본이랑 똑같이 말고,
실제 사진 레퍼런스로 재생성으로 할게」 · `docs/process/일본맛집_3-3단계_본문.md`
「고른 사진은 레퍼런스다」). 구글 지도 실사를 그대로 깔지 않고, 사람이 고른 그 사진을
입력으로 넣어 **같은 가게·같은 메뉴를 새로 찍은 것처럼** 다시 그린다. 비율은 캔버스와 같은 4:5 다.

⚠ `/api/images/restyle`(Gemini nanobanana2)로는 못 한다 — `GEMINI_API_KEY` 에 IP 제한이
  걸려 이 PC·서버 모두 `403 API_KEY_IP_ADDRESS_BLOCKED` 다(2026-10-14 실측).
  그래서 fal.ai 쪽으로 돈다.
"""

from __future__ import annotations

import base64
import logging

from app.config import settings
# fal 호출·내려받기는 이미 image_enhance 에 한 벌 있다 — 두 벌로 만들지 않는다.
from app.services.image_enhance import _download, _fal_post

logger = logging.getLogger(__name__)

MODEL = "fal-ai/nano-banana-2/edit"
# 본문 배경 비율 — **캔버스와 같은 4:5**(2026-10-15 사람 지시). 아침에 3:4 로 갔더니 1080×1350 에
# 얹을 때 1.2배 늘고 위아래 7% 가 잘려, 모델이 잡은 구도가 그대로 안 들어갔다.
ASPECT_RATIO = "4:5"

# 레퍼런스는 **무엇을 찍을지**만 알려 준다 — 베끼지 않는다.
# 사진의 결은 일본맛집_3-2단계 「음식 사진의 결」·「먹음직스러워야 한다」 그대로다.
# 음식은 **위쪽에** 둔다 — 낱장 아래 5분의 1 에 글이 올라가 그 자리를 가린다
# (2026-10-15 사람 지시 — 「메인이 되는 영역은 위쪽에 넣어서 생성하도록」).
# 2026-10-15 추가 지시 — 「음식이 더 잘 보이는 각도 · 그림자 자연스럽게 · 어색하게 잘리지 않고
# 자연스럽게 이어지도록 · 주변에 있는 쓸데없는것까지 똑같이 생성할 필요 없음」.
# 2026-10-16 사람 지시 — 「이미지에 글자가 하나도 없어서 어색해보여. 글자까지 생성해줘」.
# `no text, no logos` 를 뺐다 — 그릇·젓가락집·노렌·메뉴판처럼 **현실에 글자가 있는 자리**는
# 짧고 또렷하게 넣는다. 깨진 글자·가짜 문자·캐러셀 문구는 여전히 금지이고, 또렷하게 못 쓸
# 자리는 초점을 흐려 둔다(무지로 비우지 않는다). 위 「clutter」 줄에서도 `menus, signage` 를
# 뺐다 — 남겨 두면 새 규칙과 부딪힌다. 원본은 `일본맛집_3-2단계_썸네일이미지.md` 「글자」다.
PROMPT = " ".join([
    "Use this photo only as a reference for the dish and the shop it came from.",
    "Take a NEW photo of that same dish at that same kind of shop — same food and same kind of",
    "serving ware, but freshly framed: do not copy the reference composition, and do not swap in a",
    "different dish.",
    "Do not reproduce the clutter around the dish in the reference — other tables, bags, flyers,",
    "extra side dishes and anything that is not part of the hero serving can simply be gone.",
    "Make it look like the single best customer review photo taken on a phone at the table:",
    "shot from slightly above, about 60 degrees, so the food itself reads clearly — the inside of the",
    "bowl, the cut surfaces and the toppings are all visible at a glance,",
    "the hero serving fills most of the upper two thirds of the frame and sits whole inside it;",
    "where something does run past the frame edge let it continue naturally the way a real photo does,",
    "never an awkward cut that slices the hero dish in half or leaves an object looking severed,",
    "the reference photo is a different shape than this frame — fill this whole frame with one",
    "continuous real scene, carrying the same table, background and lighting all the way out to every",
    "edge as freshly photographed surface; never stretch, mirror, repeat or smear the reference edge to",
    "reach an edge, and never leave bars, borders, flat padding or an obviously pasted-in strip,",
    "leave the bottom fifth of the frame as plain, softly blurred table surface — no part of the dish,",
    "no serving ware and no important detail there, because text is laid over that strip,",
    "freshly served — visible steam, glossy sauce and oil sheen, vivid natural ingredient colors,",
    "warm shop lighting from the side so highlights sparkle, with soft natural shadows that fall",
    "consistently with that one light — nothing floating without a shadow, no harsh double shadows,",
    "background only slightly blurred,",
    "clean table — no hands, no people, no crumpled napkins, no spilled crumbs, no empty plates, no clutter,",
    "unedited phone-camera color, no watermarks,",
    "lettering that really belongs in such a scene may stay — a short shop name on the bowl, plate,",
    "chopstick sleeve or tray, a noren, sign or menu board behind the table — kept short, accurate and",
    "legible; never render carousel copy, long sentences, broken glyphs, fake characters or distorted",
    "numbers, and where accurate lettering is not possible let that surface fall out of focus in the",
    "background instead of wiping it blank.",
])


# 일본숙소 축 본문 배경(2026-10-15 저녁 사람 지시 — 「본문 이미지도 원본 이미지 참고해서 직접 찍은 듯한
# 이미지로 재생성」). 원본은 `일본숙소_3-3단계_본문.md` 「사진 — 실사를 레퍼런스로 다시 그린다」의
# 「2) 재생성」 문단이고, 아래는 그 영어판이다 — 한쪽을 고치면 같이 고친다.
# 레퍼런스는 **어느 숙소의 무엇인지**만 알려 준다. 구조·마감·색·창 배열은 가져오고 구도는 새로 잡는다.
# 맛집 `PROMPT` 를 그대로 쓰면 객실·외관이 「한 접시」로 다시 그려진다 — 그래서 따로 둔다.
HOTEL_PROMPT = " ".join([
    "Use this photo only as a reference for which hotel this is and which part of it is shown —",
    "keep that place's real structure, finishes, colors and window layout.",
    "Do not copy the reference composition: take that same scene anew, like a single photo a guest",
    "staying there took on a phone.",
    "Unedited phone-camera color with no filter and no HDR, natural light coming in from one side",
    "and one consistent set of shadows — no double shadows, nothing floating without a shadow.",
    "Do not reproduce the clutter in the reference: notices and signs taped up, piles of towels,",
    "scattered luggage, other guests.",
    "No people, no hands, no watermarks. Lettering and signage may stay only on an exterior shot and",
    "only exactly as they appear in the reference; never add any new lettering.",
    "Keep the bottom fifth of the frame simple and uncluttered, because text is laid over that strip.",
    "The reference photo is a different shape than this frame — fill this whole frame with one",
    "continuous real scene, continuing the same room or building in the same light all the way out to",
    "every edge; never stretch, mirror, repeat or smear the reference edge, and never leave bars,",
    "black margins, flat padding or an obviously pasted-in strip.",
])

# 축의 `regen_prompt` 값 → 프롬프트. 없는 이름이면 기본(맛집)이다.
PROMPTS = {"hotel": HOTEL_PROMPT}


def prompt_for(key: str | None) -> str:
    """축 설정의 `regen_prompt` 이름으로 프롬프트를 고른다. 비었거나 모르는 이름이면 맛집용 `PROMPT`."""
    return PROMPTS.get((key or "").strip(), PROMPT)


async def _as_data_uri(source_url: str) -> str:
    """fal 이 읽을 수 있게 **바이트를 실어 보낸다.**

    우리 서버 주소(`/api/images/...`)는 밖에서 못 읽고, 구글 사진 주소는 만료되거나
    레퍼러를 요구할 때가 있다 — 어느 쪽이든 받아서 data URI 로 넘기는 게 안전하다.
    """
    url = source_url
    if url.startswith("/api/"):
        url = f"http://127.0.0.1:8000{url}"
    blob = await _download(url)
    return "data:image/png;base64," + base64.b64encode(blob).decode("ascii")


async def from_reference(
    source_url: str,
    *,
    prompt: str = PROMPT,
    aspect_ratio: str = ASPECT_RATIO,
    timeout: float = 180.0,
) -> bytes:
    """실사 1장을 레퍼런스로 넣어 다시 그린 그림의 **바이트**를 돌려준다.

    부르는 쪽이 이것을 스튜디오에 올려 주소를 얻는다(`studio_remote.upload_image`) —
    구글 사진 주소처럼 만료되지 않게.
    """
    fal_key = (settings.FAL_KEY or "").strip()
    if not fal_key:
        raise RuntimeError("FAL_KEY is not configured")

    result_url = await _fal_post(
        MODEL,
        {
            "prompt": prompt,
            "image_urls": [await _as_data_uri(source_url)],
            "num_images": 1,
            "aspect_ratio": aspect_ratio,
        },
        fal_key,
        timeout=timeout,
    )
    out = await _download(result_url)
    logger.info("[regen] %s → %d bytes (%s)", source_url[:70], len(out), aspect_ratio)
    return out
