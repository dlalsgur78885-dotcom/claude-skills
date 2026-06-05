"""Carousel management and orchestrator endpoints."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

from app.database import get_db
from app.models.user import User
from app.models.carousel import GeneratedCarousel, CarouselStatus
from app.models.post import CollectedPost
from app.schemas.carousel import (
    CarouselCreate,
    CarouselListItem,
    CarouselUpdate,
    CarouselResponse,
    OrchestratorRequest,
    OrchestratorResponse,
)
from app.api.auth import get_current_user
from app.agents.orchestrator import Orchestrator


async def _hydrate_source_url(carousel: GeneratedCarousel, db: AsyncSession) -> CarouselResponse:
    """Build a CarouselResponse with `source_post_url` joined in.

    The model deliberately doesn't carry a SQLAlchemy relationship to
    CollectedPost (carousels survive after the source row gets soft-deleted),
    so we look the URL up on demand. Returns None for the field when the
    source post no longer exists or the carousel was created from scratch.
    """
    source_url: str | None = None
    if carousel.source_post_id is not None:
        post = await db.execute(
            select(CollectedPost.post_url).where(CollectedPost.id == carousel.source_post_id)
        )
        source_url = post.scalar_one_or_none()
    base = CarouselResponse.model_validate(carousel)
    base.source_post_url = source_url
    return base

router = APIRouter(prefix="/carousels", tags=["carousels"])


def _carousel_list_item(carousel: GeneratedCarousel) -> CarouselListItem:
    canvas_data = carousel.canvas_data or {}
    slides = canvas_data.get("canvas_slides") if isinstance(canvas_data, dict) else None
    thumbnail_url: str | None = None
    if isinstance(slides, list) and slides:
        first = slides[0]
        objects = first.get("objects") if isinstance(first, dict) else None
        if isinstance(objects, list):
            for obj in objects:
                if not isinstance(obj, dict):
                    continue
                obj_type = str(obj.get("type") or "").lower()
                if obj_type in {"image", "fabricimage"} and obj.get("src"):
                    thumbnail_url = str(obj["src"])
                    break

    return CarouselListItem(
        id=carousel.id,
        user_id=carousel.user_id,
        source_post_id=carousel.source_post_id,
        title=carousel.title,
        template_id=carousel.template_id,
        status=str(getattr(carousel.status, "value", carousel.status)),
        created_at=carousel.created_at,
        updated_at=carousel.updated_at,
        slide_count=len(slides) if isinstance(slides, list) else 0,
        thumbnail_url=thumbnail_url,
    )


@router.get("/", response_model=list[CarouselListItem])
async def list_carousels(
    limit: int = Query(20, le=100),
    offset: int = Query(0),
    status: str | None = Query(None, description="draft | editing | finalized"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(GeneratedCarousel)
        .where(GeneratedCarousel.user_id == user.id)
        .order_by(GeneratedCarousel.updated_at.desc())
        .limit(limit)
        .offset(offset)
    )
    if status:
        # SQLAlchemy Enum column stores the string value; filter by exact match.
        stmt = stmt.where(GeneratedCarousel.status == status)
    result = await db.execute(stmt)
    return [_carousel_list_item(carousel) for carousel in result.scalars().all()]


@router.post("/", response_model=CarouselResponse, status_code=201)
async def create_carousel(
    data: CarouselCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    carousel = GeneratedCarousel(
        user_id=user.id,
        title=data.title,
        source_post_id=data.source_post_id,
        template_id=data.template_id,
        canvas_data=data.canvas_data,
    )
    db.add(carousel)
    await db.commit()
    await db.refresh(carousel)
    return carousel


@router.get("/{carousel_id}", response_model=CarouselResponse)
async def get_carousel(
    carousel_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(GeneratedCarousel).where(
            GeneratedCarousel.id == carousel_id,
            GeneratedCarousel.user_id == user.id,
        )
    )
    carousel = result.scalar_one_or_none()
    if not carousel:
        raise HTTPException(status_code=404, detail="캐러셀을 찾을 수 없습니다")
    return await _hydrate_source_url(carousel, db)


@router.patch("/{carousel_id}", response_model=CarouselResponse)
async def update_carousel(
    carousel_id: int,
    data: CarouselUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(GeneratedCarousel).where(
            GeneratedCarousel.id == carousel_id,
            GeneratedCarousel.user_id == user.id,
        )
    )
    carousel = result.scalar_one_or_none()
    if not carousel:
        raise HTTPException(status_code=404, detail="캐러셀을 찾을 수 없습니다")

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(carousel, field, value)

    await db.commit()
    await db.refresh(carousel)
    return carousel


@router.delete("/{carousel_id}", status_code=204)
async def delete_carousel(
    carousel_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(GeneratedCarousel).where(
            GeneratedCarousel.id == carousel_id,
            GeneratedCarousel.user_id == user.id,
        )
    )
    carousel = result.scalar_one_or_none()
    if not carousel:
        raise HTTPException(status_code=404, detail="캐러셀을 찾을 수 없습니다")

    await db.delete(carousel)
    await db.commit()


@router.post("/{carousel_id}/clone", response_model=CarouselResponse, status_code=201)
async def clone_carousel(
    carousel_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Duplicate a carousel — canvas_data is deep-copied so edits on the copy
    don't bleed into the original. Status resets to `draft` and the title gets
    a "(복제)" suffix so it sorts beside the source in the user's works list.
    """
    result = await db.execute(
        select(GeneratedCarousel).where(
            GeneratedCarousel.id == carousel_id,
            GeneratedCarousel.user_id == user.id,
        )
    )
    src = result.scalar_one_or_none()
    if not src:
        raise HTTPException(status_code=404, detail="캐러셀을 찾을 수 없습니다")

    import copy

    cloned = GeneratedCarousel(
        user_id=src.user_id,
        source_post_id=src.source_post_id,
        title=f"{src.title or '제목 없음'} (복제)",
        canvas_data=copy.deepcopy(src.canvas_data or {}),
        template_id=src.template_id,
        status=CarouselStatus.DRAFT,
    )
    db.add(cloned)
    await db.commit()
    await db.refresh(cloned)
    return cloned


@router.post("/analyze-post")
async def analyze_post(
    data: dict,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """포스트의 모든 이미지 OCR + 캡션 분석."""
    import asyncio
    from app.models.post import CollectedPost
    from sqlalchemy.orm import selectinload
    from pathlib import Path
    import easyocr
    import logging

    logger = logging.getLogger(__name__)

    post_id = data.get("post_id")
    if not post_id:
        raise HTTPException(status_code=400, detail="post_id 필요")

    result = await db.execute(
        select(CollectedPost)
        .where(CollectedPost.id == post_id)
        .options(selectinload(CollectedPost.images))
    )
    post = result.scalar_one_or_none()
    if not post:
        raise HTTPException(status_code=404, detail="포스트를 찾을 수 없습니다")

    # Build (slide_index, local_path) work list first so the heavy OCR batch
    # can be offloaded to a worker thread in one shot — keeps the event loop
    # free for other requests during the multi-second easyocr work.
    sorted_imgs = sorted(post.images, key=lambda x: x.slide_index)
    work: list[tuple[int, str, Path | None]] = []
    for img in sorted_imgs:
        raw_path = img.raw_path
        if raw_path.startswith("/api/images/raw/"):
            parts = raw_path.replace("/api/images/raw/", "").split("/")
            local_path = Path("data/images/raw") / parts[0] / parts[1]
        else:
            local_path = Path(raw_path)
        work.append((img.slide_index, raw_path, local_path if local_path.exists() else None))

    def _ocr_batch(items: list[tuple[int, str, Path | None]]) -> list[list[str]]:
        # easyocr.Reader is not documented thread-safe — run sequentially
        # inside this single worker thread. Model load is one-time per Reader.
        reader = easyocr.Reader(["ko", "en"], gpu=False, verbose=False)
        out: list[list[str]] = []
        for _idx, _rp, lp in items:
            if lp is None:
                out.append([])
                continue
            try:
                results = reader.readtext(str(lp))
                out.append([text for _, text, conf in results if conf > 0.3])
            except Exception as e:
                logger.warning(f"OCR failed for {lp}: {e}")
                out.append([])
        return out

    ocr_results = await asyncio.to_thread(_ocr_batch, work)

    slides_analysis = []
    for (slide_index, raw_path, _lp), ocr_texts in zip(work, ocr_results):
        slides_analysis.append({
            "slide_index": slide_index,
            "image_path": raw_path,
            "ocr_texts": ocr_texts,
            "ocr_full": " ".join(ocr_texts),
        })

    return {
        "post_id": post.id,
        "post_url": post.post_url,
        "caption": post.caption,
        "hashtags": post.hashtags,
        "like_count": post.like_count,
        "comment_count": post.comment_count,
        "slide_count": post.slide_count,
        "slides": slides_analysis,
        "summary": {
            "total_slides": len(slides_analysis),
            "slides_with_text": len([s for s in slides_analysis if s["ocr_texts"]]),
            "all_ocr_text": " | ".join([s["ocr_full"] for s in slides_analysis if s["ocr_full"]]),
        },
    }


@router.post("/render")
async def render_carousel_endpoint(
    data: dict,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Apply a template to a list of blueprint slides and return Fabric.js canvas slides.

    Body: {
      template_id: int,                  # CarouselTemplate row id (or null → minimal default)
      slides: list[{type, headline, body, subtext?, items?, index}],
      brand_color: str | null,           # channel/user override
      brand_logo_path: str | null,
      user_image_urls: { [slide_index]: url },  # picked in Step 2
    }
    Returns: { canvas_slides: [...] }
    """
    from app.services.carousel_renderer import render_carousel
    from app.models.template import CarouselTemplate

    template_id = data.get("template_id")
    slides = data.get("slides") or []
    if not slides:
        raise HTTPException(status_code=400, detail="slides가 비어 있습니다")

    template = None
    if template_id:
        template = await db.get(CarouselTemplate, template_id)
        # Render is read-only — any authenticated user can apply any template.
        # Edits/deletes are gated separately on /api/templates/{id} PATCH/DELETE.

    if not template:
        raise HTTPException(status_code=400, detail="유효한 template_id가 필요합니다")

    brand_overrides = {
        "primary_color": data.get("brand_color"),
        "logo_path": data.get("brand_logo_path"),
    }
    user_image_urls = {int(k): v for k, v in (data.get("user_image_urls") or {}).items() if v}
    raw_item = data.get("user_item_image_urls") or {}
    user_item_image_urls: dict[int, dict[int, str]] = {}
    for sk, cells in raw_item.items():
        if not isinstance(cells, dict):
            continue
        try:
            sidx = int(sk)
        except (TypeError, ValueError):
            continue
        inner: dict[int, str] = {}
        for ck, url in cells.items():
            if not url:
                continue
            try:
                inner[int(ck)] = url
            except (TypeError, ValueError):
                continue
        if inner:
            user_item_image_urls[sidx] = inner

    # Per-slide layout override: user can pin a specific layout from the template
    # instead of letting the auto-picker decide. Validated against the template's
    # actual layouts in the renderer (unknown names fall back to auto-pick).
    raw_layout_overrides = data.get("layout_overrides") or {}
    layout_overrides: dict[int, str] = {}
    for sk, ln in raw_layout_overrides.items():
        if not ln:
            continue
        try:
            layout_overrides[int(sk)] = str(ln)
        except (TypeError, ValueError):
            continue

    canvas_slides = await render_carousel(
        template_canvas=template.canvas or {},
        template_brand=template.brand or {},
        template_layouts=template.layouts or {},
        slides=slides,
        brand_overrides=brand_overrides,
        user_image_urls=user_image_urls,
        user_item_image_urls=user_item_image_urls,
        layout_overrides=layout_overrides,
        skip_background_images=bool(data.get("skip_background_images")),
    )
    return {"canvas_slides": canvas_slides, "template_id": template.id, "template_slug": template.slug}


def _template_has_multicell(layouts: dict) -> bool:
    """True if any layout renders more than one image cell — a regular grid
    (rows×cols > 1) or the irregular per-cell pattern. A template with no
    multi-cell layout is one-subject-per-slide; the Vision extractor is then
    told not to split slides into items."""
    for layout in (layouts or {}).values():
        if not isinstance(layout, dict):
            continue
        grid = layout.get("grid")
        if isinstance(grid, dict):
            if (int(grid.get("rows") or 1) * int(grid.get("cols") or 1)) > 1:
                return True
        for slot in layout.get("text_slots") or []:
            if "cell_" in str(slot.get("role") or ""):
                return True
    return False


_BODY_TEXT_ROLES = {"body", "description", "caption", "subheadline", "subtitle"}


def _layout_has_body_slot(layout: dict) -> bool:
    """True if the layout has a text slot that renders a slide's body/subtext."""
    if not isinstance(layout, dict):
        return False
    for slot in (layout.get("text_slots") or []):
        if str(slot.get("role") or "").lower() in _BODY_TEXT_ROLES:
            return True
    return False


def _pick_typed_layout(layouts: dict, prefs: list[str]) -> dict | None:
    """Find the layout a slide type renders with — mirrors carousel_renderer
    _pick_layout's name preference, falling back to the first layout."""
    for name in prefs:
        if isinstance((layouts or {}).get(name), dict):
            return layouts[name]
    for layout in (layouts or {}).values():
        if isinstance(layout, dict):
            return layout
    return None


@router.post("/generate-content")
async def generate_content(
    data: dict,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """주제, 인스타그램 URL, 또는 기존 레퍼런스 포스트 기반으로 콘텐츠 생성."""
    from app.services.content_gen import ContentGenerator
    from app.services.content_extractor import extract_slides_from_post_images
    from app.services.post_ingest import ingest_post_by_url_via_hiker
    from app.services.template_studio import get_template
    from app.models.post import CollectedPost
    from sqlalchemy.orm import selectinload

    topic = data.get("topic", "")
    tone = data.get("tone", "professional")
    slide_count = data.get("slide_count", 8)
    ref_ids = list(data.get("ref_ids", []))
    post_urls = data.get("post_urls") or []
    template_id = data.get("template_id")

    # URL이 들어오면 HikerAPI로 자동 수집 → ref_ids에 추가
    ingested_for_extraction: list[CollectedPost] = []
    for url in post_urls:
        url = (url or "").strip()
        if not url:
            continue
        try:
            ingested = await ingest_post_by_url_via_hiker(url, user.id, db)
            if ingested.id not in ref_ids:
                ref_ids.append(ingested.id)
            # Always try vision extraction for an explicitly-passed URL, even if
            # the post was previously ingested and is already in ref_ids — the
            # user is asking for *this URL's* content, not a generic re-mix of
            # the ref-set.
            ingested_for_extraction.append(ingested)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"URL 수집 실패 ({url}): {e}")

    # When the user kicks off generation from /posts ("이 게시물 쓸게요" →
    # /create?refs=...) the frontend only sends ref_ids — no post_urls. The
    # vision branch below keys off ingested_for_extraction, so without this
    # fallback that flow falls through to content_gen.generate_slides() with
    # an empty topic and the LLM hallucinates a generic carousel
    # ("성공적인 카드뉴스" etc.) instead of using the benchmark's actual
    # slides. Load the referenced posts directly so vision extraction runs.
    if not ingested_for_extraction and ref_ids:
        existing_rows = await db.execute(
            select(CollectedPost).where(CollectedPost.id.in_(ref_ids))
        )
        for post in existing_rows.scalars().all():
            ingested_for_extraction.append(post)

    # URL을 통해 들어온 새 포스트가 있고 사용자가 명시적 주제를 안 줬으면
    # → Vision으로 슬라이드 본문을 직접 추출 (LLM 재생성이 아닌 원본 그대로)
    if ingested_for_extraction and not topic.strip():
        first = ingested_for_extraction[0]
        # 슬라이드 이미지 URL 모아서 Vision에 전달
        img_rows = await db.execute(
            select(CollectedPost)
            .where(CollectedPost.id == first.id)
            .options(selectinload(CollectedPost.images))
        )
        post_with_imgs = img_rows.scalar_one_or_none()
        image_urls = (
            [im.raw_path for im in (post_with_imgs.images or [])]
            if post_with_imgs else []
        )
        # When the user picked a template, profile its layouts: a template with
        # no multi-cell layout is one-subject-per-slide, so Vision is told not to
        # split slides into items (the "▶지역/▶날짜 → 2칸" over-split bug).
        template_profile = None
        if template_id:
            try:
                tpl = await get_template(db, int(template_id), user.id)
                if tpl and tpl.layouts:
                    layouts = tpl.layouts
                    cover_layout = _pick_typed_layout(
                        layouts, ["photo_with_caption", "fullbg_overlay", "single_image", "text_only"]
                    )
                    cta_layout = _pick_typed_layout(
                        layouts,
                        ["phone_mockup", "fullbg_overlay", "photo_with_caption", "single_image", "text_only"],
                    )
                    template_profile = {
                        "single_content": not _template_has_multicell(layouts),
                        # cover/cta whose template layout has no body slot must be
                        # extracted title-only — else the cover gets a description
                        # the template can't render.
                        "cover_headline_only": cover_layout is not None and not _layout_has_body_slot(cover_layout),
                        "cta_headline_only": cta_layout is not None and not _layout_has_body_slot(cta_layout),
                    }
            except Exception:
                logger.warning("[generate-content] template profile load failed", exc_info=True)
        try:
            extracted = await extract_slides_from_post_images(
                image_urls,
                cache_key=f"post_{first.id}_{first.instagram_post_id}",
                template_profile=template_profile,
            )
        except Exception as e:
            logger.exception("Vision content extraction failed")
            extracted = []

        if extracted:
            def _clean(s: str) -> str:
                # collapse newlines/multiple spaces; image search APIs don't allow them
                return " ".join((s or "").split()).strip()

            extracted_topic = _clean(extracted[0].get("headline") or first.caption[:60])

            # Translate each headline into multiple search-query variants:
            #   - native language of the subject (e.g. 도쿄 공원 → "代々木公園")
            #   - English for stock-photo APIs
            #   - original Korean as last fallback
            # Image search tries them in priority order.
            # For GRID slides (with `items[]`), translate every item's title
            # individually so each cell can be searched separately. For non-grid
            # slides, fall back to the slide headline.
            slide_descs: list[tuple[str, str]] = []
            for s in extracted:
                if s.get("type") not in ("cover", "content"):
                    continue
                body = _clean(s.get("body") or "")
                items = s.get("items") or []
                if items:
                    for it in items:
                        t = _clean((it.get("title") if isinstance(it, dict) else "") or "")
                        if not t:
                            continue
                        sub = _clean((it.get("subtitle") if isinstance(it, dict) else "") or "")
                        desc = _clean((it.get("description") if isinstance(it, dict) else "") or "")
                        item_body = " ".join(x for x in (sub, desc) if x)[:120]
                        slide_descs.append((t, item_body or body))
                else:
                    head = _clean(s.get("headline") or "")
                    if not head:
                        continue
                    slide_descs.append((head, body))

            ko_terms = [h for h, _ in slide_descs]
            keyword_variants: dict[str, dict[str, str]] = {}
            if ko_terms:
                try:
                    # Use API path directly — CLI doesn't reliably handle JSON output
                    from app.agents.llm_client import _call_api
                    import json as _json
                    # Pass the cover headline as topic context so the LLM can carry the city across slides
                    cover_topic = extracted_topic
                    desc_lines = []
                    for i, (h, b) in enumerate(slide_descs):
                        b_short = (b or "")[:120]
                        desc_lines.append(f'  {i+1}. "{h}"' + (f' — body: "{b_short}"' if b_short else ""))

                    prompt = (
                        f"Topic context: {cover_topic!r}\n\n"
                        "Build search queries (3 language variants) for each slide.\n\n"
                        "HARD RULES (every single query MUST satisfy these):\n"
                        "1. **City name is REQUIRED only when the subject is location-bound** "
                        "— places/shops/restaurants/cafes/landmarks/parks/streets/neighborhoods. "
                        "Skip the city for portable products (snacks, packaged goods, cosmetics, "
                        "books, gadgets) — those are sold globally and the city would only hurt "
                        "image-search precision. When in doubt, include the city.\n"
                        "2. If the headline is a brand/shop/person/proper noun, KEEP IT VERBATIM. "
                        "Do not replace it with a generic description — surround it with category "
                        "(and city if location-bound).\n"
                        "3. Brand names are NOT translated. KINJI stays KINJI in Korean, English, AND Japanese.\n\n"
                        "Output for each slide:\n"
                        '  "ko":      Korean query — 3-6 words. Include city in 한글 only for places.\n'
                        '  "en":      English equivalent (lowercase non-brand parts).\n'
                        '  "native":  Subject country\'s native script '
                        "(Japanese 漢字 for Japan, French for France, …). For products, "
                        "the brand/product name in native script is enough.\n"
                        '  "country": ISO 3166-1 alpha-2 (jp, fr, kr, us, …).\n\n'
                        "Examples:\n"
                        '  Place — Topic "도쿄 공원 8곳", "요요기 공원":\n'
                        '    {"ko": "도쿄 요요기 공원", "en": "tokyo yoyogi park", "native": "東京 代々木公園", "country": "jp"}\n'
                        '  Place — Topic "도쿄 빈티지샵 7곳", "KINJI" body "하라주쿠 데님":\n'
                        '    {"ko": "하라주쿠 KINJI 빈티지샵", "en": "harajuku KINJI vintage store", "native": "原宿 KINJI 古着屋", "country": "jp"}\n'
                        '  Product — Topic "일본 간식 베스트", "롯데 파이노미":\n'
                        '    {"ko": "롯데 파이노미 초콜릿 파이", "en": "lotte pie no mi chocolate pie", "native": "ロッテ パイの実", "country": "jp"}\n'
                        '  Product — Topic "일본 간식 베스트", "메이지 다케노코노사토":\n'
                        '    {"ko": "메이지 다케노코노사토 초콜릿", "en": "meiji takenoko no sato chocolate", "native": "明治 たけのこの里", "country": "jp"}\n'
                        '  Place — Topic "파리 카페 5곳", "Café de Flore":\n'
                        '    {"ko": "파리 Café de Flore 생제르맹", "en": "paris Café de Flore saint-germain", "native": "Paris Café de Flore Saint-Germain", "country": "fr"}\n\n'
                        "Output ONLY a JSON array, one per slide IN ORDER, with the headline as \"input\":\n"
                        '  [{"input": "...", "ko": "...", "en": "...", "native": "...", "country": "..."}, ...]\n\n'
                        f"Exactly {len(slide_descs)} items, matching:\n"
                        + "\n".join(desc_lines)
                    )
                    raw = await _call_api(
                        "gemini/gemini-2.5-flash",
                        [{"role": "user", "content": prompt}],
                        json_mode=True,
                        max_tokens=2048,
                    )
                    try:
                        res = _json.loads(raw)
                    except Exception:
                        # Strip markdown fences if any
                        cleaned = raw.strip()
                        if cleaned.startswith("```"):
                            cleaned = cleaned.split("```")[1]
                            if cleaned.startswith("json"):
                                cleaned = cleaned[4:]
                        res = _json.loads(cleaned.strip())
                    # LLM may return either {phrase: {en, native, country}} or [{en, native, country}, ...]
                    pairs: list[tuple[str, dict]] = []
                    if isinstance(res, dict):
                        # Sometimes wrapped: {translations: [...]}
                        for key in ("translations", "results", "data"):
                            if key in res and isinstance(res[key], list):
                                res = res[key]
                                break
                    if isinstance(res, list):
                        # Match response items to input phrases by their "input" field if present,
                        # otherwise fall back to positional index.
                        ko_set = {t: t for t in ko_terms}
                        for i, item in enumerate(res):
                            if not isinstance(item, dict):
                                continue
                            input_key = str(item.get("input") or "").strip()
                            if input_key and input_key in ko_set:
                                pairs.append((input_key, item))
                            elif i < len(ko_terms):
                                pairs.append((ko_terms[i], item))
                    elif isinstance(res, dict):
                        for k, v in res.items():
                            if isinstance(v, dict):
                                pairs.append((str(k), v))

                    for ko, v in pairs:
                        native = str(v.get("native") or "").strip()
                        en = str(v.get("en") or "").strip()
                        ko_desc = str(v.get("ko") or "").strip()  # Korean descriptive (for Naver)
                        country = str(v.get("country") or "").strip().lower()
                        if country == "kr":
                            native = ""
                        keyword_variants[ko] = {
                            "en": en,
                            "native": native,
                            "ko_desc": ko_desc,
                            "country": country,
                        }
                except Exception as e:
                    logger.exception(f"[generate-content] keyword translation failed: {e}")

            def _build_keywords(ko: str) -> tuple[list[str], str]:
                v = keyword_variants.get(ko, {})
                native = v.get("native") or ""
                en = v.get("en") or ""
                ko_desc = v.get("ko_desc") or ""
                country = (v.get("country") or "").lower() or "kr"
                seen, out = set(), []
                for k in (ko_desc, native, en, ko):
                    k = (k or "").strip()
                    if k and k.lower() not in seen:
                        seen.add(k.lower())
                        out.append(k)
                return out, country

            image_keywords = []
            for s in extracted:
                idx = s.get("index", 0)
                stype = s.get("type", "content")
                items = s.get("items") or []
                # Grid slides: one keyword per cell, using item.title
                if items and stype in ("cover", "content"):
                    for j, it in enumerate(items):
                        title = _clean((it.get("title") if isinstance(it, dict) else "") or "")
                        ko = title or _clean(s.get("headline") or "") or extracted_topic
                        keys, country = _build_keywords(ko)
                        image_keywords.append({
                            "slide_index": idx,
                            "item_index": j,
                            "keywords": keys,
                            "style": "photo",
                            "country": country,
                        })
                    continue
                # Single-content slides: one keyword for the whole slide
                if stype == "cover":
                    ko = _clean(extracted_topic)
                    keys, country = _build_keywords(ko)
                    image_keywords.append({"slide_index": idx, "item_index": None, "keywords": keys, "style": "photo", "country": country})
                elif stype == "content":
                    ko = _clean(s.get("headline") or "") or extracted_topic
                    keys, country = _build_keywords(ko)
                    image_keywords.append({"slide_index": idx, "item_index": None, "keywords": keys, "style": "photo", "country": country})

            # 캡션은 원본 그대로, 해시태그는 원본 해시태그 사용
            return {
                "topic": extracted_topic,
                "slides": extracted,
                "caption": first.caption or "",
                "hashtags": first.hashtags or [],
                "image_keywords": image_keywords,
                "ref_posts": [{
                    "id": first.id,
                    "caption": (first.caption or "")[:80],
                    "post_url": first.post_url,
                    "like_count": first.like_count,
                    "comment_count": first.comment_count,
                    "slide_count": first.slide_count,
                    "thumbnail": image_urls[0] if image_urls else None,
                }],
                "ref_images": [
                    {"post_id": first.id, "slide_index": i, "url": u, "caption": (first.caption or "")[:60]}
                    for i, u in enumerate(image_urls[:20])
                ],
                "extraction_mode": "vision",
            }
        # Vision 실패하면 아래의 LLM 재생성 흐름으로 폴백

    # 레퍼런스 포스트가 있으면 분석
    ref_posts = []
    if ref_ids:
        result = await db.execute(
            select(CollectedPost)
            .where(CollectedPost.id.in_(ref_ids))
            .options(selectinload(CollectedPost.images))
            .order_by(CollectedPost.like_count.desc())
        )
        ref_posts = result.scalars().all()

    # 레퍼런스에서 주제/톤/슬라이드 수 추출
    if ref_posts and not topic:
        # 캡션에서 주제 추출
        captions = [p.caption for p in ref_posts if p.caption]
        all_hashtags = []
        for p in ref_posts:
            all_hashtags.extend(p.hashtags or [])
        topic = ", ".join(all_hashtags[:5]) if all_hashtags else (captions[0][:50] if captions else "")
        # 평균 슬라이드 수
        avg_slides = round(sum(p.slide_count for p in ref_posts) / len(ref_posts))
        slide_count = max(5, min(avg_slides, 10))

    gen = ContentGenerator()

    # 레퍼런스가 있으면 분석 정보를 프롬프트에 포함
    if ref_posts:
        ref_context = "\n".join([
            f"- 좋아요 {p.like_count}, 댓글 {p.comment_count}, {p.slide_count}장: {(p.caption or '')[:100]}"
            for p in ref_posts[:5]
        ])
        topic = f"{topic}\n\n[레퍼런스 포스트 분석]\n{ref_context}"

    result = await gen.generate_slides(
        topic=topic, tone=tone, slide_count=slide_count
    )

    slides = result.get("slides", [])
    image_keywords = []
    clean_topic = topic.split("\n")[0]  # 레퍼런스 컨텍스트 제거
    for slide in slides:
        headline = slide.get("headline", "")
        stype = slide.get("type", "content")
        items = slide.get("items") or []
        idx = slide.get("index", 0)
        if items and stype in ("cover", "content"):
            for j, it in enumerate(items):
                title = (it.get("title") if isinstance(it, dict) else "") or headline or clean_topic
                image_keywords.append({"slide_index": idx, "item_index": j, "keywords": [title], "style": "photo"})
            continue
        if stype == "cover":
            image_keywords.append({"slide_index": idx, "item_index": None, "keywords": [clean_topic], "style": "photo"})
        elif stype == "content" and headline:
            image_keywords.append({"slide_index": idx, "item_index": None, "keywords": [headline], "style": "photo"})

    # 레퍼런스 포스트의 이미지 정보도 반환
    ref_images = []
    for p in ref_posts:
        for img in (p.images or []):
            ref_images.append({
                "post_id": p.id,
                "slide_index": img.slide_index,
                "url": img.raw_path,
                "caption": (p.caption or "")[:60],
            })

    return {
        "topic": clean_topic,
        "slides": slides,
        "caption": result.get("caption", ""),
        "hashtags": result.get("hashtags", []),
        "image_keywords": image_keywords,
        "ref_posts": [
            {
                "id": p.id,
                "caption": (p.caption or "")[:80],
                "post_url": p.post_url,
                "like_count": p.like_count,
                "comment_count": p.comment_count,
                "slide_count": p.slide_count,
                "thumbnail": p.images[0].raw_path if p.images else None,
            }
            for p in ref_posts
        ],
        "ref_images": ref_images[:20],
    }


class TranslateKeywordRequest(BaseModel):
    query: str
    context: str = ""


# Per-process LRU cache for the LLM-classified query plan. Same (query, ctx)
# yields the same structured output every time, but each carousel touches
# the same keyword across multiple cells — without this cache, generate-content
# fires the same Gemini call N times in a single user flow. 500 slots covers
# a healthy session; oldest evicted when full.
from collections import OrderedDict as _OrderedDict

_TRANSLATE_CACHE: "_OrderedDict[tuple[str, str], dict]" = _OrderedDict()
_TRANSLATE_CACHE_MAX = 500


def _translate_cache_key(query: str, ctx: str) -> tuple[str, str]:
    # Collapse whitespace + casefold so cosmetic differences hit the same slot.
    return (" ".join(query.split()).casefold(), " ".join(ctx.split()).casefold())


@router.post("/translate-keyword")
async def translate_keyword_endpoint(
    body: TranslateKeywordRequest,
    user: User = Depends(get_current_user),
):
    """Classify a Korean keyword (place vs general) and produce search variants.

    - Place (cafe/park/shop/street/restaurant/landmark): emit native-script
      query first (e.g. 도쿄 요요기 공원 → 東京 代々木公園) so non-English image
      search engines route through the local CDN.
    - General (product/object/concept): keep brand verbatim, drop city if the
      subject is portable.

    Returns {kind, queries[], country}. queries are ordered best→fallback so
    the frontend can iterate and merge results round-robin.
    """
    import json as _json
    from app.agents.llm_client import _call_api

    q = (body.query or "").strip()
    if not q:
        raise HTTPException(status_code=400, detail="query 비어 있음")
    ctx = (body.context or "").strip()
    ctx_line = f"전체 캐러셀 주제 컨텍스트: {ctx!r}\n\n" if ctx else ""

    cache_key = _translate_cache_key(q, ctx)
    cached = _TRANSLATE_CACHE.get(cache_key)
    if cached is not None:
        _TRANSLATE_CACHE.move_to_end(cache_key)
        return cached

    # Feedback #15-16: 이미지 검색 정확도 개선을 위한 구조화된 query plan 출력.
    # 기존 (kind/queries/country)는 백워드 호환으로 유지하고, 새로 다음을 추가:
    #   forms                 — 언어별 이름 표기 (한국어 + 현지어 + 영문/로마자)
    #   region_anchor         — 언어별 지역 앵커 (place 계열만, 없으면 빈 객체)
    #   category              — 세부 카테고리 ("ramen restaurant", "tokyo neighborhood" 등)
    #   desired_image_types   — 검색에 바이어스 줄 이미지 타입 (food/exterior/scene 등)
    #   excludes              — 디스카운트 대상 (map/menu_board/logo 등)
    # `queries`는 forms + region_anchor + default modifier로 코드가 합성 가능하지만
    # 호환 편의상 LLM이 함께 생성한다.
    prompt = (
        f"한국어 이미지 검색 키워드를 받아 구조화된 query plan을 생성합니다.\n\n"
        f"{ctx_line}"
        f"# kind 분류\n"
        f"- **place**: 카페·식당·공원·거리·호텔·명소·동네·가게·상점·시장 등 위치에 묶인 것\n"
        f"- **general**: 제품·과자·화장품·의류·책·가전·일반 명사·추상 개념 등 위치 무관\n\n"
        f"# forms — 언어별 이름 표기 (sparse, 해당 없는 key 생략)\n"
        f"  ko: 한국어 표기 (거의 항상)\n"
        f"  ja: 일본어 origin이면 한자/가나 표기\n"
        f"  zh: 중국어 origin이면 한자 표기\n"
        f"  en: 영문/로마자 (브랜드, 글로벌 키워드, 비라틴 origin의 로마자)\n"
        f"  → 한국 origin은 ko + (en 있을 때만), 일본/중국 origin은 ko + 현지어 + en 셋 다\n\n"
        f"# region_anchor — 언어별 지역 앵커\n"
        f"  place 계열(restaurant/cafe/landmark/place 등)만 채움, 그 외는 빈 객체 {{}}\n"
        f"  forms 와 동일한 언어 키를 사용 (ko='도쿄', ja='東京', en='Tokyo')\n"
        f"  region은 city/metropolitan 수준 (도쿄·오사카·서울·파리). 너무 좁은 동네(도톤보리)는 X\n\n"
        f"# category — 구체 카테고리 (가능한 한 아래 canonical 영문 키에 맞춰 분류)\n"
        f"  음식점: ramen restaurant · sushi restaurant · udon restaurant · soba restaurant ·\n"
        f"          curry restaurant · tempura restaurant · yakiniku restaurant · izakaya ·\n"
        f"          korean bbq · pho restaurant · pizza restaurant · burger restaurant ·\n"
        f"          pasta restaurant · steakhouse · taco restaurant\n"
        f"  카페·디저트: cafe · coffee shop · bakery · ice cream shop · dessert shop\n"
        f"  술집: bar · wine bar\n"
        f"  장소·기타: tokyo neighborhood · park · landmark · museum · temple · shrine ·\n"
        f"          beach · vintage store · convenience store · department store · select shop\n"
        f"  위 목록에 없으면 자유롭게 영문 소문자로 (예: 'office lunch box', 'vacuum cleaner')\n\n"
        f"# desired_image_types — 검색에 어떤 사진을 원하는지 (배열)\n"
        f"  enum: food | exterior | interior | landmark | scene | ambiance | product\n"
        f"  카테고리에서 자연스러운 1~3개. 예: restaurant=[food,exterior], landmark=[landmark,scene],\n"
        f"  neighborhood=[scene,ambiance,exterior], cafe=[interior,exterior,ambiance], product=[product]\n\n"
        f"# excludes — 디스카운트 대상\n"
        f"  enum: map | menu_board | logo | coupon | ad | face_centric\n"
        f"  place류는 기본 [map,menu_board,logo,coupon] 권장\n\n"
        f"# queries (백워드 호환) — 위 forms + region_anchor 로 만든 검색어 3~5개\n"
        f"  place: 현지어 → en → ko 순. 각 form에 region_anchor를 자연 어순으로 결합\n"
        f"  general: ko → en → 현지어 순. 도시 X\n\n"
        f"# country — ISO2 (kr|jp|fr|us|cn|...)\n\n"
        f"# 출력 (단일 JSON 객체만)\n"
        f'{{"kind":"place|general","forms":{{...}},"region_anchor":{{...}},'
        f'"category":"...","desired_image_types":[...],"excludes":[...],'
        f'"queries":[...],"country":"..."}}\n\n'
        f"# 예시\n"
        f'  입력: "도쿄 요요기 공원" →\n'
        f'    {{"kind":"place",\n'
        f'     "forms":{{"ko":"요요기 공원","ja":"代々木公園","en":"Yoyogi Park"}},\n'
        f'     "region_anchor":{{"ko":"도쿄","ja":"東京","en":"Tokyo"}},\n'
        f'     "category":"tokyo park","desired_image_types":["scene","landmark","ambiance"],\n'
        f'     "excludes":["map","logo"],\n'
        f'     "queries":["東京 代々木公園","Yoyogi Park Tokyo","도쿄 요요기 공원"],"country":"jp"}}\n'
        f'  입력: "하라주쿠 KINJI 빈티지샵" →\n'
        f'    {{"kind":"place",\n'
        f'     "forms":{{"ko":"하라주쿠 KINJI 빈티지샵","ja":"原宿 KINJI 古着屋","en":"Harajuku KINJI vintage store"}},\n'
        f'     "region_anchor":{{"ko":"도쿄","ja":"東京","en":"Tokyo"}},\n'
        f'     "category":"vintage store","desired_image_types":["exterior","interior"],\n'
        f'     "excludes":["map","logo","menu_board"],\n'
        f'     "queries":["東京 原宿 KINJI 古着屋","Harajuku KINJI vintage store Tokyo","도쿄 하라주쿠 KINJI 빈티지샵"],"country":"jp"}}\n'
        f'  입력: "메이지 아폴로 초콜릿" →\n'
        f'    {{"kind":"general",\n'
        f'     "forms":{{"ko":"메이지 아폴로 초콜릿","ja":"明治 アポロ チョコレート","en":"meiji apollo chocolate"}},\n'
        f'     "region_anchor":{{}},\n'
        f'     "category":"chocolate product","desired_image_types":["product"],\n'
        f'     "excludes":[],\n'
        f'     "queries":["메이지 아폴로 초콜릿","meiji apollo chocolate","明治 アポロ チョコレート"],"country":"jp"}}\n'
        f'  입력: "기요스미시라카와" (컨텍스트: 도쿄 로컬 동네 카드뉴스) →\n'
        f'    {{"kind":"place",\n'
        f'     "forms":{{"ko":"기요스미시라카와","ja":"清澄白河","en":"Kiyosumi-Shirakawa"}},\n'
        f'     "region_anchor":{{"ko":"도쿄","ja":"東京","en":"Tokyo"}},\n'
        f'     "category":"tokyo neighborhood","desired_image_types":["scene","ambiance","exterior"],\n'
        f'     "excludes":["map","logo","menu_board"],\n'
        f'     "queries":["東京 清澄白河","Kiyosumi-Shirakawa Tokyo","도쿄 기요스미시라카와"],"country":"jp"}}\n\n'
        f'입력: "{q}"\n출력:'
    )
    try:
        raw = await _call_api(
            "gemini/gemini-2.5-flash",
            [{"role": "user", "content": prompt}],
            json_mode=True,
            max_tokens=512,
        )
        if isinstance(raw, str):
            raw_text = raw.strip()
            if raw_text.startswith("```"):
                parts = raw_text.split("```")
                if len(parts) >= 3:
                    raw_text = parts[1].strip()
                    if raw_text.lower().startswith("json"):
                        raw_text = raw_text[4:].strip()
            data_obj = _json.loads(raw_text)
        else:
            data_obj = raw
        if isinstance(data_obj, list) and len(data_obj) == 1 and isinstance(data_obj[0], dict):
            data_obj = data_obj[0]
        if not isinstance(data_obj, dict):
            raise ValueError(f"non-dict response: {str(data_obj)[:120]}")
        kind = str(data_obj.get("kind") or "general").lower().strip()
        if kind not in ("place", "general"):
            kind = "general"
        queries_raw = data_obj.get("queries") or []
        if not isinstance(queries_raw, list):
            queries_raw = [q]
        # Dedupe (case-insensitive) preserving order, drop empties
        seen, queries = set(), []
        for item in queries_raw:
            s = str(item or "").strip()
            if s and s.lower() not in seen:
                seen.add(s.lower())
                queries.append(s)
        if not queries:
            queries = [q]
        country = (str(data_obj.get("country") or "").strip().lower()) or "kr"

        # Feedback #15-16: structured query plan fields. All optional — frontend
        # falls back gracefully if missing. Validate shapes so a malformed LLM
        # response doesn't poison the cell state downstream.
        def _str_dict(v: object) -> dict[str, str]:
            if not isinstance(v, dict):
                return {}
            out: dict[str, str] = {}
            for k, val in v.items():
                ks = str(k or "").strip().lower()
                vs = str(val or "").strip()
                if ks and vs:
                    out[ks] = vs
            return out

        def _str_list(v: object, allowed: set[str] | None = None) -> list[str]:
            if not isinstance(v, list):
                return []
            out: list[str] = []
            for item in v:
                s = str(item or "").strip().lower()
                if not s:
                    continue
                if allowed is not None and s not in allowed:
                    continue
                if s not in out:
                    out.append(s)
            return out

        forms = _str_dict(data_obj.get("forms"))
        region_anchor = _str_dict(data_obj.get("region_anchor"))
        category = str(data_obj.get("category") or "").strip()
        desired_image_types = _str_list(
            data_obj.get("desired_image_types"),
            allowed={"food", "exterior", "interior", "landmark", "scene", "ambiance", "product"},
        )
        excludes = _str_list(
            data_obj.get("excludes"),
            allowed={"map", "menu_board", "logo", "coupon", "ad", "face_centric"},
        )

        result = {
            "kind": kind,
            "queries": queries,
            "country": country,
            "forms": forms,
            "region_anchor": region_anchor,
            "category": category,
            "desired_image_types": desired_image_types,
            "excludes": excludes,
        }
        # Cache successful runs only — never cache the fallback below.
        _TRANSLATE_CACHE[cache_key] = result
        _TRANSLATE_CACHE.move_to_end(cache_key)
        while len(_TRANSLATE_CACHE) > _TRANSLATE_CACHE_MAX:
            _TRANSLATE_CACHE.popitem(last=False)
        return result
    except Exception as e:
        logger.exception("translate-keyword failed")
        # Defensive fallback — keep the original Korean as the single query.
        return {
            "kind": "general",
            "queries": [q],
            "country": "kr",
            "forms": {"ko": q},
            "region_anchor": {},
            "category": "",
            "desired_image_types": [],
            "excludes": [],
            "fallback_reason": str(e)[:120],
        }


class ParaphraseRequest(BaseModel):
    texts: list[str]
    tone: str = "marketing"  # "marketing" | "casual" | "punchy"
    kind: str = "body"  # "body" (카드뉴스 속지) | "title" (제목)


def _strip_json_fence(raw: str) -> str:
    text = raw.strip()
    if text.startswith("```"):
        parts = text.split("```")
        if len(parts) >= 3:
            text = parts[1].strip()
            if text.lower().startswith("json"):
                text = text[4:].strip()
    return text


def _unescape_newlines(text: str) -> str:
    r"""Turn a literal escaped newline the model emitted (a backslash followed
    by 'n', i.e. the two characters ``\n``) into a real newline. Models asked to
    JSON-escape line breaks sometimes double-escape, so ``json.loads`` leaves a
    literal ``\n`` inside the string — the editor then shows "\n" instead of a
    line break. Normalize the common forms so paraphrased 속지글/캡션 wrap."""
    if not isinstance(text, str) or "\\" not in text:
        return text
    return text.replace("\\r\\n", "\n").replace("\\n", "\n").replace("\\r", "\n")


def default_paraphrase_body(n: int, tone: str = "marketing") -> str:
    """Render the system-default body for the /paraphrase prompt.

    Public so the per-user settings endpoint can hand the same text to the UI
    as the placeholder/starting point. The input + JSON output framing is
    added by the caller, not here.

    한국어 AI-티 제거 규칙은 epoko77-ai/im-not-ai 의 분류·처방집 기반.
    길이는 원문(±10%) 그대로 유지 — 정보 누락 없이 표현만 바꾸기.
    """
    tone_hint = {
        "marketing": "인스타 캡션에 사람이 직접 쓴 듯한 평범한 한국어",
        "casual": "친구에게 말하듯 가볍고 편한 한국어",
        "punchy": "짧고 또박또박한 한국어",
    }.get(tone, "인스타 캡션에 사람이 직접 쓴 듯한 평범한 한국어")
    return (
        f"다음 {n}개의 한국어 설명(인스타 카드뉴스 셀에 들어갈 텍스트)을 다시 써주세요.\n\n"
        f"# 핵심 원칙 (반드시 지킬 것)\n"
        f"**원본 내용의 요소는 모두 살리되, 같은 내용을 다른 표현 방식으로 나타낸다.**\n"
        f"- 의미·정보는 그대로, 표현 방식만 새롭게.\n"
        f"- 단순히 어순만 바꾸는 게 아니라 **어휘·문장 구조·관점**까지 적극 다르게 써서 '같은 말을 다르게 한 듯한' 결과로.\n"
        f"- 원문에 없던 새 정보·과장·감상은 추가하지 말 것. 거꾸로, 원문에 있던 정보를 빼지도 말 것.\n\n"
        f"# 원칙\n"
        f"- 톤: {tone_hint}\n"
        f"- **길이 보존**: 출력은 원문 글자 수의 ±10% 이내. 절대로 짧게 줄이지 말 것.\n"
        f"  · 원문이 80자면 출력도 72~88자. 원문이 두 문장이면 출력도 두 문장.\n"
        f"  · 정보를 빼서 문장을 짧게 만들지 말 것.\n"
        f"- **정보 누락 금지**: 원문에 나오는 모든 요소를 빠짐없이 옮길 것 — 장소·시간·이유·비교·부연 설명·감상·맥락·예시 모두. 핵심 정보(제품명·브랜드명·맛·식감·재료·고유명사)는 단어·표기 그대로 유지.\n"
        f"- **한 호흡 한 문장**(단문일 때 한정): 단문을 쉼표로 두 덩이로 쪼개지 말 것. 디자인에서 두 줄로 갈라져 보임.\n"
        f"  · 나쁨: '바삭한 비스킷, 진한 초콜릿 코팅' ← 단문 콤마 분할\n"
        f"  · 좋음: '바삭한 비스킷에 진한 초콜릿 코팅'\n"
        f"  · 단, 원문이 두 문장 이상이면 마침표로 자연스럽게 끊을 것.\n"
        f"- 같은 표현/접속사 반복 금지, 입력 순서 그대로 출력\n\n"
        f"# ❌ 쓰지 말 것 (AI 티 강함)\n"
        f"**과장·외침**\n"
        f"- 느낌표(!) — 평서문으로 끝낼 것\n"
        f"- '마법·신세계·혁명·판타지·행복·천국·꿀맛·비밀·진리·발견·매력·완벽' 같은 추상 명사\n"
        f"- 'X의 Y' 외침 패턴: '~의 마법', '~의 발견', '~의 매력', '~의 행복', '~의 향연', '~의 정수'\n"
        f"- '톡!', '폭발!', '귀여움 폭발', '느낌적인 느낌' 같은 의성·의태 과장\n"
        f"- '혁신적·획기적·압도적·환상적·놀라운' 같은 과대 형용사\n"
        f"**번역투·이중 표현**\n"
        f"- '~을 통해 X' (→ '~로 X' / '~해서 X')\n"
        f"- '~에 대해' (→ '~를' / 직접 서술)\n"
        f"- '~에 있어서' (→ '~에서' / '~할 때')\n"
        f"- '~되어진다·~여진다' 이중 피동 (→ '~된다·~진다')\n"
        f"- '~고 있다' 남발 (→ 현재형 단순화)\n"
        f"- '~할 수 있다·~할 수 있을 것이다' — 단언 가능하면 '~한다·~이다'\n"
        f"**형식·과수식**\n"
        f"- '매우·정말·너무·아주·대단히·진짜' 같은 정도부사 (구체 단어로 바꾸거나 삭제)\n"
        f"- '~적·~성·~화' 접사 (구체 동사·명사로 풀기)\n"
        f"- '~다는 것이다' (→ '~다')\n"
        f"- '~할 필요가 있다' (→ '~해야 한다' 또는 구체 행위)\n\n"
        f"# ✅ 지향하는 톤\n"
        f"인스타 카드뉴스에서 사람이 직접 쓴 듯한 평서문. **원문 길이·정보는 그대로 두고, 어휘·문장 구조·관점까지 적극 바꿔 같은 내용을 새 표현으로** 나타낸다. 명사구로 끝나는 것도 OK.\n\n"
        f"# 예시\n"
        f"  ▷ 단문 (한 호흡 한 문장, 쉼표 분할 X)\n"
        f"  원문: '사르르 녹는 겨울 한정 카라멜 초콜릿' (18자)\n"
        f"  좋음: '입에서 부드럽게 녹는 겨울 한정 카라멜 초콜릿' (22자)\n"
        f"  나쁨: '겨울 한정 카라멜 초콜릿, 입에서 부드럽게 녹음' ← 쉼표 분할\n"
        f"  나쁨: '입안 가득 겨울 판타지! 사르르 녹는 카라멜 초콜릿!' ← 느낌표·판타지\n\n"
        f"  원문: '바삭 비스킷에 진한 밀크 초콜릿 샌드' (18자)\n"
        f"  좋음: '바삭한 비스킷 사이에 진한 밀크 초콜릿이 들어간 샌드' (26자)\n"
        f"  나쁨: '바삭한 비스킷, 진한 밀크 초콜릿 샌드' ← 쉼표 분할\n\n"
        f"  ▷ 장문 (정보 빠짐없이, 길이 그대로)\n"
        f"  원문: '제가 가장 좋아하는 헝가리 부다페스트 여행지인데요. 도시 뷰가 아름답지만 그 중 일몰빛은 제 인생 보물급!' (54자)\n"
        f"  좋음: '헝가리 부다페스트에서 제일 마음에 든 곳이에요. 도시 야경도 좋지만 그 중에서도 일몰 풍경은 평생 못 잊을 정도였어요.' (57자)\n"
        f"  나쁨: '부다페스트 일몰 명소' ← 정보 대거 누락·단축\n"
        f"  나쁨: '제 인생 보물 같은 부다페스트 일몰 풍경!' ← 도시 뷰·여행지 맥락 누락\n\n"
        f"  원문: '1층은 식료품 2층은 잡화와 군것질거리가 있어요. 소세지·술·과일·향신료 등을 주로 팔고 구경하기 좋아요.' (54자)\n"
        f"  좋음: '1층에는 식료품이 있고 2층에는 잡화와 간식거리가 있어요. 소세지와 술, 과일, 향신료 등이 주를 이루고 둘러보기 좋아요.' (58자)\n"
        f"  나쁨: '1층 식료품, 2층 잡화·간식' ← 부연 설명 통째 삭제"
    )


def default_paraphrase_title(n: int) -> str:
    """System-default body for /paraphrase when kind='title' — the 카드뉴스
    표지·슬라이드 제목 rewrite voice. Titles need a short, punchy hook, unlike
    the length-preserving body rewrite (feedback #11-13)."""
    return (
        f"다음 {n}개의 한국어 카드뉴스 제목을 다시 써주세요.\n\n"
        f"# 핵심 원칙\n"
        f"제목은 짧고 강한 후킹 문장입니다. 원문의 핵심 주제는 유지하되 표현·구조는 새롭게.\n\n"
        f"# 원칙\n"
        f"- 원문의 핵심 주제·소재는 그대로 유지\n"
        f"- 클릭하고 계속 보고 싶게 만드는 후킹 표현 사용\n"
        f"- 10~20자 내외의 짧은 제목 중심 — 설명식으로 길게 늘이지 말 것\n"
        f"- 레퍼런스 원문과 문장 구조·어순이 겹치지 않게 변경\n"
        f"- 원문에 없던 정보·과장은 추가하지 말 것, 사실은 왜곡하지 말 것\n"
        f"- 입력 순서 그대로 출력\n\n"
        f"# ❌ 쓰지 말 것 (AI 티)\n"
        f"- 느낌표(!) — 평서문이나 명사구로 끝낼 것\n"
        f"- '마법·신세계·혁명·판타지·천국·꿀맛·완벽·비밀·정수' 같은 추상·과장 명사\n"
        f"- 'X의 Y' 외침 패턴 ('~의 마법', '~의 발견', '~의 매력')\n"
        f"- '혁신적·획기적·압도적·환상적·놀라운' 같은 과대 형용사\n"
        f"- 번역투 '~을 통해', '~에 대해', 이중 피동 '~되어진다'\n\n"
        f"# 예시\n"
        f"  원문: '겨울에 가기 좋은 국내 여행지 추천'\n"
        f"  좋음: '겨울에 진짜 가봐야 하는 국내 여행지'\n"
        f"  나쁨: '겨울 여행의 마법 같은 국내 명소 대공개!' ← 과장·느낌표\n"
        f"  원문: '직장인 점심 도시락 꿀팁'\n"
        f"  좋음: '점심값 아끼는 직장인 도시락 노하우'\n"
        f"  나쁨: '도시락의 신세계, 직장인 점심 혁명!' ← 추상·외침"
    )


@router.post("/paraphrase")
async def paraphrase_endpoint(
    body: ParaphraseRequest,
    user: User = Depends(get_current_user),
):
    """Rewrite a batch of short Korean descriptions: same meaning, fresh wording.

    Used by the Step 1 (콘텐츠 확인) UI when the user wants alternative phrasing
    for one cell or all cells of a grid slide. One LLM call handles the whole
    batch — much cheaper than per-cell round trips.
    """
    import json as _json
    from json import JSONDecodeError
    from app.agents.llm_client import _call_api

    texts = [t for t in (body.texts or []) if isinstance(t, str)]
    if not texts:
        return {"paraphrased": []}

    numbered = "\n".join(f"{i+1}. {t}" for i, t in enumerate(texts))

    # 제목과 속지(body)는 글의 성격이 달라 프롬프트를 분리한다 (feedback #11-13).
    # 유형별 사용자 오버라이드가 있으면 그게 우선, 없으면 유형별 기본 프롬프트.
    # 입력 + JSON 출력 형식 framing 은 어느 경우든 서버가 덧붙인다.
    if body.kind == "title":
        user_body = (getattr(user, "title_paraphrase_prompt", None) or "").strip()
        body_text = user_body or default_paraphrase_title(len(texts))
    else:
        user_body = (getattr(user, "paraphrase_prompt", None) or "").strip()
        body_text = user_body or default_paraphrase_body(len(texts), body.tone)

    prompt = (
        f"{body_text}\n\n"
        f"입력:\n{numbered}\n\n"
        f"출력: 위 {len(texts)}개에 대응하는 JSON 배열만. 예: [\"새 표현1\", \"새 표현2\", ...]\n"
        f"문자열 안 줄바꿈은 반드시 \\n(JSON escape)으로 쓰고, 실제 줄바꿈은 넣지 마세요."
    )
    try:
        max_tokens = max(2048, min(8192, sum(len(t) for t in texts) * 3 + 768))
        raw = await _call_api(
            "gemini/gemini-2.5-flash",
            [{"role": "user", "content": prompt}],
            json_mode=True,
            max_tokens=max_tokens,
            temperature=0.3,
        )
        try:
            data_obj = _json.loads(_strip_json_fence(raw)) if isinstance(raw, str) else raw
        except JSONDecodeError as first_err:
            logger.warning(f"paraphrase JSON parse failed; retrying once: {first_err}")
            retry_prompt = (
                "다음 입력을 같은 순서의 JSON 문자열 배열로만 다시 써주세요.\n"
                "마크다운 금지, 설명 금지, 객체 금지. 반드시 유효한 JSON 배열만 출력하세요.\n"
                "문자열 안 따옴표와 줄바꿈은 JSON 규칙에 맞게 escape하세요.\n\n"
                f"입력 JSON 배열:\n{_json.dumps(texts, ensure_ascii=False)}"
            )
            try:
                raw = await _call_api(
                    "gemini/gemini-2.5-flash",
                    [{"role": "user", "content": retry_prompt}],
                    json_mode=True,
                    max_tokens=max_tokens,
                    temperature=0.2,
                )
                data_obj = _json.loads(_strip_json_fence(raw)) if isinstance(raw, str) else raw
            except Exception as retry_err:
                logger.exception(f"paraphrase retry failed; returning originals: {retry_err}")
                return {"paraphrased": texts, "fallback": True}
        if isinstance(data_obj, dict):
            for key in ("paraphrased", "results", "data", "items"):
                if isinstance(data_obj.get(key), list):
                    data_obj = data_obj[key]
                    break
        if not isinstance(data_obj, list):
            logger.warning(f"paraphrase returned non-list; returning originals: {str(data_obj)[:120]}")
            return {"paraphrased": texts, "fallback": True}
        out: list[str] = []
        for i, item in enumerate(data_obj):
            if isinstance(item, str):
                out.append(_unescape_newlines(item.strip()))
            elif isinstance(item, dict):
                out.append(_unescape_newlines(str(item.get("text") or item.get("rewrite") or "").strip()))
            else:
                out.append(texts[i] if i < len(texts) else "")
        # Pad/truncate to match input length so the caller can zip 1:1
        while len(out) < len(texts):
            out.append(texts[len(out)])
        out = out[: len(texts)]
        return {"paraphrased": out}
    except Exception as e:
        logger.exception("paraphrase failed")
        return {"paraphrased": texts, "fallback": True}


class CaptionParaphraseRequest(BaseModel):
    caption: str
    topic: str = ""


def default_paraphrase_caption() -> str:
    """System-default rules body for /paraphrase-caption (feedback #11-13).
    The {hook, body} JSON output framing is added by the endpoint; this is the
    editable rules portion, mirroring default_paraphrase_body for /paraphrase."""
    return (
        "# hook (첫 줄, 10자 이내)\n"
        "- 인스타 캡션의 첫 줄은 미리보기에 보이는 부분. **사용자가 '더보기'를 누르게 만드는 미끼.**\n"
        "- 독자의 **욕망·결핍·FOMO**를 자극: '나만 모르면 어쩌지', '나도 갖고 싶다', '안 가면 손해'\n"
        "- 10자 이내 (공백 포함). 이모지 금지. 일반 명사구·평서문·반문형 모두 OK\n"
        "- 캡션 본문 주제·청자를 읽고 그에 맞춰 작성\n"
        "- 좋은 예 (구체적 갈증 자극):\n"
        "  · 여행 캐러셀 → '현지인만 아는 곳', '여행 가기 전 필독', '관광객 1도 없음'\n"
        "  · 쇼핑·맛집 → '직원만 아는 픽', '재고 떨어지기 전', '한국에 없음'\n"
        "  · 정보·팁    → '다들 잘못 알고 있음', '이거 모르면 손해', '돈 아끼는 법'\n"
        "  · 일반       → '저장 필수', '후회 없음', '진짜 있음'\n"
        "- 나쁜 예: '여행의 마법', '꿈의 발견', '환상의 코스', '신세계' ← 추상·과장\n"
        "- 나쁜 예: '재밌는 여행', '맛있는 간식' ← 평범, 후킹력 0\n\n"
        "# body (본문, 원문과 같은 의미 다른 표현)\n"
        "- 원문 캡션의 사실·제품명·브랜드·수치를 단어 그대로 유지\n"
        "- 표현·접속사·문장 순서는 자연스럽게 변주\n"
        "- 길이 원문 ±30% 이내\n"
        "- 마지막에는 저장·공유·댓글·팔로우 등 행동 유도(CTA)를 자연스럽게 포함\n\n"
        "# ❌ 절대 금지 (AI 티)\n"
        "- 느낌표(!) 전면 금지 — 평서문으로만 끝낼 것 (hook도 body도)\n"
        "- 추상 명사: 마법·판타지·신세계·혁명·천국·꿀맛·완벽·발견\n"
        "- 'X의 Y' 외침 패턴: '~의 마법', '~의 발견', '~의 매력'\n"
        "- 정도부사 매우·정말·너무·대단히 남용\n"
        "- 번역투: '~을 통해', '~에 대해', '~에 있어서', '~되어진다', '~할 수 있다'(단언 가능 시)\n"
        "- 형식명사: '~다는 것이다', '~할 필요가 있다'\n"
        "- 의성·의태 과장: 톡!, 폭발!, 귀여움 폭발"
    )


@router.post("/paraphrase-caption")
async def paraphrase_caption_endpoint(
    body: CaptionParaphraseRequest,
    user: User = Depends(get_current_user),
):
    """Rewrite a carousel caption: hook-y first line + paraphrased body.

    Single LLM call returns structured {hook, body}. The hook (≤10자) is built
    to make readers tap "더보기"; the body keeps the original meaning but uses
    fresh wording. Same anti-AI-tell rules as /paraphrase.
    """
    import json as _json
    from json import JSONDecodeError
    from app.agents.llm_client import _call_api, llm_call

    raw_caption = (body.caption or "").strip()
    if not raw_caption:
        raise HTTPException(status_code=400, detail="캡션이 비어 있습니다")

    topic = (body.topic or "").strip()
    topic_line = f"주제 컨텍스트: {topic!r}\n\n" if topic else ""

    # 캡션 치환 규칙도 계정별로 덮어쓸 수 있다 (feedback #11-13). hook/body 의
    # JSON 출력 형식 framing 은 서버가 유지하고, 규칙 본문만 사용자 값으로 교체.
    caption_rules = (getattr(user, "caption_paraphrase_prompt", None) or "").strip()
    if not caption_rules:
        caption_rules = default_paraphrase_caption()

    prompt = (
        f"인스타그램 카드뉴스의 한국어 캡션을 다시 써주세요. **출력은 100% 한국어로만**.\n\n"
        f"{topic_line}"
        f"# 출력 형식\n"
        f"단일 JSON 객체(배열 X, 마크다운 X)만 출력:\n"
        f'  {{"hook": "한국어 한 줄", "body": "한국어 본문"}}\n\n'
        f"문자열 안 줄바꿈은 반드시 \\n(JSON escape)으로 쓰고, 실제 줄바꿈은 넣지 마세요.\n\n"
        f"{caption_rules}\n\n"
        f"# 원문 캡션\n{raw_caption}\n\n"
        f"위 규칙에 따라 JSON만 출력:"
    )
    try:
        messages = [{"role": "user", "content": prompt}]
        max_tokens = max(2048, min(8192, len(raw_caption) * 2 + 768))
        try:
            raw = await _call_api(
                "gemini/gemini-2.5-flash",
                messages,
                json_mode=True,
                max_tokens=max_tokens,
                temperature=0.3,
            )
        except Exception as gemini_err:
            msg = str(gemini_err)
            is_quota = (
                "429" in msg
                or "RateLimit" in msg
                or "RESOURCE_EXHAUSTED" in msg
                or "monthly spending cap" in msg
            )
            if not is_quota:
                raise
            logger.warning("caption paraphrase Gemini quota hit; falling back to Claude Haiku")
            raw = await llm_call(
                "haiku",
                messages,
                json_mode=True,
                max_tokens=max_tokens,
            )
        try:
            data_obj = _json.loads(_strip_json_fence(raw)) if isinstance(raw, str) else raw
        except JSONDecodeError as first_err:
            logger.warning(f"caption paraphrase JSON parse failed; retrying once: {first_err}")
            retry_prompt = (
                "다음 인스타그램 캡션을 다시 쓰고, 유효한 단일 JSON 객체만 출력하세요.\n"
                "마크다운 금지, 설명 금지. 키는 hook, body 두 개만 사용하세요.\n"
                "문자열 안 따옴표와 줄바꿈은 JSON 규칙에 맞게 escape하세요.\n"
                f"주제: {topic or ''}\n\n"
                f"원문 캡션:\n{raw_caption}\n\n"
                '출력 예: {"hook":"한국어 한 줄","body":"한국어 본문"}'
            )
            try:
                raw = await _call_api(
                    "gemini/gemini-2.5-flash",
                    [{"role": "user", "content": retry_prompt}],
                    json_mode=True,
                    max_tokens=max_tokens,
                    temperature=0.2,
                )
                data_obj = _json.loads(_strip_json_fence(raw)) if isinstance(raw, str) else raw
            except Exception as retry_err:
                logger.exception(f"caption paraphrase retry failed; returning original: {retry_err}")
                return {"paraphrased": raw_caption, "hook": "", "body": raw_caption, "fallback": True}
        # LLM occasionally wraps the object in a 1-element array. Unwrap.
        if isinstance(data_obj, list) and len(data_obj) == 1 and isinstance(data_obj[0], dict):
            data_obj = data_obj[0]
        if not isinstance(data_obj, dict):
            logger.warning(f"caption paraphrase returned non-dict; returning original: {str(data_obj)[:120]}")
            return {"paraphrased": raw_caption, "hook": "", "body": raw_caption, "fallback": True}
        hook = _unescape_newlines(str(data_obj.get("hook") or "").strip())
        body_text = _unescape_newlines(str(data_obj.get("body") or "").strip())
        # Defensive cleanup — the model occasionally ignores prompt constraints.
        # 1) Strip emoji and other pictographic characters from the hook.
        import re as _re
        emoji_pattern = _re.compile(
            "[\U0001F300-\U0001FAFF\U0001F600-\U0001F64F\U0001F900-\U0001F9FF"
            "\U0001F1E6-\U0001F1FF\U00002600-\U000027BF\U0001F000-\U0001F0FF]+",
            flags=_re.UNICODE,
        )
        hook = emoji_pattern.sub("", hook).strip()
        # 2) Drop trailing punctuation (looks AI-y)
        hook = hook.rstrip("!?.…~")
        # 3) Hard-clamp to 10 chars (per spec)
        if len(hook) > 10:
            hook = hook[:10].rstrip()
        full = f"{hook}\n\n{body_text}" if hook else body_text
        return {"paraphrased": full, "hook": hook, "body": body_text}
    except Exception as e:
        logger.exception("caption paraphrase failed")
        return {"paraphrased": raw_caption, "hook": "", "body": raw_caption, "fallback": True}


@router.post("/orchestrate", response_model=OrchestratorResponse)
async def orchestrate(
    data: OrchestratorRequest,
    user: User = Depends(get_current_user),
):
    """Run the agent orchestration pipeline."""
    orchestrator = Orchestrator()
    result = await orchestrator.run(
        user_request=data.request,
        context=data.context,
    )
    return OrchestratorResponse(**result)
