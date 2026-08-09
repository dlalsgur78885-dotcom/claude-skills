"""AI image enhancement via fal.ai.

Three category-tuned pipelines exposed to the editor:

  - landscape  → fal-ai/aura-sr (pure 4x super-resolution, no prompt, no
                 hallucinated detail — safest for natural scenery)
  - food       → fal-ai/clarity-upscaler (prompt-guided, emphasises texture
                 and saturation — bumps food shots that are technically OK
                 but look flat)
  - portrait   → fal-ai/clarity-upscaler with skin/face-oriented prompt
                 (avoids over-sharpening artefacts on faces)

Result is downloaded into data/images/enhanced/ so the editor can reload it
via the same `/api/images/enhanced/<hash>.png` route used for restyled and
cutout outputs. No DB writes — the URL itself is the only handle.
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

ENHANCED_DIR = settings.DATA_DIR / "images" / "enhanced"


_CATEGORY_PROMPTS = {
    "food": (
        "Sharp food photography, vibrant natural colors, crisp surface texture, "
        "appetizing detail. Keep the original composition and lighting."
    ),
    "portrait": (
        "Natural skin texture, sharp facial features, clean detail, "
        "no over-smoothing. Preserve the original framing and expression."
    ),
    # landscape uses aura-sr (no prompt) — kept here for symmetry / fallback.
    "landscape": "",
}


def _extract_result_url(payload: dict) -> str | None:
    """fal.ai SR/upscale endpoints return either `image.url` or `images[0].url`."""
    if isinstance(payload, dict):
        img = payload.get("image")
        if isinstance(img, dict) and isinstance(img.get("url"), str):
            return img["url"]
        imgs = payload.get("images")
        if isinstance(imgs, list) and imgs:
            first = imgs[0]
            if isinstance(first, dict) and isinstance(first.get("url"), str):
                return first["url"]
    return None


async def _fal_post(endpoint: str, body: dict, fal_key: str, *, timeout: float = 120.0) -> str:
    async with httpx.AsyncClient(timeout=timeout) as c:
        r = await c.post(
            f"https://fal.run/{endpoint}",
            headers={"Authorization": f"Key {fal_key}", "Content-Type": "application/json"},
            json=body,
        )
        r.raise_for_status()
        payload = r.json()
    url = _extract_result_url(payload)
    if not url:
        raise RuntimeError(f"{endpoint} returned no image URL: {str(payload)[:200]}")
    return url


async def _download(url: str) -> bytes:
    async with httpx.AsyncClient(
        timeout=60.0,
        follow_redirects=True,
        headers={"User-Agent": "Mozilla/5.0", "Accept": "image/*"},
    ) as c:
        r = await c.get(url)
        r.raise_for_status()
        return r.content


async def enhance_image(source_url: str, category: str) -> tuple[str, Path]:
    """Run the AI upscale that matches `category` and persist the result.

    Returns (public_url, file_path). public_url is rooted at
    /api/images/enhanced/<hash>.png so the existing static route serves it.
    Raises RuntimeError when FAL_KEY isn't configured or the upstream fails.
    """
    fal_key = (settings.FAL_KEY or "").strip()
    if not fal_key:
        raise RuntimeError("FAL_KEY is not configured")

    cat = (category or "landscape").lower()
    if cat not in _CATEGORY_PROMPTS:
        cat = "landscape"

    ENHANCED_DIR.mkdir(parents=True, exist_ok=True)

    # Resolve source URL. If the caller passed our own /api/images/... path,
    # fal.ai can't fetch it (private host) — we have to read it from disk and
    # post the bytes inline as a data URI. For external URLs (Pexels/Pixabay/
    # Naver), forward the URL directly so fal pulls it from the CDN.
    if source_url.startswith("/api/"):
        # Pull from local disk via httpx loopback. The backend container can
        # always reach itself at 127.0.0.1:8000 — and going through the route
        # keeps the path-resolution rules in one place.
        local_url = f"http://127.0.0.1:8000{source_url}"
        src_bytes = await _download(local_url)
        import base64
        image_input = "data:image/png;base64," + base64.b64encode(src_bytes).decode("ascii")
    else:
        image_input = source_url

    if cat == "landscape":
        # aura-sr: pure 4x SR, no prompt, no creative drift.
        result_url = await _fal_post(
            "fal-ai/aura-sr",
            {"image_url": image_input, "upscaling_factor": 4},
            fal_key,
        )
    else:
        # clarity-upscaler: prompt-guided detail enhancement (food / portrait).
        result_url = await _fal_post(
            "fal-ai/clarity-upscaler",
            {
                "image_url": image_input,
                "prompt": _CATEGORY_PROMPTS[cat],
                "upscale_factor": 2,
                "creativity": 0.35,
                "resemblance": 0.6,
            },
            fal_key,
        )

    out_bytes = await _download(result_url)
    out_hash = hashlib.sha256(out_bytes + cat.encode()).hexdigest()[:16]
    out_path = ENHANCED_DIR / f"{out_hash}.png"
    out_path.write_bytes(out_bytes)

    public_url = f"/api/images/enhanced/{out_path.name}"
    logger.info("[enhance/%s] %s → %s (%d bytes)", cat, source_url[:80], public_url, len(out_bytes))
    return public_url, out_path
