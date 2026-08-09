"""Bing image search scraper via Playwright (no API key required).

Navigates bing.com/images/search?q=<query>, extracts image candidates from
the .imgpt cards' `m` JSON attribute (murl/turl/w/h), and optionally
downloads the top N to a local directory.
"""

import asyncio
import json
import logging
import os
import re
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

import httpx

logger = logging.getLogger(__name__)

_SEARCH_URL = "https://www.bing.com/images/search?q={q}&form=HDRSC2&first=1"


async def search_bing_images(query: str, count: int = 10, timeout: int = 30) -> list[dict]:
    """Search Bing images for `query`. Returns up to `count` results.

    Each result: {source_url, thumbnail_url, width, height, host, title}.
    Does not download — call `download_images` separately.
    """
    from playwright.async_api import async_playwright, TimeoutError as PWTimeout

    url = _SEARCH_URL.format(q=quote_plus(query))
    results: list[dict] = []

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="ko-KR",
            viewport={"width": 1280, "height": 900},
        )
        page = await ctx.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=timeout * 1000)
            try:
                await page.wait_for_selector("a.iusc", timeout=timeout * 1000)
            except PWTimeout:
                logger.warning(f"[Bing] no results selector for query={query!r}")
                return []

            # Each <a class="iusc"> has an `m` attribute with JSON metadata.
            raw_meta: list[str] = await page.eval_on_selector_all(
                "a.iusc",
                "els => els.map(e => e.getAttribute('m')).filter(Boolean)",
            )
        finally:
            await browser.close()

    for meta_str in raw_meta:
        try:
            meta = json.loads(meta_str)
        except json.JSONDecodeError:
            continue
        murl = meta.get("murl") or ""
        if not murl:
            continue
        results.append({
            "source_url": murl,
            "thumbnail_url": meta.get("turl", ""),
            "width": int(meta.get("mw") or 0),
            "height": int(meta.get("mh") or 0),
            "host": meta.get("purl", ""),
            "title": meta.get("t", ""),
        })
        if len(results) >= count:
            break

    return results


_FNAME_SAFE = re.compile(r"[^a-zA-Z0-9._-]+")


def _ext_from_url(url: str, fallback: str = ".jpg") -> str:
    path = url.split("?")[0].split("#")[0]
    ext = os.path.splitext(path)[1].lower()
    if ext in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
        return ext
    return fallback


async def download_images(
    items: list[dict],
    out_dir: str | Path,
    timeout: int = 15,
    concurrency: int = 5,
) -> list[dict]:
    """Download `source_url` for each item to out_dir, fall back to thumbnail_url.

    Returns the items list with `local_path` populated (empty string if both failed).
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    sem = asyncio.Semaphore(concurrency)
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Referer": "https://www.bing.com/",
    }

    async with httpx.AsyncClient(timeout=timeout, headers=headers, follow_redirects=True) as client:
        async def fetch(idx: int, item: dict) -> dict:
            async with sem:
                for candidate in (item.get("source_url"), item.get("thumbnail_url")):
                    if not candidate:
                        continue
                    try:
                        resp = await client.get(candidate)
                        resp.raise_for_status()
                        ext = _ext_from_url(candidate)
                        fname = f"{idx:02d}{ext}"
                        path = out_dir / fname
                        path.write_bytes(resp.content)
                        item["local_path"] = str(path)
                        return item
                    except Exception as e:
                        logger.debug(f"[Bing] download fail idx={idx} url={candidate}: {e}")
                item["local_path"] = ""
                return item

        return await asyncio.gather(*(fetch(i, it) for i, it in enumerate(items)))


async def search_and_download(
    query: str,
    out_dir: str | Path,
    count: int = 10,
) -> list[dict]:
    """Convenience: search + download in one call."""
    items = await search_bing_images(query, count=count)
    if not items:
        return []
    return await download_images(items, out_dir=out_dir)
