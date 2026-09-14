"""지도 축의 표지 그림 — **그리지 않고 진짜 지도를 찍는다.**

`지도_3-2단계_썸네일이미지.md` 2026-08-26 변경:

> `generate_image` 로 「구글맵 화면풍」을 그리던 방식을 **버린다.**
> 그리지 말고 **실제 지도 화면을 캐처해서 쓴다.**

## 왜 노드를 부르나

찍는 일은 봇의 `browser-capture.js`(playwright)가 이미 하고 있고, 그 안에 이 화면
특유의 함정이 다 들어 있다 — 타일이 안 멎어 `networkidle` 로는 못 기다린다든가,
장마다 처음 화면으로 되돌리지 않으면 앞 장의 필터가 남아 **조용히 엉뚱한 화면**이
찍힌다든가. 파이썬으로 옮겨 적으면 그 교훈을 처음부터 다시 배우게 된다.
그래서 `place_lookup` 이 봇의 파이썬 벤더를 부르는 것과 같은 이유로, 여기서는
**노드를 자식 프로세스로 부른다.** 방향만 반대다.

## 카드가 안 보여야 한다

사람 지시(2026-08-28) — 「선택한 지도에서 **카드만** 안 보이게 확대해서 넣어주면
내가 알아서 조절할게」. 확대해서 범위가 줄거나 구도가 치우치는 것은 문제 삼지 않는다.

**이 자리는 완전 자동이 안 된다.** 카드가 빠졌는지는 그림을 봐야 알 수 있고, 배율·
위치는 지역마다 다르다. 그래서 여기서는 **지침서의 「검증된 시작값」으로 후보 2~3장을
찍어 두고**, 어느 것을 쓸지는 사람이 화면에서 고른다(다른 축이 사진 5장 중 하나를
고르는 것과 같은 자리다). 값이 없는 지역은 기본값으로 찍고, 마음에 안 들면 [다시 뽑기].
"""

import asyncio
import json
import logging
import shutil
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

BOT_ROOT = Path(__file__).resolve().parents[3].parent / "캐러셀 봇"
GUIDE_URL = "https://travelassi-web-production.up.railway.app/user_renew_vue/guides{gid}.apsl"

NODE = shutil.which("node")

# 배율만 다르게 해서 후보를 낸다. 앵커는 **주제의 그 버튼**이다(아래 `capture` 참고).
#
# 버튼을 누르면 지도가 그 버튼의 핀 전체에 맞춰지는데, 이상치 핀 하나가 섞이면 범위가
# 크게 벌어진다(전국 가이드에서 오키나와 핀 때문에 일본까지 들어왔다 — 2026-09-04).
# 그래서 **조여 들어가는 쪽**으로 후보를 낸다. 구도까지 맞추려 들지 않는다 —
# 지침서가 「범위·구도 때문에 되묻지 않는다. 그건 사람이 편집기에서 조절한다」고 정했다.
ZOOMS: list[int] = [0, 2, 4]

# 배경으로 쓸 거면 4:5 (지침서). 1600×1350 은 전국 컷에 쓰던 값이라 세로가 모자라다.
SIZE = {"width": 1080, "height": 1350}

# ⚠ 인자가 아니라 **표준입력**으로 넘긴다. `node -e` 는 스크립트 파일이 없어 첫 인자가
#   argv[1] 로 오는데(argv[2] 가 아니다), 그 차이로 조용히 undefined 를 파싱하다 죽었다
#   (2026-09-04). 윈도우의 명령줄 길이·따옴표 문제도 함께 피한다.
_SCRIPT = r"""
import { captureMany } from './src/browser-capture.js';
let raw = '';
for await (const chunk of process.stdin) raw += chunk;
try {
  const r = await captureMany(JSON.parse(raw));
  process.stdout.write(JSON.stringify(r));
} catch (e) {
  process.stdout.write(JSON.stringify({ error: String(e && e.message || e) }));
}
"""


def is_available() -> bool:
    return bool(NODE) and (BOT_ROOT / "src" / "browser-capture.js").is_file()


def guide_url(guide_id: str) -> str:
    return GUIDE_URL.format(gid=guide_id)


async def capture(guide_id: str, button: str = "", count: int = 3,
                  anchor: str = "") -> list[bytes]:
    """그 가이드 화면의 지도를 후보로 몇 장 찍어 바이트로 돌려준다.

    **앵커는 주제의 그 버튼이다.** 지침서의 「검증된 시작값」은 *장소*를 눌러 지도를
    점프시키는데, 그러면 누른 장소의 **카드가 화면에 남는다** — 지침서가 빼라고 한 바로
    그 카드다. 그래서 지역마다 카드를 밀어낼 pan 값을 따로 외워야 했다(그 표가 생긴 이유).

    버튼 칩을 누르면 그럴 필요가 없다(2026-09-04 실측):
      · 카드가 아예 안 뜬다 — 장소를 고른 게 아니니까.
      · 지도가 **그 버튼의 핀들**에 맞춰 다시 잡힌다. 주제가 곧 그 버튼이라 의미도 맞다.
      · 지역별 pan 표가 필요 없다. 배율만 몇 단계 다르게 해서 후보를 낸다.

    **`anchor` 는 지역까지 좁힌 주제에만 준다.** 버튼 칩만 누르면 화면이 그 버튼의 핀
    **전체**에 맞춰져, 「도쿄 …」 주제인데 한국까지 담긴 지도가 나온다(2026-09-04).
    그래서 그 지역 장소를 하나 더 눌러 지도를 거기로 점프시킨다. 대신 지침서가 빼라고 한
    **카드가 화면에 남을 수 있다** — 후보 중에 카드가 걸린 장이 있으면 사람이 다른 장을
    고르거나 [다시 뽑기] 한다(이 자리는 원래 사람이 고르는 자리다).

    실패한 장은 건너뛴다 — 한 장도 못 찍으면 빈 목록이다(부르는 쪽이 판단한다).
    """
    if not is_available():
        logger.warning("[map] node 나 봇의 browser-capture.js 를 찾지 못했습니다.")
        return []

    click = [x for x in (button, anchor) if x]
    shots = [
        # `map_only` 가 아니라 **`mapOnly`** 다 — captureMany 는 카멜케이스를 받는다
        # (봇의 tools.js 가 map_only 를 여기로 옮겨 준다. 우리는 직접 부르므로 직접 맞춘다).
        # ⚠ `waitMs` 가 반드시 있어야 한다. domcontentloaded 로 일찍 여는 대신, 타일이
        #   그려질 시간을 여기서 준다. 안 주면 **빈 지도**가 찍히고 mapOnly 크롭도 실패해
        #   목록까지 통째로 담긴 그림이 나온다(2026-09-04 실측).
        {"click": click, "zoom": z, "mapOnly": True, "waitMs": 12_000, "label": f"확대{z:+d}"}
        for z in ZOOMS[:count]
    ]
    payload = json.dumps({
        "url": guide_url(guide_id), "shots": shots, **SIZE,
        # ⚠ 큰 가이드(984곳)는 45초 안에 다 안 열린다 — 그래서 여유를 넉넉히 준다
        #   (2026-09-04 kids_family 가 시간 초과로 한 장도 못 찍혔다).
        #   그렇다고 `networkidle` 을 기다리면 **영영 안 온다** — 150초를 줘도 시간 초과였다.
        #   타일이 끊임없이 흘러들어오기 때문이다(browser-capture.js 에도 같은 기록이 있다).
        #   그래서 일찍 열고, 그리는 시간은 위 `waitMs` 로 준다.
        "firstWaitUntil": "domcontentloaded",
        "navTimeoutMs": 90_000,
    }, ensure_ascii=False)

    proc = await asyncio.create_subprocess_exec(
        NODE, "--input-type=module", "-e", _SCRIPT,
        cwd=str(BOT_ROOT), stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    try:
        out, err = await asyncio.wait_for(proc.communicate(payload.encode("utf-8")), timeout=300)
    except asyncio.TimeoutError:
        proc.kill()
        logger.warning("[map] 캡처가 5분을 넘겼습니다.")
        return []

    try:
        data = json.loads(out.decode("utf-8", errors="replace") or "{}")
    except json.JSONDecodeError:
        logger.warning(f"[map] 캡처 응답을 읽지 못했습니다: {err.decode('utf-8', 'replace')[-200:]}")
        return []
    if data.get("error"):
        logger.warning(f"[map] 캡처 실패: {data['error']}")
        return []

    blobs: list[bytes] = []
    for one in data.get("shots") or []:
        if one.get("error") or not one.get("path"):
            logger.warning(f"[map] 한 장 실패: {one.get('error') or '경로 없음'}")
            continue
        # 못 누른 라벨이 있으면 그 장은 원하던 화면이 아니다 — 조용히 쓰지 않는다.
        if one.get("not_found"):
            logger.warning(f"[map] 클릭 실패라 버립니다: {one['not_found']}")
            continue
        try:
            blobs.append(Path(one["path"]).read_bytes())
        except OSError as e:
            logger.warning(f"[map] 파일을 읽지 못했습니다: {e}")
    return blobs
