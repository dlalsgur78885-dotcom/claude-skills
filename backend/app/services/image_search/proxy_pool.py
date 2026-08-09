"""Country-aware round-robin proxy rotation.

Config format (`SCRAPING_PROXY_URLS` in .env, semicolon-separated):
  SCRAPING_PROXY_URLS=jp:http://u:p@japan.proxy:6969;kr:http://u:p@korea.proxy:6969;default:http://u:p@global.proxy:6969

Each entry is `<country>:<proxy_url>` where country is ISO-2 code or "default".
Lookup: `next_proxy("jp")` returns next JP proxy → falls back to "default" pool
if no JP proxy configured. Empty config → None (direct connection).

Backwards-compatible: an entry without a `:` prefix is treated as default.
"""

from __future__ import annotations

import threading
from collections import defaultdict
from itertools import cycle
from typing import Iterator

from app.config import settings

_lock = threading.Lock()
_pools: dict[str, Iterator[str]] | None = None


def _build_pools() -> dict[str, Iterator[str]]:
    raw = (settings.SCRAPING_PROXY_URLS or "").strip()
    if not raw:
        return {}

    grouped: dict[str, list[str]] = defaultdict(list)
    for entry in raw.split(";"):
        entry = entry.strip()
        if not entry:
            continue
        # `country:url` — country is up to the FIRST colon; URL contains ":" too.
        if ":" in entry and not entry.startswith("http"):
            head, _, tail = entry.partition(":")
            country = head.strip().lower()
            url = tail.strip()
        else:
            country = "default"
            url = entry
        if url:
            grouped[country].append(url)

    return {country: cycle(urls) for country, urls in grouped.items()}


def next_proxy(country: str | None = None) -> str | None:
    """Pick the next proxy URL for the requested country, or fall back to 'default'."""
    global _pools
    with _lock:
        if _pools is None:
            _pools = _build_pools()
        if not _pools:
            return None
        cc = (country or "").lower().strip()
        # Try exact match → default pool → any pool
        for key in (cc, "default"):
            if key and key in _pools:
                return next(_pools[key])
        # No exact and no default — use first available pool
        first_key = next(iter(_pools))
        return next(_pools[first_key])
