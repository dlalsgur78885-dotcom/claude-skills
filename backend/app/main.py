"""FastAPI application entry point."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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
        import logging
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
