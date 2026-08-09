"""'쓸게요' pipeline: take a benchmark post → OCR + element extraction → Bing image pool.

Stages:
  1. download    — fetch slide images locally (skip if already on disk)
  2. analyze     — Gemini Vision: slide images + caption → slide texts + elements
  3. collect     — for each element: Bing image search + download N candidates
  4. done        — pipeline finished
  (failed)      — pipeline aborted, error stored on PostUsageJob
"""

import asyncio
import logging
import re
from datetime import datetime
from pathlib import Path

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.agents.llm_client import gemini_vision
from app.config import settings
from app.database import async_session
from app.models.element import ElementImagePool, ExtractedElement, PostUsageJob
from app.models.image import PostImage
from app.models.post import CollectedPost
from app.services.image_search import ImageResult, search_all

logger = logging.getLogger(__name__)

POOL_DIR = settings.DATA_DIR / "images" / "pool"
RAW_DIR = settings.DATA_DIR / "images" / "raw"

IMAGES_PER_ELEMENT = 10
ANALYZE_PROMPT = """\
당신은 인스타그램 카드뉴스 분석가입니다. 아래 캡션과 첨부된 슬라이드 이미지(순서대로)를 읽고
다음을 JSON으로만 출력하세요. 한국어 게시물입니다.

요구 출력 스키마:
{
  "slide_texts": ["슬라이드 1의 텍스트", "슬라이드 2의 텍스트", ...],
  "elements": [
    {
      "name": "요소 이름(짧은 명사구)",
      "search_query": "이미지 검색에 쓸 키워드(한국어 또는 영어, 1-3단어)",
      "source_text": "이 요소가 등장한 문구 일부"
    }
  ]
}

규칙:
- slide_texts: 슬라이드별 OCR 결과를 그대로 글자만 추출. 디자인 요소·이모지는 빼고 텍스트만.
- elements: 게시물에서 이미지로 표현하면 좋을 핵심 명사·주제만. 추상명사·접속사·꾸밈말 제외. 최대 8개.
- search_query는 이미지 검색(네이버/Unsplash/Pexels/Pixabay)에 그대로 넣을 문구. 너무 일반적이거나 너무 좁지 않게.
- 다른 설명 없이 JSON 하나만 출력.

캡션:
"""


_SLUG_RE = re.compile(r"[^a-zA-Z0-9가-힣_-]+")


def _slug(name: str, max_len: int = 40) -> str:
    s = _SLUG_RE.sub("_", name.strip()).strip("_")
    return s[:max_len] or "element"


def _ext_from_url(url: str) -> str:
    suffix = Path(url.split("?")[0].split("#")[0]).suffix.lower()
    return suffix if suffix in (".jpg", ".jpeg", ".png", ".webp", ".gif") else ".jpg"


_DL_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
}


async def _download_results(
    items: list[ImageResult],
    out_dir: Path,
    timeout: int = 15,
    concurrency: int = 5,
) -> list[tuple[ImageResult, str]]:
    """Download each result; returns (item, local_path) pairs. local_path='' on failure."""
    out_dir.mkdir(parents=True, exist_ok=True)
    sem = asyncio.Semaphore(concurrency)

    async with httpx.AsyncClient(
        timeout=timeout, headers=_DL_HEADERS, follow_redirects=True
    ) as client:
        async def fetch(idx: int, item: ImageResult) -> tuple[ImageResult, str]:
            async with sem:
                for url in (item.source_url, item.thumbnail_url):
                    if not url:
                        continue
                    try:
                        resp = await client.get(url)
                        resp.raise_for_status()
                        path = out_dir / f"{idx:02d}{_ext_from_url(url)}"
                        path.write_bytes(resp.content)
                        return item, str(path)
                    except Exception as e:
                        logger.debug(f"[image_pool] dl fail idx={idx} url={url}: {e}")
                return item, ""

        return await asyncio.gather(*(fetch(i, it) for i, it in enumerate(items)))


async def _download_slides_if_needed(
    db: AsyncSession,
    post: CollectedPost,
) -> list[str]:
    """Ensure slide images are on disk. Returns local FS paths in slide order.

    PostImage.raw_path may be:
      - an IG CDN URL (http…) → not yet downloaded
      - an /api/images/raw/{post_id}/{file} URL → already downloaded, served by API
      - a local filesystem path (legacy) → already downloaded
    After download, raw_path is rewritten to the /api/images/raw/... URL.
    """
    out_dir = RAW_DIR / str(post.id)
    out_dir.mkdir(parents=True, exist_ok=True)

    images = sorted(post.images, key=lambda i: i.slide_index)
    slide_paths: list[str] = []

    def _fs_for_api_url(url: str) -> Path | None:
        prefix = "/api/images/raw/"
        if not url.startswith(prefix):
            return None
        rest = url[len(prefix):]
        return RAW_DIR / rest

    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        for img in images:
            current = img.raw_path or ""

            api_fs = _fs_for_api_url(current)
            if api_fs and api_fs.exists():
                slide_paths.append(str(api_fs))
                continue

            if current and not current.startswith("http") and Path(current).exists():
                slide_paths.append(current)
                continue

            if not current.startswith("http"):
                logger.warning(f"[use_post] slide {img.slide_index} has no fetchable source")
                continue

            try:
                resp = await client.get(current)
                resp.raise_for_status()
                ext = ".jpg"
                ctype = resp.headers.get("content-type", "")
                if "png" in ctype:
                    ext = ".png"
                elif "webp" in ctype:
                    ext = ".webp"
                fname = f"slide_{img.slide_index}{ext}"
                fpath = out_dir / fname
                fpath.write_bytes(resp.content)
                img.raw_path = f"/api/images/raw/{post.id}/{fname}"
                slide_paths.append(str(fpath))
            except Exception as e:
                logger.error(f"[use_post] slide {img.slide_index} download failed: {e}")

    await db.commit()
    return slide_paths


async def _collect_for_element(element_id: int, query: str, post_id: int) -> int:
    """Multi-source search + download + quality score. Writes ElementImagePool rows."""
    from app.services.image_search.quality import assess_quality

    out_dir = POOL_DIR / str(post_id) / f"{element_id}_{_slug(query)}"
    results = await search_all(query, limit=IMAGES_PER_ELEMENT)
    if not results:
        return 0

    pairs = await _download_results(results, out_dir=out_dir)

    async def _score(item: ImageResult, path: str) -> tuple[ImageResult, str, float]:
        if not path:
            return item, path, 0.0
        score = await asyncio.to_thread(assess_quality, path)
        return item, path, score

    scored = await asyncio.gather(*(_score(it, lp) for it, lp in pairs))

    async with async_session() as db:
        for rank, (item, local_path, quality) in enumerate(scored):
            db.add(ElementImagePool(
                element_id=element_id,
                source_url=item.source_url,
                local_path=local_path,
                thumbnail_url=item.thumbnail_url,
                width=item.width,
                height=item.height,
                rank=rank,
                source=item.source,
                quality_score=quality,
            ))
        await db.commit()
    return len(scored)


async def run_analyze(post_id: int) -> None:
    """Stage 1: download slides + Gemini Vision analyze → save elements (selected=True).

    Pipeline pauses at status='awaiting_review'. Run run_collect() after the
    operator edits/selects elements.
    """
    async with async_session() as db:
        post_result = await db.execute(
            select(CollectedPost)
            .where(CollectedPost.id == post_id)
            .options(selectinload(CollectedPost.images))
        )
        post = post_result.scalar_one_or_none()
        if not post:
            logger.error(f"[use_post] post {post_id} not found")
            return

        job_result = await db.execute(
            select(PostUsageJob).where(PostUsageJob.post_id == post_id)
        )
        job = job_result.scalar_one_or_none()
        if not job:
            job = PostUsageJob(post_id=post_id, status="running", stage="download")
            db.add(job)
        else:
            job.status = "running"
            job.stage = "download"
            job.error = ""
            job.started_at = datetime.now()
            job.finished_at = None
        await db.commit()

        try:
            slide_paths = await _download_slides_if_needed(db, post)
            if not slide_paths:
                raise RuntimeError("슬라이드 이미지가 없습니다")

            job.stage = "analyze"
            await db.commit()

            analysis = await gemini_vision(
                image_paths=slide_paths,
                prompt=ANALYZE_PROMPT + (post.caption or ""),
                model="gemini-flash",
                json_mode=True,
            )
            if not isinstance(analysis, dict) or "elements" not in analysis:
                raise RuntimeError(f"Gemini Vision 응답 형식 오류: {analysis}")

            job.slide_texts = analysis.get("slide_texts", [])
            await db.commit()

            existing_elements = await db.execute(
                select(ExtractedElement).where(ExtractedElement.post_id == post_id)
            )
            for el in existing_elements.scalars().all():
                await db.delete(el)
            await db.commit()

            element_rows: list[ExtractedElement] = []
            for el in analysis.get("elements", []):
                row = ExtractedElement(
                    post_id=post_id,
                    name=str(el.get("name", "")).strip()[:255],
                    search_query=str(el.get("search_query") or el.get("name", "")).strip()[:500],
                    source_text=str(el.get("source_text", "")).strip()[:2000],
                    selected=True,
                )
                if not row.name:
                    continue
                db.add(row)
                element_rows.append(row)
            await db.commit()

            job.status = "awaiting_review"
            job.stage = "awaiting_review"
            await db.commit()
            logger.info(
                f"[use_post] post {post_id} analyzed → {len(element_rows)} elements (awaiting review)"
            )

        except Exception as e:
            logger.exception(f"[use_post] post {post_id} analyze failed")
            job.status = "failed"
            job.error = str(e)[:2000]
            job.finished_at = datetime.now()
            await db.commit()


async def run_collect(post_id: int) -> None:
    """Stage 2: collect images for elements where selected=True. Operator-triggered."""
    async with async_session() as db:
        job_result = await db.execute(
            select(PostUsageJob).where(PostUsageJob.post_id == post_id)
        )
        job = job_result.scalar_one_or_none()
        if not job:
            logger.error(f"[use_post] post {post_id}: no job")
            return
        job.status = "running"
        job.stage = "collect"
        job.error = ""
        job.finished_at = None
        await db.commit()

        try:
            el_result = await db.execute(
                select(ExtractedElement).where(
                    ExtractedElement.post_id == post_id,
                    ExtractedElement.selected.is_(True),
                )
            )
            elements = el_result.scalars().all()
            if not elements:
                raise RuntimeError("선택된 요소가 없습니다")

            await asyncio.gather(*[
                _collect_for_element(e.id, e.search_query, post_id) for e in elements
            ], return_exceptions=True)

            job.status = "done"
            job.stage = "done"
            job.finished_at = datetime.now()
            await db.commit()
            logger.info(f"[use_post] post {post_id} collected for {len(elements)} elements")

        except Exception as e:
            logger.exception(f"[use_post] post {post_id} collect failed")
            job.status = "failed"
            job.error = str(e)[:2000]
            job.finished_at = datetime.now()
            await db.commit()
