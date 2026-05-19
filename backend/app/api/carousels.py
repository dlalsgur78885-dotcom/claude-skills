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
from app.schemas.carousel import (
    CarouselCreate,
    CarouselUpdate,
    CarouselResponse,
    OrchestratorRequest,
    OrchestratorResponse,
)
from app.api.auth import get_current_user
from app.agents.orchestrator import Orchestrator

router = APIRouter(prefix="/carousels", tags=["carousels"])


@router.get("/", response_model=list[CarouselResponse])
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
    return result.scalars().all()


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
    return carousel


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

    # OCR 실행
    reader = easyocr.Reader(["ko", "en"], gpu=False, verbose=False)
    slides_analysis = []

    for img in sorted(post.images, key=lambda x: x.slide_index):
        # 로컬 경로 해석
        raw_path = img.raw_path
        if raw_path.startswith("/api/images/raw/"):
            parts = raw_path.replace("/api/images/raw/", "").split("/")
            local_path = Path("data/images/raw") / parts[0] / parts[1]
        else:
            local_path = Path(raw_path)

        ocr_texts = []
        if local_path.exists():
            try:
                results = reader.readtext(str(local_path))
                ocr_texts = [text for _, text, conf in results if conf > 0.3]
            except Exception as e:
                logger.warning(f"OCR failed for {local_path}: {e}")

        slides_analysis.append({
            "slide_index": img.slide_index,
            "image_path": img.raw_path,
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
    from app.models.post import CollectedPost
    from sqlalchemy.orm import selectinload

    topic = data.get("topic", "")
    tone = data.get("tone", "professional")
    slide_count = data.get("slide_count", 8)
    ref_ids = list(data.get("ref_ids", []))
    post_urls = data.get("post_urls") or []

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
        try:
            extracted = await extract_slides_from_post_images(
                image_urls,
                cache_key=f"post_{first.id}_{first.instagram_post_id}",
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
                        "gemini/gemini-2.0-flash",
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

    prompt = (
        f"한국어 이미지 검색 키워드를 받아 (1) 장소인지 일반(제품/개념)인지 분류하고 "
        f"(2) 검색에 쓸 다국어 변형을 생성합니다.\n\n"
        f"{ctx_line}"
        f"# 분류 규칙\n"
        f"- **place**: 카페, 식당, 공원, 거리, 호텔, 명소, 동네, 가게, 상점, 시장 등 위치에 묶인 것\n"
        f"- **general**: 제품, 과자, 화장품, 의류, 책, 가전, 일반 명사 등 어디서나 팔리는 것 / 추상 개념\n\n"
        f"# 변형 생성 규칙\n"
        f"- place 인 경우: 반드시 도시명 포함. native(현지 언어 표기) → en(영문) → ko(원문) 순으로 queries 배열\n"
        f"- general 인 경우: 브랜드/제품명 그대로(번역 X). 도시 제외. ko → en → native 순\n"
        f"- 브랜드명·고유명사는 어느 언어에서든 원래 표기 유지 (예: KINJI는 모든 언어에서 KINJI)\n"
        f"- 일본 → native는 漢字·かな, 프랑스 → French, 한국 → 한국어, 영어권 → English\n\n"
        f"# 출력 (단일 JSON 객체만)\n"
        f'  {{"kind": "place" | "general", "queries": ["...", "...", "..."], "country": "kr|jp|fr|us|..."}}\n\n'
        f"# 예시\n"
        f'  입력: "도쿄 요요기 공원" → {{"kind":"place","queries":["東京 代々木公園","tokyo yoyogi park","도쿄 요요기 공원"],"country":"jp"}}\n'
        f'  입력: "하라주쿠 KINJI 빈티지샵" → {{"kind":"place","queries":["原宿 KINJI 古着屋","harajuku KINJI vintage store","하라주쿠 KINJI 빈티지샵"],"country":"jp"}}\n'
        f'  입력: "메이지 아폴로 초콜릿" → {{"kind":"general","queries":["메이지 아폴로 초콜릿","meiji apollo chocolate","明治 アポロ チョコレート"],"country":"jp"}}\n'
        f'  입력: "코알라 노마치" → {{"kind":"general","queries":["코알라 노마치","koala no march","コアラのマーチ"],"country":"jp"}}\n'
        f'  입력: "파리 Café de Flore" → {{"kind":"place","queries":["Paris Café de Flore Saint-Germain","paris cafe de flore","파리 Café de Flore 생제르맹"],"country":"fr"}}\n\n'
        f'입력: "{q}"\n출력:'
    )
    try:
        raw = await _call_api(
            "gemini/gemini-2.0-flash",
            [{"role": "user", "content": prompt}],
            json_mode=True,
            max_tokens=512,
        )
        data_obj = _json.loads(raw) if isinstance(raw, str) else raw
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
        return {"kind": kind, "queries": queries, "country": country}
    except Exception as e:
        logger.exception("translate-keyword failed")
        # Defensive fallback — keep the original Korean as the single query.
        return {"kind": "general", "queries": [q], "country": "kr", "fallback_reason": str(e)[:120]}


class ParaphraseRequest(BaseModel):
    texts: list[str]
    tone: str = "marketing"  # "marketing" | "casual" | "punchy"


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
    from app.agents.llm_client import _call_api

    texts = [t for t in (body.texts or []) if isinstance(t, str)]
    if not texts:
        return {"paraphrased": []}

    numbered = "\n".join(f"{i+1}. {t}" for i, t in enumerate(texts))

    # User-supplied body wins when present — accounts that want a different
    # voice / set of rules can override without touching server code. The
    # input + JSON output framing is still added by the system so the LLM
    # response shape stays consistent regardless of what the user wrote.
    user_body = (getattr(user, "paraphrase_prompt", None) or "").strip()
    if user_body:
        body_text = user_body
    else:
        body_text = default_paraphrase_body(len(texts), body.tone)

    prompt = (
        f"{body_text}\n\n"
        f"입력:\n{numbered}\n\n"
        f"출력: 위 {len(texts)}개에 대응하는 JSON 배열만. 예: [\"새 표현1\", \"새 표현2\", ...]"
    )
    try:
        raw = await _call_api(
            "gemini/gemini-2.0-flash",
            [{"role": "user", "content": prompt}],
            json_mode=True,
            max_tokens=2048,
        )
        data_obj = _json.loads(raw) if isinstance(raw, str) else raw
        if isinstance(data_obj, dict):
            for key in ("paraphrased", "results", "data", "items"):
                if isinstance(data_obj.get(key), list):
                    data_obj = data_obj[key]
                    break
        if not isinstance(data_obj, list):
            raise ValueError(f"non-list response: {str(data_obj)[:120]}")
        out: list[str] = []
        for i, item in enumerate(data_obj):
            if isinstance(item, str):
                out.append(item.strip())
            elif isinstance(item, dict):
                out.append(str(item.get("text") or item.get("rewrite") or "").strip())
            else:
                out.append(texts[i] if i < len(texts) else "")
        # Pad/truncate to match input length so the caller can zip 1:1
        while len(out) < len(texts):
            out.append(texts[len(out)])
        out = out[: len(texts)]
        return {"paraphrased": out}
    except Exception as e:
        logger.exception("paraphrase failed")
        raise HTTPException(status_code=502, detail=f"문구 치환 실패: {e}")


class CaptionParaphraseRequest(BaseModel):
    caption: str
    topic: str = ""


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
    from app.agents.llm_client import _call_api

    raw_caption = (body.caption or "").strip()
    if not raw_caption:
        raise HTTPException(status_code=400, detail="캡션이 비어 있습니다")

    topic = (body.topic or "").strip()
    topic_line = f"주제 컨텍스트: {topic!r}\n\n" if topic else ""

    prompt = (
        f"인스타그램 카드뉴스의 한국어 캡션을 다시 써주세요. **출력은 100% 한국어로만**.\n\n"
        f"{topic_line}"
        f"# 출력 형식\n"
        f"단일 JSON 객체(배열 X, 마크다운 X)만 출력:\n"
        f'  {{"hook": "한국어 한 줄", "body": "한국어 본문"}}\n\n'
        f"# hook (첫 줄, 10자 이내)\n"
        f"- 인스타 캡션의 첫 줄은 미리보기에 보이는 부분. **사용자가 '더보기'를 누르게 만드는 미끼.**\n"
        f"- 독자의 **욕망·결핍·FOMO**를 자극: '나만 모르면 어쩌지', '나도 갖고 싶다', '안 가면 손해'\n"
        f"- 10자 이내 (공백 포함). 이모지 금지. 일반 명사구·평서문·반문형 모두 OK\n"
        f"- 캡션 본문 주제·청자를 읽고 그에 맞춰 작성\n"
        f"- 좋은 예 (구체적 갈증 자극):\n"
        f"  · 여행 캐러셀 → '현지인만 아는 곳', '여행 가기 전 필독', '관광객 1도 없음'\n"
        f"  · 쇼핑·맛집 → '직원만 아는 픽', '재고 떨어지기 전', '한국에 없음'\n"
        f"  · 정보·팁    → '다들 잘못 알고 있음', '이거 모르면 손해', '돈 아끼는 법'\n"
        f"  · 일반       → '저장 필수', '후회 없음', '진짜 있음'\n"
        f"- 나쁜 예: '여행의 마법', '꿈의 발견', '환상의 코스', '신세계' ← 추상·과장\n"
        f"- 나쁜 예: '재밌는 여행', '맛있는 간식' ← 평범, 후킹력 0\n\n"
        f"# body (본문, 원문과 같은 의미 다른 표현)\n"
        f"- 원문 캡션의 사실·제품명·브랜드·수치를 단어 그대로 유지\n"
        f"- 표현·접속사·문장 순서는 자연스럽게 변주\n"
        f"- 길이 원문 ±30% 이내\n\n"
        f"# ❌ 절대 금지 (AI 티)\n"
        f"- 느낌표(!) 전면 금지 — 평서문으로만 끝낼 것 (hook도 body도)\n"
        f"- 추상 명사: 마법·판타지·신세계·혁명·천국·꿀맛·완벽·발견\n"
        f"- 'X의 Y' 외침 패턴: '~의 마법', '~의 발견', '~의 매력'\n"
        f"- 정도부사 매우·정말·너무·대단히 남용\n"
        f"- 번역투: '~을 통해', '~에 대해', '~에 있어서', '~되어진다', '~할 수 있다'(단언 가능 시)\n"
        f"- 형식명사: '~다는 것이다', '~할 필요가 있다'\n"
        f"- 의성·의태 과장: 톡!, 폭발!, 귀여움 폭발\n\n"
        f"# 원문 캡션\n{raw_caption}\n\n"
        f"위 규칙에 따라 JSON만 출력:"
    )
    try:
        raw = await _call_api(
            "gemini/gemini-2.0-flash",
            [{"role": "user", "content": prompt}],
            json_mode=True,
            max_tokens=2048,
        )
        data_obj = _json.loads(raw) if isinstance(raw, str) else raw
        # LLM occasionally wraps the object in a 1-element array. Unwrap.
        if isinstance(data_obj, list) and len(data_obj) == 1 and isinstance(data_obj[0], dict):
            data_obj = data_obj[0]
        if not isinstance(data_obj, dict):
            raise ValueError(f"non-dict response: {str(data_obj)[:120]}")
        hook = str(data_obj.get("hook") or "").strip()
        body_text = str(data_obj.get("body") or "").strip()
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
        raise HTTPException(status_code=502, detail=f"캡션 치환 실패: {e}")


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
