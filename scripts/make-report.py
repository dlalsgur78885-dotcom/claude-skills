"""정리한 내용을 웹 보고서로 올리고 링크를 찍는다 (2026-10-25 사람 지시).

디스코드 답은 3줄 안쪽이라, 표·비교·회차 정리처럼 길게 봐야 하는 것은 보고서로 보낸다.

  python scripts/make-report.py "<제목>" <마크다운 파일>
  python scripts/make-report.py "<제목>" -          (표준 입력으로 마크다운)

출력 한 줄: 보고서 주소. 그 주소를 디스코드 답에 그대로 붙인다.
본문은 마크다운만 된다 — HTML 을 넣으면 글자 그대로 보인다(`backend/app/api/reports.py`).
"""

import asyncio
import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))
sys.stdout.reconfigure(encoding="utf-8")
# 마크다운 파일 경로는 부른 자리 기준이라 먼저 절대경로로 잡아 둔다.
SRC_ARG = sys.argv[2] if len(sys.argv) == 3 else ""
SRC_PATH = None if SRC_ARG in ("", "-") else Path(SRC_ARG).resolve()
# 백엔드 설정은 backend/.env 를 **현재 폴더 기준**으로 읽는다 — 그 자리로 옮겨 가야 계정이 잡힌다.
os.chdir(BACKEND)

from app.services import studio_remote  # noqa: E402


def main() -> None:
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    title = sys.argv[1]
    markdown = sys.stdin.read() if SRC_PATH is None else SRC_PATH.read_text(encoding="utf-8")
    if not markdown.strip():
        sys.exit("보고서 본문이 비어 있습니다.")
    res = asyncio.run(studio_remote.call("/reports/", {"title": title, "markdown": markdown}, timeout=40))
    print(f"{studio_remote._base()}/reports/{res['id']}")


if __name__ == "__main__":
    main()
