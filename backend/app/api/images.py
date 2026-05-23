"""Image serving & search endpoints."""

import hashlib
import ipaddress
import logging
import mimetypes
import socket
from dataclasses import asdict
from pathlib import Path
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, Response

from app.config import settings
from app.api.auth import get_current_user
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/images", tags=["images"])

_PROXY_MAX_BYTES = 20 * 1024 * 1024  # 20MB hard cap

# Permanent on-disk cache for the /proxy endpoint. Naver blog images, in
# particular, frequently 404 days after the carousel was created (CDN
# expiration / blog post deletion). Once we successfully fetched an image,
# the cached copy keeps it alive forever.
_PROXY_CACHE_DIR = settings.DATA_DIR / "images" / "proxy_cache"
_PROXY_CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _check_host(host: str) -> tuple[bool, str]:
    """Block proxy from reaching private/loopback addresses (SSRF guard).

    Returns (ok, reason). reason explains DNS failure vs private IP separately.
    """
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return False, "도메인을 찾을 수 없습니다 (DNS 실패)"
    for info in infos:
        addr = info[4][0]
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            continue
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            return False, "내부 IP는 차단됩니다"
    return True, ""


def _referer_for(host: str) -> str:
    """Pick a host-appropriate Referer so hotlink-blocking CDNs accept us."""
    h = host.lower()
    if "naver.net" in h or "naver.com" in h:
        return "https://blog.naver.com/"
    if "gnst.jp" in h or "livejapan.com" in h:
        return "https://livejapan.com/"
    if "namu.wiki" in h:
        return "https://namu.wiki/"
    if "pinimg.com" in h or "pinterest" in h:
        return "https://www.pinterest.com/"
    if "instagram" in h or "cdninstagram" in h:
        return "https://www.instagram.com/"
    # Default: pretend the request originated from the image's own site
    return f"https://{host}/"


@router.get("/proxy")
async def proxy_external_image(url: str = Query(..., min_length=8)):
    """Fetch an external image and re-serve it with CORS allowed.

    Used by the canvas editor to load arbitrary CDN images without tainting
    the canvas (so PNG export still works). SSRF-safe: rejects private IPs.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise HTTPException(status_code=400, detail="http/https 만 허용됩니다")
    host = parsed.hostname or ""
    if not host:
        raise HTTPException(status_code=400, detail="호스트가 없습니다")
    ok, reason = _check_host(host)
    if not ok:
        raise HTTPException(status_code=400, detail=f"{host}: {reason}")

    # Disk cache lookup — survives both /tmp scheduler cleanups AND external 404s
    cache_key = hashlib.sha1(url.encode("utf-8")).hexdigest()
    cached_files = list(_PROXY_CACHE_DIR.glob(f"{cache_key}.*"))
    if cached_files:
        cached = cached_files[0]
        media_type = mimetypes.guess_type(cached.name)[0] or "image/jpeg"
        return Response(
            content=cached.read_bytes(),
            media_type=media_type,
            headers={
                "Access-Control-Allow-Origin": "*",
                "Cache-Control": "public, max-age=86400",
                "X-Proxy-Source": "cache",
            },
        )

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
        "Accept-Language": "ko,en-US;q=0.9,en;q=0.8",
        # Many CDNs (naver, live-japan) hotlink-block missing/foreign referers.
        "Referer": _referer_for(host),
    }
    try:
        async with httpx.AsyncClient(timeout=15, headers=headers, follow_redirects=True) as c:
            r = await c.get(url)
        r.raise_for_status()
    except httpx.HTTPError as e:
        logger.warning(f"[proxy] fetch failed for {url}: {e}")
        raise HTTPException(status_code=502, detail=f"이미지 가져오기 실패: {e}")

    if len(r.content) > _PROXY_MAX_BYTES:
        raise HTTPException(status_code=413, detail="이미지가 너무 큽니다 (>20MB)")

    media_type = r.headers.get("content-type") or "image/jpeg"
    if not media_type.lower().startswith("image/"):
        raise HTTPException(status_code=415, detail=f"이미지가 아닙니다 ({media_type})")

    # Persist to cache so a future 404 from the origin doesn't kill the editor view
    ext = mimetypes.guess_extension(media_type.split(";")[0].strip()) or ".jpg"
    try:
        (_PROXY_CACHE_DIR / f"{cache_key}{ext}").write_bytes(r.content)
    except Exception as e:
        logger.warning(f"[proxy] cache write failed: {e}")

    return Response(
        content=r.content,
        media_type=media_type,
        headers={
            "Access-Control-Allow-Origin": "*",
            "Cache-Control": "public, max-age=86400",
            "X-Proxy-Source": "origin",
        },
    )


@router.get("/raw/{post_id}/{filename}")
async def serve_raw_image(post_id: int, filename: str):
    path = settings.DATA_DIR / "images" / "raw" / str(post_id) / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="이미지를 찾을 수 없습니다")
    return FileResponse(path)


@router.get("/processed/{post_id}/{filename}")
async def serve_processed_image(post_id: int, filename: str):
    path = settings.DATA_DIR / "images" / "processed" / str(post_id) / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="이미지를 찾을 수 없습니다")
    return FileResponse(path)


@router.get("/output/{carousel_id}/{filename}")
async def serve_output_image(carousel_id: int, filename: str):
    path = settings.DATA_DIR / "images" / "output" / str(carousel_id) / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="이미지를 찾을 수 없습니다")
    return FileResponse(path)


@router.get("/pool/{post_id}/{element_dir}/{filename}")
async def serve_pool_image(post_id: int, element_dir: str, filename: str):
    path = settings.DATA_DIR / "images" / "pool" / str(post_id) / element_dir / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="이미지를 찾을 수 없습니다")
    return FileResponse(path)


@router.get("/restyled/{filename}")
async def serve_restyled_image(filename: str):
    path = settings.DATA_DIR / "images" / "restyled" / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="이미지를 찾을 수 없습니다")
    return FileResponse(path)


@router.get("/cutouts/{filename}")
async def serve_cutout_image(filename: str):
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="bad path")
    path = settings.DATA_DIR / "images" / "cutouts" / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="이미지를 찾을 수 없습니다")
    return FileResponse(path)


@router.get("/enhanced/{filename}")
async def serve_enhanced_image(filename: str):
    """Serve an AI-upscaled image produced by /api/images/enhance."""
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="bad path")
    path = settings.DATA_DIR / "images" / "enhanced" / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="이미지를 찾을 수 없습니다")
    return FileResponse(path)


@router.get("/logos/{filename}")
async def serve_logo(filename: str):
    path = settings.DATA_DIR / "images" / "logos" / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="로고를 찾을 수 없습니다")
    return FileResponse(path)


@router.get("/cta/{user_id}/{filename}")
async def serve_cta_image(user_id: str, filename: str):
    """Serve a user's registered CTA image (uploaded via /api/cta/upload)."""
    if not user_id.isdigit() or "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="bad path")
    path = settings.DATA_DIR / "images" / "cta" / user_id / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="CTA 이미지를 찾을 수 없습니다")
    return FileResponse(path)


@router.get("/template-source/{slug}/{filename}")
async def serve_template_source_slide(slug: str, filename: str):
    """Serve cached source-post slide image used during template generation."""
    # path traversal guard
    if "/" in slug or "\\" in slug or "/" in filename or "\\" in filename or ".." in slug or ".." in filename:
        raise HTTPException(status_code=400, detail="bad path")
    path = settings.DATA_DIR / "template_studio_cache" / slug / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="원본 슬라이드를 찾을 수 없습니다")
    return FileResponse(path)


@router.get("/template-assets/{user_id}/{filename}")
async def serve_template_asset(user_id: str, filename: str):
    """Serve a decoration asset uploaded via /templates/upload-asset.

    Read-only: anyone with the URL can fetch it (the final-render pipeline
    needs to load these without auth). Privacy here is by URL obscurity (token-hex
    filename); template assets aren't sensitive secrets.
    """
    if not user_id.isdigit() or "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="bad path")
    path = settings.DATA_DIR / "images" / "template_assets" / user_id / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="에셋을 찾을 수 없습니다")
    return FileResponse(path)


class RestyleRequest(BaseModel):
    source_url: str
    user_prompt: str = ""
    brand_color: str | None = None
    brand_mood: str = ""
    model: str = "nanobanana2"


@router.post("/restyle")
async def restyle_image_endpoint(
    body: RestyleRequest,
    user: User = Depends(get_current_user),
):
    """Re-render a real photo in a brand style via nanobanana2 (image-to-image)."""
    from app.services.image_restyle import restyle_image
    try:
        public_url, _path = await restyle_image(
            body.source_url,
            user_prompt=body.user_prompt,
            brand_color=body.brand_color,
            brand_mood=body.brand_mood,
            model=body.model,
        )
    except Exception as e:
        logger.exception("restyle failed")
        raise HTTPException(status_code=502, detail=f"스타일 변환 실패: {e}")
    return {"url": public_url}


class EnhanceRequest(BaseModel):
    source_url: str
    category: str = "landscape"  # food | landscape | portrait


@router.post("/enhance")
async def enhance_image_endpoint(
    body: EnhanceRequest,
    user: User = Depends(get_current_user),
):
    """Run an AI super-resolution / detail-enhance pass on a canvas image.

    Category-tuned: landscape uses aura-sr (clean SR, no hallucination);
    food and portrait use clarity-upscaler with category-specific prompts.
    Returns the new public URL — the caller replaces the canvas image src.
    """
    from app.services.image_enhance import enhance_image
    try:
        public_url, _path = await enhance_image(body.source_url, body.category)
    except RuntimeError as e:
        # FAL_KEY missing or upstream returned no URL — surface as 502 so the
        # frontend shows a useful message instead of a generic 500.
        logger.warning(f"enhance failed: {e}")
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        logger.exception("enhance failed")
        raise HTTPException(status_code=502, detail=f"화질 향상 실패: {e}")
    return {"url": public_url}


class CutoutRequest(BaseModel):
    source_url: str
    mode: str = "standard"  # "standard" (rembg) | "generative" (nanobanana2 + rembg)
    model: str = "isnet-general-use"


@router.post("/cutout")
async def cutout_image_endpoint(
    body: CutoutRequest,
    user: User = Depends(get_current_user),
):
    """Produce a transparent PNG cutout of the source image.

    mode="standard" runs local rembg (free, ~5s). Keeps hands/people that are
    part of the salient foreground.

    mode="generative" runs Gemini image edit with a "extract product only"
    prompt (~10s, ~$0.04). Removes hands holding the product and any extra
    elements. Falls back to rembg post-processing to guarantee an alpha channel.
    """
    from app.services.image_cutout import cutout_image
    if body.mode not in ("standard", "generative"):
        raise HTTPException(status_code=400, detail="mode must be standard or generative")
    try:
        public_url, _path = await cutout_image(
            body.source_url, mode=body.mode, model=body.model
        )
    except Exception as e:
        logger.exception("cutout failed")
        raise HTTPException(status_code=502, detail=f"누끼 제거 실패: {e}")
    return {"url": public_url}


@router.get("/search")
async def search_images(
    q: str = Query(..., min_length=1),
    style: str = Query("photo", regex="^(photo|icon|cutout)$"),
    source: str | None = Query(None, description="bing|naver|wikimedia (style=photo only)"),
    limit: int = Query(12, le=50),
    country: str | None = Query(None, description="ISO-2 country code — routes through that country's proxy"),
    user: User = Depends(get_current_user),
):
    """이미지 검색.

    - style=photo: 멀티소스 엔진. source 미지정 시 폴백 체인(bing→naver→wikimedia).
      Carousel studio feedback #15-16: stock photo provider 3종은 제거 (캐러셀
      대상이 특정 가게·장소·아이템이라 stock 매칭률이 낮음). bing 잡식 + naver
      한국어 블로그 + wikimedia 랜드마크 큐레이션이 실용적.
    - style=icon|cutout: 기존 ImageProcessor (Pixabay illustration / Flaticon).
    """
    if style == "photo":
        from app.services.image_search import PROVIDERS, search_all

        if source:
            if source not in PROVIDERS:
                raise HTTPException(400, f"unknown source: {source}. choose from {list(PROVIDERS)}")
            results = await PROVIDERS[source].safe_search(q, limit, country=country)
        else:
            results = await search_all(q, limit=limit, country=country)

        # Map ImageResult → frontend contract (id/url/preview_url)
        images = [
            {
                "id": f"{r.source}-{i}",
                "source": r.source,
                "url": r.source_url,
                "preview_url": r.thumbnail_url or r.source_url,
                "width": r.width,
                "height": r.height,
                "title": r.title,
                "has_transparency": r.has_transparency,
            }
            for i, r in enumerate(results)
        ]
        return {
            "query": q,
            "style": style,
            "source": source or "all",
            "total": len(images),
            "images": images,
        }

    from app.services.image_processor import ImageProcessor
    processor = ImageProcessor()
    results = await processor.search_by_style(q, style, limit)
    return {"query": q, "style": style, "total": len(results), "images": results}
