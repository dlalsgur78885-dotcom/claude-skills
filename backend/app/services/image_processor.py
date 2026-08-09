"""Image processing service: multi-source image search, download, resize.

Photo priority:   Pexels → Pixabay → Unsplash → Naver → Bing
Icon priority:    Pixabay(illustration) → Flaticon
Background removal: rembg (local, unlimited)
"""

import logging
from pathlib import Path

import httpx
from PIL import Image

from app.config import settings

logger = logging.getLogger(__name__)

RAW_DIR = settings.DATA_DIR / "images" / "raw"
PROCESSED_DIR = settings.DATA_DIR / "images" / "processed"


class ImageProcessor:
    """Handles transparent image sourcing, downloading, and processing."""

    # ─── Transparent Image Sourcing (primary) ───

    async def search_transparent_stock(
        self, query: str, limit: int = 10
    ) -> dict:
        """Search Pixabay for transparent/cutout images.

        Uses colors=transparent to only get PNG images with alpha channel.
        Docs: https://pixabay.com/api/docs/
        """
        api_key = settings.PIXABAY_API_KEY
        if not api_key:
            return {"images": [], "error": "PIXABAY_API_KEY not set"}

        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://pixabay.com/api/",
                params={
                    "key": api_key,
                    "q": query,
                    "image_type": "illustration",
                    "colors": "transparent",
                    "per_page": min(limit, 200),
                    "safesearch": "true",
                },
                timeout=15,
            )
            response.raise_for_status()
            data = response.json()

        images = [
            {
                "id": hit["id"],
                "url": hit["largeImageURL"],
                "preview_url": hit["previewURL"],
                "width": hit["imageWidth"],
                "height": hit["imageHeight"],
                "tags": hit.get("tags", ""),
                "source": "pixabay",
                "has_transparency": True,
            }
            for hit in data.get("hits", [])
        ]

        return {"query": query, "total": data.get("totalHits", 0), "images": images}

    async def generate_transparent_image(
        self, prompt: str, size: str = "1024x1024", quality: str = "medium"
    ) -> dict:
        """Generate a transparent image using OpenAI GPT-Image API.

        Requires OPENAI_API_KEY. Outputs PNG with alpha channel.
        """
        api_key = settings.OPENAI_API_KEY
        if not api_key:
            return {"error": "OPENAI_API_KEY not set"}

        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.openai.com/v1/images/generations",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": "gpt-image-1",
                    "prompt": prompt,
                    "background": "transparent",
                    "output_format": "png",
                    "size": size,
                    "quality": quality,
                },
                timeout=60,
            )
            response.raise_for_status()
            data = response.json()

        image_data = data.get("data", [{}])[0]
        return {
            "url": image_data.get("url", ""),
            "revised_prompt": image_data.get("revised_prompt", ""),
            "source": "openai",
            "has_transparency": True,
        }

    async def search_icons(self, query: str, limit: int = 20) -> dict:
        """Search Flaticon for transparent icons/illustrations.

        All Flaticon icons are inherently transparent (SVG/PNG).
        """
        api_key = settings.FLATICON_API_KEY
        if not api_key:
            return {"icons": [], "error": "FLATICON_API_KEY not set"}

        async with httpx.AsyncClient() as client:
            # Get auth token first
            token_resp = await client.post(
                "https://api.flaticon.com/v3/app/authentication",
                headers={"Accept": "application/json"},
                json={"apikey": api_key},
                timeout=10,
            )
            token_resp.raise_for_status()
            token = token_resp.json().get("data", {}).get("token", "")

            # Search icons
            response = await client.get(
                "https://api.flaticon.com/v3/search/icons",
                headers={
                    "Accept": "application/json",
                    "Authorization": f"Bearer {token}",
                },
                params={"q": query, "limit": limit},
                timeout=15,
            )
            response.raise_for_status()
            data = response.json()

        icons = [
            {
                "id": icon["id"],
                "description": icon.get("description", ""),
                "url": icon.get("images", {}).get("png", {}).get("512", ""),
                "svg_url": icon.get("images", {}).get("svg", ""),
                "source": "flaticon",
                "has_transparency": True,
            }
            for icon in data.get("data", [])
        ]

        return {"query": query, "icons": icons}

    # ─── Smart Image Sourcing Pipeline ───

    async def find_cutout_images(
        self, query: str, limit: int = 10, generate_if_empty: bool = True
    ) -> dict:
        """Smart sourcing: try stock first, then AI-generate if needed.

        Priority:
        1. Pixabay transparent stock
        2. Flaticon icons (if query seems icon-like)
        3. OpenAI GPT-Image generation (if enabled)
        """
        results = []

        # 1. Try Pixabay transparent stock
        stock = await self.search_transparent_stock(query, limit)
        if stock.get("images"):
            results.extend(stock["images"])
            logger.info(f"Found {len(stock['images'])} transparent stock images for '{query}'")

        # 2. If not enough, try Flaticon
        if len(results) < limit:
            icons = await self.search_icons(query, limit - len(results))
            if icons.get("icons"):
                for icon in icons["icons"]:
                    if icon.get("url"):
                        results.append({
                            "url": icon["url"],
                            "source": "flaticon",
                            "has_transparency": True,
                            "tags": icon.get("description", ""),
                        })

        # 3. If still empty, AI-generate
        if not results and generate_if_empty:
            generated = await self.generate_transparent_image(
                f"high quality cutout of {query}, product photo style, clean edges"
            )
            if generated.get("url"):
                results.append({
                    "url": generated["url"],
                    "source": "openai_generated",
                    "has_transparency": True,
                })
                logger.info(f"AI-generated transparent image for '{query}'")

        return {
            "query": query,
            "total": len(results),
            "images": results[:limit],
        }

    # ─── Photo Search (Pexels, Unsplash, Naver, Bing) ───

    async def search_pexels(self, query: str, limit: int = 10) -> list[dict]:
        """Pexels API: 200회/시간 무료, 고품질 사진."""
        api_key = settings.PEXELS_API_KEY
        if not api_key:
            return []
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    "https://api.pexels.com/v1/search",
                    headers={"Authorization": api_key},
                    params={"query": query, "per_page": min(limit, 80), "locale": "ko-KR"},
                    timeout=15,
                )
                resp.raise_for_status()
                return [
                    {
                        "id": f"pexels_{p['id']}",
                        "url": p["src"]["large2x"],
                        "preview_url": p["src"]["medium"],
                        "width": p["width"],
                        "height": p["height"],
                        "source": "pexels",
                        "photographer": p.get("photographer", ""),
                    }
                    for p in resp.json().get("photos", [])
                ]
        except Exception as e:
            logger.warning(f"Pexels search failed: {e}")
            return []

    async def search_pixabay_photo(self, query: str, limit: int = 10) -> list[dict]:
        """Pixabay API: 무제한(100회/분), 사진 모드."""
        api_key = settings.PIXABAY_API_KEY
        if not api_key:
            return []
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    "https://pixabay.com/api/",
                    params={
                        "key": api_key, "q": query, "image_type": "photo",
                        "per_page": min(limit, 200), "safesearch": "true",
                    },
                    timeout=15,
                )
                resp.raise_for_status()
                return [
                    {
                        "id": f"pixabay_{h['id']}",
                        "url": h["largeImageURL"],
                        "preview_url": h["previewURL"],
                        "width": h["imageWidth"],
                        "height": h["imageHeight"],
                        "source": "pixabay",
                    }
                    for h in resp.json().get("hits", [])
                ]
        except Exception as e:
            logger.warning(f"Pixabay photo search failed: {e}")
            return []

    async def search_unsplash(self, query: str, limit: int = 10) -> list[dict]:
        """Unsplash API: 50회/시간 무료, 최고 품질."""
        api_key = settings.UNSPLASH_ACCESS_KEY
        if not api_key:
            return []
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    "https://api.unsplash.com/search/photos",
                    headers={"Authorization": f"Client-ID {api_key}"},
                    params={"query": query, "per_page": min(limit, 30)},
                    timeout=15,
                )
                resp.raise_for_status()
                return [
                    {
                        "id": f"unsplash_{r['id']}",
                        "url": r["urls"]["regular"],
                        "preview_url": r["urls"]["small"],
                        "width": r["width"],
                        "height": r["height"],
                        "source": "unsplash",
                        "photographer": r.get("user", {}).get("name", ""),
                    }
                    for r in resp.json().get("results", [])
                ]
        except Exception as e:
            logger.warning(f"Unsplash search failed: {e}")
            return []

    async def search_naver(self, query: str, limit: int = 10) -> list[dict]:
        """Naver Image Search API: 25,000회/일 무료. 한국 콘텐츠에 강함."""
        client_id = settings.NAVER_CLIENT_ID
        client_secret = settings.NAVER_CLIENT_SECRET
        if not client_id or not client_secret:
            return []
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    "https://openapi.naver.com/v1/search/image",
                    headers={
                        "X-Naver-Client-Id": client_id,
                        "X-Naver-Client-Secret": client_secret,
                    },
                    params={"query": query, "display": min(limit, 100), "sort": "sim", "filter": "large"},
                    timeout=15,
                )
                resp.raise_for_status()
                return [
                    {
                        "id": f"naver_{i}",
                        "url": item["link"],
                        "preview_url": item["thumbnail"],
                        "width": int(item.get("sizewidth", 0) or 0),
                        "height": int(item.get("sizeheight", 0) or 0),
                        "source": "naver",
                        "title": item.get("title", ""),
                    }
                    for i, item in enumerate(resp.json().get("items", []))
                ]
        except Exception as e:
            logger.warning(f"Naver search failed: {e}")
            return []

    async def search_bing(self, query: str, limit: int = 10) -> list[dict]:
        """Bing Image Search API: 1,000회/월 무료."""
        api_key = settings.BING_SEARCH_KEY
        if not api_key:
            return []
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    "https://api.bing.microsoft.com/v7.0/images/search",
                    headers={"Ocp-Apim-Subscription-Key": api_key},
                    params={"q": query, "count": min(limit, 150), "license": "ShareCommercially", "safeSearch": "Strict"},
                    timeout=15,
                )
                resp.raise_for_status()
                return [
                    {
                        "id": f"bing_{v.get('imageId', i)}",
                        "url": v["contentUrl"],
                        "preview_url": v["thumbnailUrl"],
                        "width": v.get("width", 0),
                        "height": v.get("height", 0),
                        "source": "bing",
                    }
                    for i, v in enumerate(resp.json().get("value", []))
                ]
        except Exception as e:
            logger.warning(f"Bing search failed: {e}")
            return []

    # ─── Unified Search ───

    async def search_photos(self, query: str, limit: int = 10) -> list[dict]:
        """모든 소스에서 사진 검색. 우선순위: Pexels → Pixabay → Unsplash → Naver → Bing."""
        results: list[dict] = []

        for searcher in [
            self.search_pexels,
            self.search_pixabay_photo,
            self.search_unsplash,
            self.search_naver,
            self.search_bing,
        ]:
            if len(results) >= limit:
                break
            found = await searcher(query, limit - len(results))
            results.extend(found)
            if found:
                logger.info(f"[{found[0]['source']}] {len(found)} images for '{query}'")

        return results[:limit]

    async def search_icons_all(self, query: str, limit: int = 10) -> list[dict]:
        """아이콘/일러스트 검색. 우선순위: Pixabay(illustration) → Flaticon."""
        results: list[dict] = []

        # Pixabay illustration
        stock = await self.search_transparent_stock(query, limit)
        results.extend(stock.get("images", []))

        # Flaticon
        if len(results) < limit:
            icons = await self.search_icons(query, limit - len(results))
            for icon in icons.get("icons", []):
                if icon.get("url"):
                    results.append({
                        "id": f"flaticon_{icon['id']}",
                        "url": icon["url"],
                        "preview_url": icon["url"],
                        "source": "flaticon",
                        "has_transparency": True,
                    })

        return results[:limit]

    async def search_by_style(
        self, query: str, style: str = "photo", limit: int = 10
    ) -> list[dict]:
        """style에 따라 적절한 소스에서 검색.

        style: "photo" | "icon" | "cutout"
        """
        if style == "icon":
            return await self.search_icons_all(query, limit)
        elif style == "cutout":
            result = await self.find_cutout_images(query, limit, generate_if_empty=False)
            return result.get("images", [])
        else:
            return await self.search_photos(query, limit)

    # ─── Download & Basic Processing ───

    async def download_images(self, post_id: int, image_urls: list[str]) -> dict:
        """Download images from URLs to local storage."""
        output_dir = RAW_DIR / str(post_id)
        output_dir.mkdir(parents=True, exist_ok=True)

        downloaded = []
        async with httpx.AsyncClient() as client:
            for i, url in enumerate(image_urls):
                try:
                    response = await client.get(url, timeout=30)
                    response.raise_for_status()

                    ext = "jpg"
                    content_type = response.headers.get("content-type", "")
                    if "png" in content_type:
                        ext = "png"
                    elif "webp" in content_type:
                        ext = "webp"

                    filepath = output_dir / f"slide_{i}.{ext}"
                    filepath.write_bytes(response.content)

                    with Image.open(filepath) as img:
                        w, h = img.size
                        has_alpha = img.mode in ("RGBA", "LA", "PA")

                    downloaded.append({
                        "path": str(filepath),
                        "slide_index": i,
                        "width": w,
                        "height": h,
                        "has_transparency": has_alpha,
                    })
                    logger.info(f"Downloaded slide {i} for post {post_id} (alpha={has_alpha})")
                except Exception as e:
                    logger.error(f"Failed to download image {i} for post {post_id}: {e}")

        return {
            "post_id": post_id,
            "total_urls": len(image_urls),
            "downloaded": len(downloaded),
            "files": downloaded,
        }

    async def download_transparent(self, query: str, output_dir: str | None = None) -> dict:
        """Find and download transparent images for a query."""
        sourced = await self.find_cutout_images(query, limit=5)
        if not sourced["images"]:
            return {"downloaded": 0, "files": []}

        urls = [img["url"] for img in sourced["images"] if img.get("url")]
        save_dir = Path(output_dir) if output_dir else PROCESSED_DIR / "sourced"
        save_dir.mkdir(parents=True, exist_ok=True)

        downloaded = []
        async with httpx.AsyncClient() as client:
            for i, url in enumerate(urls):
                try:
                    response = await client.get(url, timeout=30)
                    response.raise_for_status()
                    filepath = save_dir / f"{query.replace(' ', '_')}_{i}.png"
                    filepath.write_bytes(response.content)
                    downloaded.append({"path": str(filepath), "source_url": url})
                except Exception as e:
                    logger.error(f"Download failed for {url}: {e}")

        return {"query": query, "downloaded": len(downloaded), "files": downloaded}

    # ─── Background Removal (fallback only) ───

    async def remove_background(
        self, image_paths: list[str], output_format: str = "png"
    ) -> dict:
        """Remove background using rembg (LOCAL fallback).

        Only use when source images don't have transparency.
        """
        try:
            from rembg import remove
        except ImportError:
            logger.error("rembg not installed")
            return {"processed": [], "bg_removed_count": 0, "error": "rembg not installed"}

        results = []
        for path_str in image_paths:
            try:
                path = Path(path_str)
                with Image.open(path) as img:
                    # Skip if already transparent
                    if img.mode in ("RGBA", "LA", "PA"):
                        logger.info(f"Already transparent, skipping: {path.name}")
                        results.append({
                            "original": str(path),
                            "processed": str(path),
                            "width": img.width,
                            "height": img.height,
                            "skipped": True,
                        })
                        continue

                    output = remove(img)

                rel = path.relative_to(RAW_DIR) if RAW_DIR in path.parents else Path(path.name)
                out_path = PROCESSED_DIR / rel.with_suffix(f".{output_format}")
                out_path.parent.mkdir(parents=True, exist_ok=True)
                output.save(out_path)

                results.append({
                    "original": str(path),
                    "processed": str(out_path),
                    "width": output.width,
                    "height": output.height,
                })
                logger.info(f"Background removed: {path.name}")
            except Exception as e:
                logger.error(f"Background removal failed for {path_str}: {e}")

        return {
            "total_images": len(image_paths),
            "bg_removed_count": len([r for r in results if not r.get("skipped")]),
            "already_transparent": len([r for r in results if r.get("skipped")]),
            "processed": results,
        }

    async def resize_images(
        self,
        image_paths: list[str],
        max_width: int = 1080,
        max_height: int = 1350,
    ) -> dict:
        """Resize images to fit within max dimensions."""
        results = []
        for path_str in image_paths:
            try:
                path = Path(path_str)
                with Image.open(path) as img:
                    img.thumbnail((max_width, max_height), Image.LANCZOS)
                    img.save(path)
                    results.append({
                        "path": str(path),
                        "width": img.width,
                        "height": img.height,
                    })
            except Exception as e:
                logger.error(f"Resize failed for {path_str}: {e}")

        return {"resized_count": len(results), "files": results}

    async def download_and_process(self, post_ids: list[int]) -> dict:
        """Full pipeline for collected posts: download → check alpha → rembg if needed."""
        total_images = 0
        processed_count = 0
        bg_removed_count = 0
        already_transparent = 0

        # In real usage: look up image URLs from DB, download, check, process
        return {
            "post_ids": post_ids,
            "total_images": total_images,
            "processed_count": processed_count,
            "bg_removed_count": bg_removed_count,
            "already_transparent": already_transparent,
        }
