"""Resolve runtime settings — DB-stored values take precedence over env vars.

Admin can update API keys etc. through /api/settings without restarting the
server or editing the .env file.

Reads are cached in-process (TTL 30s) so each LLM call doesn't hit the DB.
"""

from __future__ import annotations

import asyncio
import os
import time

from sqlalchemy import select

from app.config import settings as env_settings
from app.database import async_session
from app.models.app_setting import AppSetting

# Settings the UI exposes to admin. Order matters for the form layout.
EDITABLE_KEYS: list[str] = [
    "GEMINI_API_KEY",
    "ANTHROPIC_API_KEY",
    "HIKER_API_KEY",
    "FAL_KEY",
    "PEXELS_API_KEY",
    "PIXABAY_API_KEY",
    "UNSPLASH_ACCESS_KEY",
    "OPENAI_API_KEY",
    "SCRAPING_PROXY_URLS",
]

_cache: dict[str, str] = {}
_cache_ts: float = 0.0
_TTL = 30.0
_lock = asyncio.Lock()


async def _load_from_db() -> dict[str, str]:
    async with async_session() as session:
        result = await session.execute(select(AppSetting))
        rows = result.scalars().all()
        return {r.key: r.value for r in rows if r.value}


async def get_setting(key: str, default: str = "") -> str:
    """Return DB-stored value, or env-var fallback, or empty string."""
    global _cache, _cache_ts
    async with _lock:
        now = time.time()
        if now - _cache_ts > _TTL:
            try:
                _cache = await _load_from_db()
            except Exception:
                pass
            _cache_ts = now

    if key in _cache and _cache[key]:
        return _cache[key]
    env_val = getattr(env_settings, key, None) or os.environ.get(key) or default
    return env_val or ""


def get_setting_sync_envonly(key: str, default: str = "") -> str:
    """Sync fallback — env var only. Use when DB is not available."""
    env_val = getattr(env_settings, key, None) or os.environ.get(key) or default
    return env_val or ""


async def invalidate_cache() -> None:
    """Force the next get_setting call to refetch from DB. Call after /settings PUT."""
    global _cache_ts
    async with _lock:
        _cache_ts = 0.0


async def apply_to_environ() -> None:
    """Push DB-stored secrets to os.environ so libraries that read os.environ
    directly (litellm, google-genai) pick up the latest values.

    Called at startup and after each /settings PUT.
    """
    db_vals = await _load_from_db()
    for key in EDITABLE_KEYS:
        v = db_vals.get(key)
        if v:
            os.environ[key] = v


async def list_settings_for_admin() -> dict[str, dict]:
    """Return all editable keys with: current value (masked for secrets), source."""
    db_vals = await _load_from_db()
    out: dict[str, dict] = {}
    for key in EDITABLE_KEYS:
        if key in db_vals and db_vals[key]:
            value = db_vals[key]
            source = "db"
        else:
            value = getattr(env_settings, key, "") or os.environ.get(key, "")
            source = "env" if value else "missing"
        out[key] = {
            "value": value,
            "source": source,
            # Don't return raw secrets — surface a masked preview only.
            "preview": _mask(value) if value else "",
        }
    return out


def _mask(s: str) -> str:
    if len(s) <= 8:
        return "*" * len(s)
    return s[:4] + "*" * (len(s) - 8) + s[-4:]
