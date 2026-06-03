"""Image cutout service — remove the background from a real photo.

Two modes:
  - "standard"   → fal.ai BiRefNet (GPU, ~1-2s, ~$0.001/img) when FAL_KEY is set.
                   Falls back to local rembg (CPU, free, ~5-10s) otherwise.
                   Keeps hands/people that are part of the salient foreground —
                   good for clean product shots.
  - "generative" → Gemini image edit (nanobanana2, ~$0.04/img, ~10s).
                   Removes hands/extra people via prompt, leaves only the named
                   subject. Post-processed with rembg to guarantee an alpha
                   channel even if the generative model returned non-transparent.

Pipeline: source URL → fetch bytes → process → save PNG to data/images/cutouts.
"""

import asyncio
import base64
import hashlib
import logging
import time
from io import BytesIO
from pathlib import Path

import httpx
from PIL import Image

from app.config import settings

logger = logging.getLogger(__name__)

CUTOUT_DIR = settings.DATA_DIR / "images" / "cutouts"

# Default rembg model — best general-purpose accuracy for products and isolated
# subjects. Falls back through this chain if a model isn't downloadable.
_REMBG_CHAIN = ["isnet-general-use", "u2net"]

_GENERATIVE_PROMPT = (
    "Extract ONLY the primary product/subject from this photo. "
    "Remove everything else completely — background, hands holding it, people, "
    "fingers, props, surfaces, shadows. Keep the subject's exact appearance, "
    "colors, packaging text, and edges intact. Place the subject on a fully "
    "WHITE background — pure #FFFFFF, no shadow, no gradient. The subject must "
    "be cleanly cut from any hands or arms."
)

# Short noun-phrase prompt for evf-sam (text-grounded segmentation).
# evf-sam expects a description of WHAT to keep — not an instruction.
_EVF_SAM_PROMPT = "the main product or object, excluding any hand, fingers, person, or arms"


def _cache_key(source_url: str, mode: str, model: str) -> str:
    return hashlib.sha256(f"{source_url}|{mode}|{model}".encode()).hexdigest()[:16]


def _resize_for_upload(img_bytes: bytes, max_dim: int = 1024) -> bytes:
    """Shrink an image so its longer edge is <= max_dim, then JPEG-encode.

    Reduces upload payload and fal.ai inference time without meaningfully
    affecting cutout quality (rembg / BiRefNet output edges are already
    smoother than per-pixel detail).
    """
    try:
        with Image.open(BytesIO(img_bytes)) as img:
            w, h = img.size
            longest = max(w, h)
            if longest <= max_dim and img.mode == "RGB":
                return img_bytes  # already small + already RGB
            if longest > max_dim:
                scale = max_dim / longest
                img = img.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.LANCZOS)
            if img.mode != "RGB":
                img = img.convert("RGB")
            buf = BytesIO()
            img.save(buf, format="JPEG", quality=88)
            return buf.getvalue()
    except Exception as e:
        logger.warning(f"[cutout] resize failed, sending original: {e}")
        return img_bytes


def _extract_result_url(payload: dict) -> str | None:
    """Pull the result image URL out of a fal.ai response payload."""
    if isinstance(payload, dict):
        if isinstance(payload.get("image"), dict):
            return payload["image"].get("url")
        if isinstance(payload.get("images"), list) and payload["images"]:
            first = payload["images"][0]
            if isinstance(first, dict):
                return first.get("url")
    return None


async def _fal_post(endpoint: str, body: dict, fal_key: str) -> str:
    """Submit a fal.ai sync job and return the result image URL."""
    async with httpx.AsyncClient(timeout=60.0) as c:
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


async def _http_get_bytes(url: str) -> bytes:
    async with httpx.AsyncClient(timeout=30.0) as c:
        r = await c.get(url)
        r.raise_for_status()
        return r.content


def _rembg_bytes(img_bytes: bytes, model: str = "isnet-general-use") -> bytes:
    """Run rembg on raw image bytes, returning a transparent PNG."""
    from rembg import remove, new_session
    chain = [model] + [m for m in _REMBG_CHAIN if m != model]
    last_err: Exception | None = None
    for m in chain:
        try:
            session = new_session(m)
            with Image.open(BytesIO(img_bytes)) as img:
                out_img = remove(img, session=session)
            buf = BytesIO()
            out_img.save(buf, format="PNG")
            return buf.getvalue()
        except Exception as e:
            last_err = e
            logger.warning(f"[cutout/rembg] model {m} failed: {e}")
    raise RuntimeError(f"all rembg models failed: {last_err}")


def _data_uri(img_bytes: bytes) -> str:
    return f"data:image/jpeg;base64,{base64.b64encode(img_bytes).decode('ascii')}"


async def _fal_qwen_edit_url(image_input: str, prompt: str, fal_key: str) -> str:
    """Run fal.ai Qwen Image Edit. `image_input` can be a fal.run CDN URL OR a
    data:image/... URI. Returns the fal.ai result URL (no local download)."""
    return await _fal_post(
        "fal-ai/qwen-image-edit",
        {"prompt": prompt, "image_url": image_input},
        fal_key,
    )


async def _fal_birefnet_url(image_input: str, fal_key: str) -> str:
    """Run fal.ai BiRefNet on a CDN URL or data URI. Returns transparent PNG URL."""
    return await _fal_post(
        "fal-ai/birefnet",
        {"image_url": image_input},
        fal_key,
    )


async def _fal_evf_sam_mask_url(image_input: str, prompt: str, fal_key: str) -> str:
    """Run fal.ai EVF-SAM: text-grounded segmentation. Returns mask PNG URL.

    Measured ~3s on fal.ai. The mask is a single-channel PNG where white pixels
    mark the subject and black pixels mark everything to drop.
    """
    return await _fal_post(
        "fal-ai/evf-sam",
        {"image_url": image_input, "prompt": prompt},
        fal_key,
    )


def _apply_mask_rgba(src_bytes: bytes, mask_bytes: bytes) -> bytes:
    """Composite source image with a grayscale mask → transparent PNG.

    PNG is saved without `optimize=True` — that flag re-encodes the image to
    minimize file size at the cost of ~0.7-1.0s extra CPU per medium image,
    which dominated the cutout pipeline latency. The unoptimized PNG is ~30%
    larger but loads identically and the difference is invisible in practice.
    """
    with Image.open(BytesIO(src_bytes)) as src_img:
        src_rgba = src_img.convert("RGBA")
    with Image.open(BytesIO(mask_bytes)) as mask_img:
        mask_l = mask_img.convert("L")
        if mask_l.size != src_rgba.size:
            # BILINEAR is ~3x faster than LANCZOS and visually indistinguishable
            # at mask resolution.
            mask_l = mask_l.resize(src_rgba.size, Image.BILINEAR)
    src_rgba.putalpha(mask_l)
    buf = BytesIO()
    src_rgba.save(buf, format="PNG", compress_level=1)
    return buf.getvalue()


async def cutout_image(
    source_url: str,
    *,
    mode: str = "standard",
    model: str = "isnet-general-use",
) -> tuple[str, Path]:
    """Produce a transparent PNG from a source image URL.

    Returns (public_url, file_path). public_url is /api/images/cutouts/<file>.png
    so the existing static-file route serves it.
    """
    CUTOUT_DIR.mkdir(parents=True, exist_ok=True)

    cache_name = f"{_cache_key(source_url, mode, model)}.png"
    out_path = CUTOUT_DIR / cache_name
    if out_path.exists():
        public_url = f"/api/images/cutouts/{out_path.name}"
        logger.info(f"[cutout/{mode}] cache hit: {public_url}")
        return public_url, out_path

    if source_url.startswith("data:"):
        # Inline image (an uploaded photo, or a filtered fabric canvas whose
        # toDataURL() the editor sent). httpx.get() can't fetch a data: URI —
        # for a large one it raises "URL too long", which is exactly what broke
        # the editor's 누끼 button. Decode the base64/percent-encoded payload.
        import urllib.parse as _urlparse
        header, _, payload = source_url.partition(",")
        if ";base64" in header.lower():
            src_bytes = base64.b64decode(payload)
        else:
            src_bytes = _urlparse.unquote_to_bytes(payload)
    else:
        async with httpx.AsyncClient(
            timeout=30.0,
            headers={"User-Agent": "Mozilla/5.0", "Accept": "image/*"},
            follow_redirects=True,
        ) as c:
            r = await c.get(source_url)
            r.raise_for_status()
        src_bytes = r.content

    if mode == "generative":
        fal_key = (settings.FAL_KEY or "").strip()
        out_bytes = None
        if fal_key:
            try:
                # Strategy 1 — EVF-SAM (text-grounded segmentation). Single call,
                # outputs a binary mask we composite locally. ~3s + ~1s overhead.
                t0 = time.monotonic()
                small = _resize_for_upload(src_bytes, max_dim=1024)
                t_resize = time.monotonic() - t0
                src_uri = _data_uri(small)
                t1 = time.monotonic()
                mask_url = await _fal_evf_sam_mask_url(src_uri, _EVF_SAM_PROMPT, fal_key)
                t_evf = time.monotonic() - t1
                t2 = time.monotonic()
                mask_bytes = await _http_get_bytes(mask_url)
                t_dl = time.monotonic() - t2
                t3 = time.monotonic()
                out_bytes = _apply_mask_rgba(small, mask_bytes)
                t_compose = time.monotonic() - t3
                logger.info(
                    "[cutout/generative] evf-sam OK | resize=%.2fs evf=%.2fs mask_dl=%.2fs compose=%.2fs total=%.2fs",
                    t_resize, t_evf, t_dl, t_compose, time.monotonic() - t0,
                )
            except Exception as e:
                logger.warning(f"[cutout/generative] evf-sam failed, trying qwen+BiRefNet: {e}")
        if out_bytes is None and fal_key:
            try:
                # Strategy 2 — Qwen edit + BiRefNet. Slower but a different
                # failure mode (handles cases evf-sam can't ground textually).
                t0 = time.monotonic()
                small = _resize_for_upload(src_bytes, max_dim=1024)
                qwen_url = await _fal_qwen_edit_url(_data_uri(small), _GENERATIVE_PROMPT, fal_key)
                t_qwen = time.monotonic() - t0
                t1 = time.monotonic()
                bg_url = await _fal_birefnet_url(qwen_url, fal_key)
                t_birefnet = time.monotonic() - t1
                t2 = time.monotonic()
                out_bytes = await _http_get_bytes(bg_url)
                t_dl = time.monotonic() - t2
                logger.info(
                    "[cutout/generative] qwen+BiRefNet OK | qwen=%.2fs birefnet=%.2fs dl=%.2fs total=%.2fs",
                    t_qwen, t_birefnet, t_dl, time.monotonic() - t0,
                )
            except Exception as e:
                logger.warning(f"[cutout/generative] qwen chain also failed, falling back: {e}")
        # Fallback: nanobanana2 via Gemini + local rembg (slower).
        if out_bytes is None:
            try:
                from app.agents.llm_client import gemini_image_edit
            except ImportError as e:
                raise RuntimeError("no generative cutout backend available") from e
            src_hash = hashlib.sha256(src_bytes).hexdigest()[:16]
            tmp_path = CUTOUT_DIR / f"_src_{src_hash}.jpg"
            tmp_path.write_bytes(src_bytes)
            try:
                gen_bytes = await gemini_image_edit([str(tmp_path)], _GENERATIVE_PROMPT, model="nanobanana2")
            finally:
                try:
                    tmp_path.unlink()
                except OSError:
                    pass
            out_bytes = await asyncio.to_thread(_rembg_bytes, gen_bytes, model=model)
    elif mode == "standard":
        fal_key = (settings.FAL_KEY or "").strip()
        out_bytes = None
        if fal_key:
            try:
                t0 = time.monotonic()
                small = _resize_for_upload(src_bytes, max_dim=1024)
                t_resize = time.monotonic() - t0
                t1 = time.monotonic()
                bg_url = await _fal_birefnet_url(_data_uri(small), fal_key)
                t_api = time.monotonic() - t1
                t2 = time.monotonic()
                out_bytes = await _http_get_bytes(bg_url)
                t_dl = time.monotonic() - t2
                logger.info(
                    "[cutout/standard] BiRefNet OK | resize=%.2fs api=%.2fs dl=%.2fs total=%.2fs",
                    t_resize, t_api, t_dl, time.monotonic() - t0,
                )
            except Exception as e:
                logger.warning(f"[cutout/standard] fal.ai failed, falling back to rembg: {e}")
        if out_bytes is None:
            try:
                import rembg  # noqa: F401
            except ImportError as e:
                raise RuntimeError(
                    "rembg not installed and fal.ai failed/unavailable"
                ) from e
            out_bytes = await asyncio.to_thread(_rembg_bytes, src_bytes, model=model)
    else:
        raise ValueError(f"unknown cutout mode: {mode!r} (expected 'standard' or 'generative')")

    out_path.write_bytes(out_bytes)
    public_url = f"/api/images/cutouts/{out_path.name}"
    logger.info(f"[cutout/{mode}] {source_url[:60]}... → {public_url} ({len(out_bytes)//1024}KB)")
    return public_url, out_path
