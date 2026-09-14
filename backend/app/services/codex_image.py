"""Codex CLI 내장 image_gen 으로 이미지를 만든다.

봇의 `캐러셀 봇/src/codex-image.js` 와 같은 방식이다 — 로그인된 Codex 세션을 쓰므로
**API 키가 필요 없다.** 그래서 이 경로는 **codex 가 깔리고 로그인된 기계에서만** 돈다
(2026-09-02 사람 결정: 대시보드는 이 PC 에서 돌린다).

옮겨 온 함정 두 가지 — 둘 다 봇에서 겪고 고친 것이다:

1. **결과 파일은 「요청한 자리」에 없을 수 있다.** Codex 는 그림을 자기 폴더에 먼저 넣고
   요청한 위치로는 **셸 명령으로 옮기는데**, 윈도우 샌드박스가 그 셸을 막는다
   ("apply deny-read ACLs"). 그러면 그림은 멀쩡히 만들어졌는데 마지막 한 걸음에서 막혀
   "안 만들어졌다" 로 끝난다. 그래서 `~/.codex/generated_images/<thread_id>/` 도 함께 본다.
   (2026-09-02 서버에서 실측 — 두 장 다 이쪽에서 회수됐다.)
2. **작업 폴더는 %TEMP% 밖이어야 한다.** cwd 를 %TEMP% 로 주면 같은 ACL 오류가 난다.

느리다 — 한 장에 1~4분이다. 웹 요청 하나로 기다리게 하지 말고 백그라운드로 돌릴 것.
"""

import asyncio
import json
import logging
import os
import shutil
import tempfile
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)

CODEX_CLI = shutil.which("codex") or shutil.which("codex.cmd")

# Codex 가 그림을 먼저 떨구는 자리. 세션(thread)별로 폴더가 갈려 남의 그림을 집을 일이 없다.
GENERATED_DIR = Path.home() / ".codex" / "generated_images"

# %TEMP% 밖이어야 한다(위 2번). 데이터 폴더 아래에 둔다.
WORK_ROOT = settings.DATA_DIR / "codexgen"

# 한 장에 40~60초이고 프로세스마다 메모리를 먹는다. 무제한으로 띄우지 않는다.
# 4 → 8 (2026-09-03): 10장이 3묶음으로 나뉘어 4분 반이 걸렸다. 8이면 2묶음이다.
# ⚠ 이 수만큼 codex 프로세스가 동시에 뜬다. 밤에 도는 작업이라 8로 뒀지만,
#   낮에 사람이 PC 를 쓰는 중에 돌리면 느려진다. 그럴 땐 도로 낮출 것.
MAX_CONCURRENT = 8

# ⚠ 자물쇠는 **프로세스에 하나**여야 한다. 부를 때마다 새로 만들면 축을 두 개 동시에
#   준비할 때 8+8 = 16 개가 뜬다(2026-09-03 — 밤 준비를 두 축으로 늘리며 잡은 것).
_GATE = asyncio.Semaphore(MAX_CONCURRENT)


def is_available() -> bool:
    return bool(CODEX_CLI)


def _pick_generated(thread_id: str) -> Path | None:
    """codex 자기 폴더에서 방금 만든 그림을 집어온다."""
    if not thread_id:
        return None
    d = GENERATED_DIR / thread_id
    if not d.is_dir():
        return None
    pngs = sorted(d.glob("*.png"), key=lambda p: p.stat().st_mtime, reverse=True)
    return pngs[0] if pngs else None


def _read_thread_id(stdout: bytes) -> str:
    """`--json` 첫 이벤트의 thread_id. 이게 곧 위 폴더 이름이다."""
    for line in stdout.decode("utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict) and event.get("thread_id"):
            return str(event["thread_id"])
    return ""


async def _generate_one(prompt: str, size: str, timeout: float) -> bytes:
    if not CODEX_CLI:
        raise RuntimeError("codex CLI 를 찾지 못했습니다. 이 기계에 설치·로그인이 필요합니다.")

    WORK_ROOT.mkdir(parents=True, exist_ok=True)
    workdir = tempfile.mkdtemp(prefix="gen-", dir=str(WORK_ROOT))

    instruction = "\n".join([
        "Generate exactly one image by calling image_gen.imagegen exactly once.",
        'Save it to "out.png" in the current working directory.',
        f"Requested size: {size}.",
        "Do NOT use OPENAI_API_KEY, the Images API, python, or any fallback CLI.",
        # 셸을 부르면 윈도우 샌드박스가 막아 확인에 매달리다 끝난다. 아예 부르지 못하게 한다.
        "Do NOT run any shell command. Do not verify the file, do not list the directory.",
        "Calling image_gen.imagegen is the only action you take.",
        "",
        "Image description:",
        prompt,
    ])

    env = {**os.environ, "NO_COLOR": "1"}
    env.pop("OPENAI_API_KEY", None)  # 내장 도구만 쓰게 한다

    try:
        proc = await asyncio.create_subprocess_exec(
            CODEX_CLI, "exec",
            "--skip-git-repo-check", "--ephemeral", "--color", "never",
            "--sandbox", "workspace-write", "--json", "-",
            cwd=workdir, env=env,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(instruction.encode("utf-8")), timeout=timeout
            )
        except asyncio.TimeoutError:
            proc.kill()
            raise RuntimeError(f"이미지 생성이 {int(timeout)}초를 넘겼습니다.")

        asked = Path(workdir) / "out.png"
        source = asked if asked.exists() else _pick_generated(_read_thread_id(stdout))
        if not source or not source.exists():
            detail = stderr.decode("utf-8", errors="replace").strip()[-200:]
            raise RuntimeError(f"이미지가 만들어지지 않았습니다. {detail}")
        return source.read_bytes()
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


async def generate_images(
    prompts: list[str],
    size: str = "1024x1536",
    timeout: float = 600.0,
) -> list[bytes | None]:
    """여러 장을 동시에 만든다. 실패한 자리는 None 이다(한 장이 죽어도 나머지는 살린다)."""
    async def one(p: str) -> bytes | None:
        async with _GATE:
            try:
                return await _generate_one(p, size, timeout)
            except Exception as e:
                logger.warning(f"[codex-image] 실패: {e}")
                return None

    return list(await asyncio.gather(*(one(p) for p in prompts)))
