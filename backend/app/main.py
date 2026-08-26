"""FastAPI application entry point."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.router import api_router
from app.config import settings
from app.database import init_db
from app.services.scheduler import start_scheduler, stop_scheduler

# Surface application-level INFO logs alongside Uvicorn's access logs so we can
# trace per-step timing (e.g. cutout pipeline stages).
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Refuse to boot with the dev secret in production
    import os
    if os.environ.get("ENV", "").lower() == "production" and settings.SECRET_KEY == "dev-only-change-me":
        raise RuntimeError("SECRET_KEY must be set in production (set env var)")
    # Startup
    await init_db()
    # Push admin-managed API keys from DB into os.environ so litellm/google-genai
    # pick them up. Falls back silently if table not yet created.
    try:
        from app.services.settings_provider import apply_to_environ
        await apply_to_environ()
    except Exception as e:
        # NOTE: 여기 있던 지역 `import logging` 을 제거했다. 함수 안에 지역 import 가
        # 하나라도 있으면 `logging` 이 함수 전체에서 지역변수가 되어, 이 except 를
        # 타지 않은 경로에서 logging 을 쓰면 UnboundLocalError 가 난다.
        # (모듈 최상단에서 이미 import 하고 있으므로 지역 import 는 불필요했다.)
        logging.getLogger(__name__).warning(f"[startup] apply_to_environ failed: {e}")
    if settings.ENABLE_SCHEDULER:
        start_scheduler()
    else:
        logging.getLogger(__name__).warning(
            "[startup] ENABLE_SCHEDULER=false — 백그라운드 잡 비활성 (수집/정리/만료 안 돎)"
        )
    yield
    # Shutdown
    if settings.ENABLE_SCHEDULER:
        stop_scheduler()


app = FastAPI(
    title="캐러셀 자동화",
    description="인스타그램 카드뉴스 벤치마킹 수집 및 자동 생성 플랫폼",
    version="0.1.0",
    lifespan=lifespan,
)

# 캔버스 저장 본문 상한을 거는 경로. 이미지 업로드는 multipart 라 아래 조건에 안 걸린다.
_SAVE_GUARD_PATHS = ("/api/carousels", "/api/templates")


@app.middleware("http")
async def limit_canvas_save_size(request: Request, call_next):
    """거대한 캔버스 저장을 **본문을 읽기 전에** 거절한다.

    2026-08-26 사고: 붙여넣기로 박힌 base64 때문에 canvas_data 가 17.5MB 가 됐고,
    1초 debounce 자동저장이 그 크기를 반복 PATCH 해 워커가 메모리 초과로 죽었다.
    컨테이너는 Up 인 채 전 요청이 504 가 되어 "봇 먹통" 으로만 보였다.

    본문을 파싱한 뒤에 크기를 재면 이미 메모리를 다 쓴 뒤라 늦다. Content-Length 로
    먼저 끊어야 실제로 서버가 산다. 한 건의 저장만 실패하고 서버는 계속 돈다.
    """
    if (
        request.method in ("POST", "PATCH", "PUT")
        and request.url.path.startswith(_SAVE_GUARD_PATHS)
        and request.headers.get("content-type", "").startswith("application/json")
    ):
        raw = request.headers.get("content-length") or ""
        limit = int(settings.MAX_CANVAS_SAVE_MB * 1024 * 1024)
        if raw.isdigit() and int(raw) > limit:
            size_mb = int(raw) / 1048576
            logging.getLogger(__name__).warning(
                "[save-guard] %s %s 거절 — %.1fMB > %.1fMB",
                request.method, request.url.path, size_mb, settings.MAX_CANVAS_SAVE_MB,
            )
            return JSONResponse(
                status_code=413,
                content={
                    "detail": (
                        f"저장 데이터가 너무 큽니다 ({size_mb:.1f}MB / 상한 "
                        f"{settings.MAX_CANVAS_SAVE_MB:.0f}MB). 사진이 캔버스에 파일째 "
                        "박혀 있을 수 있습니다. 사진을 지웠다 다시 넣어 주세요."
                    )
                },
            )
    return await call_next(request)


_allowed = [o.strip() for o in (settings.ALLOWED_ORIGINS or "").split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
