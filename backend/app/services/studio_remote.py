"""원클릭 대시보드가 캐러셀을 만들 **원격 스택** 클라이언트.

왜 원격인가 — 대시보드는 이 PC 에서 돈다(codex 가 여기 있으므로). 그런데 트래블뷰
템플릿(id 80)·기존 캐러셀·편집기는 전부 **dev 스택**에 있고, 템플릿은 **계정별**이라
로컬 DB 에는 없다(2026-09-02 확인 — junhyeok 계정엔 80 이 없고 solhee 계정에 있다).
로컬에 만들면 사람이 편집 링크를 열어도 자기 캐러셀이 없다. 봇도 같은 이유로 이쪽을 본다.

인증은 `settings.STUDIO_ACCOUNT / STUDIO_PASSWORD` 로 로그인해 토큰을 받아 쓴다.
토큰은 만료될 수 있으므로 401 이면 한 번 다시 로그인하고 재시도한다.

⚠ dev 스택은 sslip.io 자체 서명 인증서라 검증을 끄고 붙는다(봇도 같다).
"""

import asyncio
import json
import logging
import ssl
import urllib.error
import urllib.request
import uuid
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)

_TOKEN: str | None = None
_LOCK = asyncio.Lock()

_SSL = ssl.create_default_context()
_SSL.check_hostname = False
_SSL.verify_mode = ssl.CERT_NONE


def is_configured() -> bool:
    return bool(settings.STUDIO_API_BASE and settings.STUDIO_ACCOUNT)


def _base() -> str:
    return settings.STUDIO_API_BASE.rstrip("/")


def _request(path: str, *, data: bytes | None, headers: dict[str, str], timeout: float,
             method: str | None = None) -> Any:
    req = urllib.request.Request(_base() + path, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, context=_SSL, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
    return json.loads(raw) if raw else {}


async def _login() -> str:
    body = json.dumps({
        "username": settings.STUDIO_ACCOUNT,
        "password": settings.STUDIO_PASSWORD,
    }).encode()
    result = await asyncio.to_thread(
        _request, "/auth/login",
        data=body, headers={"Content-Type": "application/json"}, timeout=30,
    )
    token = result.get("access_token")
    if not token:
        raise RuntimeError("원격 스택 로그인에 실패했습니다 (토큰 없음)")
    return str(token)


async def call(path: str, payload: dict | None = None, *,
               method: str = "POST", timeout: float = 120) -> Any:
    """토큰을 붙여 부른다. 401 이면 한 번만 다시 로그인하고 재시도한다."""
    global _TOKEN
    if not is_configured():
        raise RuntimeError("STUDIO_API_BASE / STUDIO_ACCOUNT 가 설정되지 않았습니다")

    method = method.upper()
    for attempt in (1, 2):
        async with _LOCK:
            if _TOKEN is None:
                _TOKEN = await _login()
            token = _TOKEN
        headers = {"Authorization": f"Bearer {token}"}
        data = None
        if method != "GET":
            headers["Content-Type"] = "application/json"
            data = json.dumps(payload or {}, ensure_ascii=False).encode("utf-8")
        try:
            return await asyncio.to_thread(
                _request, path, data=data, headers=headers, timeout=timeout, method=method
            )
        except urllib.error.HTTPError as e:
            if e.code == 401 and attempt == 1:
                async with _LOCK:
                    _TOKEN = None          # 만료됐다 — 다시 받는다
                continue
            detail = e.read().decode("utf-8", errors="replace")[:300]
            raise RuntimeError(f"{path} 호출 실패 ({e.code}): {detail}") from e
    raise RuntimeError(f"{path} 호출 실패: 인증이 계속 거부됩니다")


async def upload_image(blob: bytes, filename: str = "image.png") -> str:
    """이미지를 원격에 올리고 **전체 주소**를 돌려준다.

    ⚠ 서버는 `/api/images/...` **상대 주소**를 준다. 그대로 캐러셀에 넣으면 편집기가
      못 읽는다 — `/api` 를 뗀 웹 주소를 앞에 붙여 전체 주소로 만든다
      (`config.apiBase` 를 그냥 붙이면 `/api/api/...` 가 된다. 봇에서 겪은 함정).
    """
    global _TOKEN
    boundary = uuid.uuid4().hex
    body = b"".join([
        f"--{boundary}\r\n".encode(),
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'.encode(),
        b"Content-Type: image/png\r\n\r\n",
        blob,
        f"\r\n--{boundary}--\r\n".encode(),
    ])

    for attempt in (1, 2):
        async with _LOCK:
            if _TOKEN is None:
                _TOKEN = await _login()
            token = _TOKEN
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        }
        try:
            result = await asyncio.to_thread(
                _request, "/images/upload", data=body, headers=headers, timeout=180
            )
            break
        except urllib.error.HTTPError as e:
            if e.code == 401 and attempt == 1:
                async with _LOCK:
                    _TOKEN = None
                continue
            raise RuntimeError(
                f"이미지 업로드 실패 ({e.code}): {e.read().decode('utf-8', errors='replace')[:200]}"
            ) from e

    url = str(result.get("url") or result.get("path") or "")
    if url.startswith("/"):
        web_base = _base()[: -len("/api")] if _base().endswith("/api") else _base()
        url = web_base + url
    return url


def editor_url(carousel_id: int) -> str:
    web_base = _base()[: -len("/api")] if _base().endswith("/api") else _base()
    return f"{web_base}/editor/{carousel_id}"
