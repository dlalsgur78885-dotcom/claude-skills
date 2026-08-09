"""Alembic-driven schema bootstrap, called from `init_db()` on startup.

Three boot states, handled automatically — operator does not need to run
`alembic` manually unless they're authoring a new migration:

- **Fresh DB** (no tables): `alembic upgrade head` runs every migration in
  order, creating the schema from the baseline.
- **Existing DB, alembic-untracked** (legacy deploys that pre-date Alembic):
  `alembic stamp head` records the current revision without DDL — we assume
  the existing schema already matches HEAD because earlier boots applied the
  idempotent `_add_missing_columns` ALTERs that have since been folded into
  the baseline.
- **Existing DB, alembic-tracked**: `alembic upgrade head` applies any
  pending migrations (no-op when already at head).

Alembic's command API is sync — we run it via `asyncio.to_thread` so the
worker thread can spin its own event loop for the async aiosqlite engine
inside env.py without colliding with the FastAPI startup loop.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import text

from app.config import settings
from app.database import async_session

logger = logging.getLogger(__name__)


def _alembic_cfg() -> Config:
    """Build a Config that points at our backend/alembic dir regardless of cwd
    (uvicorn workers, cli scripts, tests can all start in different places).
    """
    backend_root = Path(__file__).resolve().parent.parent
    cfg = Config(str(backend_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend_root / "alembic"))
    cfg.set_main_option("sqlalchemy.url", settings.DATABASE_URL)
    return cfg


async def _has_table(name: str) -> bool:
    async with async_session() as s:
        row = await s.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name=:n"),
            {"n": name},
        )
        return row.first() is not None


async def bootstrap_schema() -> None:
    cfg = _alembic_cfg()
    has_version = await _has_table("alembic_version")
    has_users = await _has_table("users")

    if has_version:
        logger.info("[migrations] alembic_version present — upgrade head")
        await asyncio.to_thread(command.upgrade, cfg, "head")
    elif has_users:
        logger.info("[migrations] legacy DB without alembic_version — stamp head")
        await asyncio.to_thread(command.stamp, cfg, "head")
    else:
        logger.info("[migrations] fresh DB — upgrade head (creates schema)")
        await asyncio.to_thread(command.upgrade, cfg, "head")
