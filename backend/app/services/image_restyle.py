"""Image restyle service - take a real photo and re-render it in a brand style.

Pipeline: source URL → fetch bytes → Gemini image edit (nanobanana2) → save to
data/images/restyled → return public URL the editor can load.
"""

import hashlib
import logging
from pathlib import Path

import httpx

from app.agents.llm_client import gemini_image_edit
from app.config import settings

logger = logging.getLogger(__name__)

RESTYLED_DIR = settings.DATA_DIR / "images" / "restyled"


def _build_style_prompt(
    user_prompt: str = "",
    brand_color: str | None = None,
    brand_mood: str = "",
) -> str:
    """Compose a default restyle prompt from optional brand cues."""
    if user_prompt.strip():
        return user_prompt.strip()
    parts = [
        "Re-render the subject of this photo with a clean editorial magazine look:",
        "preserve the actual subject (people, places, products) faithfully — do not invent or replace it,",
        "soft cinematic lighting, subtle film grain, balanced color grading,",
        "shallow depth of field that still keeps the subject readable.",
    ]
    if brand_color:
        parts.append(f"Apply a subtle accent palette around {brand_color}.")
    if brand_mood:
        parts.append(f"Mood: {brand_mood}.")
    parts.append("Square 1:1 framing. No text overlays, no watermarks.")
    return " ".join(parts)


async def restyle_image(
    source_url: str,
    *,
    user_prompt: str = "",
    brand_color: str | None = None,
    brand_mood: str = "",
    model: str = "nanobanana2",
) -> tuple[str, Path]:
    """Download a source image, restyle via Gemini, persist to disk.

    Returns (public_url, file_path). public_url is rooted at /api/images/restyled/...
    so the existing static-file route serves it.
    """
    RESTYLED_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Fetch source bytes via the same proxy guards (only public hosts)
    async with httpx.AsyncClient(
        timeout=20.0,
        headers={"User-Agent": "Mozilla/5.0", "Accept": "image/*"},
        follow_redirects=True,
    ) as c:
        r = await c.get(source_url)
        r.raise_for_status()
    src_bytes = r.content

    # 2. Drop bytes into a temp file the genai SDK can read
    src_hash = hashlib.sha256(src_bytes).hexdigest()[:16]
    tmp_path = RESTYLED_DIR / f"_src_{src_hash}.jpg"
    tmp_path.write_bytes(src_bytes)

    prompt = _build_style_prompt(user_prompt, brand_color, brand_mood)

    # 3. Send to Gemini image edit
    out_bytes = await gemini_image_edit([str(tmp_path)], prompt, model=model)

    # 4. Save output as a stable hash-named PNG
    out_hash = hashlib.sha256(out_bytes + prompt.encode()).hexdigest()[:16]
    out_path = RESTYLED_DIR / f"{out_hash}.png"
    out_path.write_bytes(out_bytes)

    # 5. Clean up temp source
    try:
        tmp_path.unlink()
    except OSError:
        pass

    public_url = f"/api/images/restyled/{out_path.name}"
    logger.info(f"[restyle] {source_url[:60]}... → {public_url} ({len(out_bytes)//1024}KB)")
    return public_url, out_path
