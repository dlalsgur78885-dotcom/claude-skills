"""Worker agents - execute specific tasks delegated by the Planner."""

import logging
from typing import Any

from app.agents.base import AgentRole, BaseAgent

logger = logging.getLogger(__name__)


class ScraperWorker(BaseAgent):
    """Scrapes Instagram channels and posts."""

    def __init__(self):
        super().__init__(AgentRole.SCRAPER)

    async def execute(self, action: str, params: dict, **kwargs) -> Any:
        handler = getattr(self, f"_action_{action}", None)
        if not handler:
            raise ValueError(f"Unknown scraper action: {action}")
        return await handler(params)

    async def _action_scrape_channel_posts(self, params: dict) -> dict:
        """Scrape posts from an Instagram channel."""
        # Implementation will use Playwright - stub for now
        from app.services.instagram import InstagramScraper

        scraper = InstagramScraper()
        return await scraper.scrape_channel(
            handle=params["handle"],
            limit=params.get("limit", 10),
            since=params.get("since"),
        )

    async def _action_scrape_single_post(self, params: dict) -> dict:
        from app.services.instagram import InstagramScraper

        scraper = InstagramScraper()
        return await scraper.scrape_post(params["post_url"])

    async def _action_discover_channels(self, params: dict) -> dict:
        from app.services.instagram import InstagramScraper

        scraper = InstagramScraper()
        return await scraper.discover_channels(
            keywords=params.get("keywords", []),
            style=params.get("style", ""),
        )

    async def _action_check_session(self, params: dict) -> dict:
        from app.services.instagram import InstagramScraper

        scraper = InstagramScraper()
        return await scraper.check_session()


class ImageProcessorWorker(BaseAgent):
    """Processes images: download, resize, background removal."""

    def __init__(self):
        super().__init__(AgentRole.IMAGE_PROCESSOR)

    async def execute(self, action: str, params: dict, **kwargs) -> Any:
        handler = getattr(self, f"_action_{action}", None)
        if not handler:
            raise ValueError(f"Unknown image_processor action: {action}")
        return await handler(params)

    async def _action_download_images(self, params: dict) -> dict:
        from app.services.image_processor import ImageProcessor

        processor = ImageProcessor()
        return await processor.download_images(
            post_id=params["post_id"],
            image_urls=params["image_urls"],
        )

    async def _action_remove_background(self, params: dict) -> dict:
        from app.services.image_processor import ImageProcessor

        processor = ImageProcessor()
        return await processor.remove_background(
            image_paths=params["image_paths"],
            output_format=params.get("output_format", "png"),
        )

    async def _action_resize_images(self, params: dict) -> dict:
        from app.services.image_processor import ImageProcessor

        processor = ImageProcessor()
        return await processor.resize_images(
            image_paths=params["image_paths"],
            max_width=params.get("max_width", 1080),
            max_height=params.get("max_height", 1350),
        )

    async def _action_download_and_process(self, params: dict) -> dict:
        from app.services.image_processor import ImageProcessor

        processor = ImageProcessor()
        return await processor.download_and_process(
            post_ids=params.get("post_ids", []),
        )


class ContentGeneratorWorker(BaseAgent):
    """Generates carousel text content using AI."""

    def __init__(self):
        super().__init__(AgentRole.CONTENT_GENERATOR)

    async def execute(self, action: str, params: dict, **kwargs) -> Any:
        handler = getattr(self, f"_action_{action}", None)
        if not handler:
            raise ValueError(f"Unknown content_generator action: {action}")
        return await handler(params)

    async def _action_generate_slide_text(self, params: dict) -> dict:
        from app.services.content_gen import ContentGenerator

        generator = ContentGenerator()
        return await generator.generate_slides(
            source_post_id=params.get("source_post_id"),
            topic=params.get("topic", ""),
            tone=params.get("tone", "professional"),
            slide_count=params.get("slide_count", 8),
        )

    async def _action_rewrite_slide(self, params: dict) -> dict:
        from app.services.content_gen import ContentGenerator

        generator = ContentGenerator()
        return await generator.rewrite_slide(
            carousel_id=params["carousel_id"],
            slide_index=params["slide_index"],
            instruction=params["instruction"],
        )

    async def _action_generate_caption(self, params: dict) -> dict:
        from app.services.content_gen import ContentGenerator

        generator = ContentGenerator()
        return await generator.generate_caption(
            carousel_id=params["carousel_id"],
            tone=params.get("tone", "professional"),
            include_hashtags=params.get("include_hashtags", True),
        )

    async def _action_analyze_benchmark(self, params: dict) -> dict:
        from app.services.content_gen import ContentGenerator

        generator = ContentGenerator()
        return await generator.analyze_benchmark(
            post_ids=params.get("post_ids", []),
        )


class DesignerWorker(BaseAgent):
    """Creates carousel design data (Fabric.js JSON)."""

    def __init__(self):
        super().__init__(AgentRole.DESIGNER)

    async def execute(self, action: str, params: dict, **kwargs) -> Any:
        handler = getattr(self, f"_action_{action}", None)
        if not handler:
            raise ValueError(f"Unknown designer action: {action}")
        return await handler(params)

    async def _action_create_carousel(self, params: dict) -> dict:
        from app.services.carousel_designer import CarouselDesigner

        designer = CarouselDesigner()
        return await designer.create_carousel(
            text_data=params.get("text_data", {}),
            image_paths=params.get("image_paths", []),
            template=params.get("template", "minimal"),
            canvas_size=params.get("canvas_size", {"width": 1080, "height": 1080}),
        )

    async def _action_apply_template(self, params: dict) -> dict:
        from app.services.carousel_designer import CarouselDesigner

        designer = CarouselDesigner()
        return await designer.apply_template(
            carousel_id=params["carousel_id"],
            template=params["template"],
        )

    async def _action_suggest_layout(self, params: dict) -> dict:
        from app.services.carousel_designer import CarouselDesigner

        designer = CarouselDesigner()
        return await designer.suggest_layout(
            slide_text=params.get("slide_text", ""),
            has_image=params.get("has_image", False),
            style_preference=params.get("style_preference", ""),
        )


class BenchmarkAnalystWorker(BaseAgent):
    """수집된 소재를 분석하여 성공 패턴을 추출한다."""

    def __init__(self):
        super().__init__(AgentRole.BENCHMARK_ANALYST)

    async def execute(self, action: str, params: dict, **kwargs) -> Any:
        handler = getattr(self, f"_action_{action}", None)
        if not handler:
            raise ValueError(f"Unknown benchmark_analyst action: {action}")
        return await handler(params)

    async def _action_analyze_top_posts(self, params: dict) -> dict:
        """좋아요/댓글 상위 포스트의 공통 패턴 분석."""
        from sqlalchemy import select
        from app.database import async_session
        from app.models.post import CollectedPost

        async with async_session() as db:
            query = (
                select(CollectedPost)
                .order_by(CollectedPost.like_count.desc())
                .limit(params.get("top_n", 20))
            )
            if params.get("channel_id"):
                query = query.where(CollectedPost.channel_id == params["channel_id"])
            result = await db.execute(query)
            posts = result.scalars().all()

        if not posts:
            return {"error": "분석할 포스트가 없습니다"}

        post_data = [
            {
                "caption": p.caption[:200],
                "like_count": p.like_count,
                "comment_count": p.comment_count,
                "slide_count": p.slide_count,
                "hashtags": p.hashtags,
            }
            for p in posts
        ]

        prompt = f"""다음은 인스타그램 인기 카드뉴스 포스트 {len(post_data)}개입니다.
공통 성공 패턴을 분석해주세요.

포스트 데이터:
{post_data}

다음 JSON 형식으로 출력:
{{
  "avg_likes": 평균 좋아요,
  "avg_comments": 평균 댓글,
  "avg_slides": 평균 슬라이드 수,
  "common_hashtags": ["자주 쓰이는 해시태그 top 10"],
  "caption_patterns": ["캡션에서 발견된 패턴들"],
  "content_themes": ["주요 주제/테마"],
  "hook_styles": ["첫 문장 후킹 스타일"],
  "recommendations": ["캐러셀 제작 시 추천사항"]
}}"""

        try:
            return await self.ask_llm_json(prompt)
        except Exception as e:
            logger.error(f"Benchmark analysis error: {e}")
            return {"error": str(e), "post_count": len(posts)}

    async def _action_compare_channels(self, params: dict) -> dict:
        """채널 간 성과 비교 분석."""
        from sqlalchemy import select, func
        from app.database import async_session
        from app.models.post import CollectedPost
        from app.models.channel import BenchmarkChannel

        async with async_session() as db:
            result = await db.execute(
                select(
                    BenchmarkChannel.instagram_handle,
                    func.avg(CollectedPost.like_count).label("avg_likes"),
                    func.avg(CollectedPost.comment_count).label("avg_comments"),
                    func.count(CollectedPost.id).label("post_count"),
                )
                .join(CollectedPost)
                .group_by(BenchmarkChannel.id)
            )
            rows = result.all()

        return {
            "channels": [
                {
                    "handle": r[0],
                    "avg_likes": round(r[1] or 0),
                    "avg_comments": round(r[2] or 0),
                    "post_count": r[3],
                }
                for r in rows
            ]
        }


class CopywriterWorker(BaseAgent):
    """브랜드 톤에 맞게 카피를 다듬고 최적화한다."""

    def __init__(self):
        super().__init__(AgentRole.COPYWRITER)

    async def execute(self, action: str, params: dict, **kwargs) -> Any:
        handler = getattr(self, f"_action_{action}", None)
        if not handler:
            raise ValueError(f"Unknown copywriter action: {action}")
        return await handler(params)

    async def _action_refine_slides(self, params: dict) -> dict:
        """슬라이드 카피를 톤/브랜드에 맞게 다듬기."""
        slides = params.get("slides", [])
        tone = params.get("tone", "professional")
        brand_voice = params.get("brand_voice", "")

        prompt = f"""인스타그램 카드뉴스 슬라이드 카피를 다듬어주세요.

톤: {tone}
{f'브랜드 보이스: {brand_voice}' if brand_voice else ''}

현재 슬라이드:
{slides}

규칙:
- 표지 headline: 15자 이내, 강렬한 후킹
- content headline: 12자 이내
- content body: 40자 이내 (한 눈에 읽히게)
- CTA: 행동을 유도하는 직접적 표현
- 이모지는 최소한으로

동일한 JSON 배열 형식으로 다듬어진 슬라이드를 출력해주세요."""

        try:
            return {"slides": await self.ask_llm_json(prompt)}
        except Exception as e:
            logger.error(f"Copywriter refine error: {e}")
            return {"slides": slides, "error": str(e)}

    async def _action_generate_hooks(self, params: dict) -> dict:
        """주제에 대한 후킹 문구 후보 생성."""
        topic = params.get("topic", "")
        count = params.get("count", 5)

        prompt = f"""인스타그램 카드뉴스 표지에 쓸 후킹 문구 {count}개를 만들어주세요.

주제: {topic}

규칙:
- 15자 이내
- 스크롤을 멈추게 하는 문구
- 궁금증/공감/충격 유발

JSON 배열로 출력: ["문구1", "문구2", ...]"""

        try:
            return {"hooks": await self.ask_llm_json(prompt)}
        except Exception as e:
            logger.error(f"Hook generation error: {e}")
            return {"hooks": [], "error": str(e)}

    async def _action_generate_caption(self, params: dict) -> dict:
        """인스타그램 게시글 캡션 생성."""
        slides = params.get("slides", [])
        tone = params.get("tone", "professional")
        include_hashtags = params.get("include_hashtags", True)

        headlines = [s.get("headline", "") for s in slides if s.get("headline")]

        prompt = f"""인스타그램 캐러셀 게시글 캡션을 작성해주세요.

슬라이드 제목들: {headlines}
톤: {tone}

규칙:
- 첫 줄은 강렬한 후킹 (접히기 전에 보이는 부분)
- 본문은 3-5줄
- {'해시태그 10-15개 포함' if include_hashtags else '해시태그 없이'}

JSON으로 출력: {{"caption": "캡션 텍스트", "hashtags": ["태그1", "태그2"]}}"""

        try:
            return await self.ask_llm_json(prompt)
        except Exception as e:
            logger.error(f"Caption generation error: {e}")
            return {"caption": "", "hashtags": [], "error": str(e)}


class ImageSourcerWorker(BaseAgent):
    """주제에 맞는 이미지를 검색하고 소싱한다."""

    def __init__(self):
        super().__init__(AgentRole.IMAGE_SOURCER)

    async def execute(self, action: str, params: dict, **kwargs) -> Any:
        handler = getattr(self, f"_action_{action}", None)
        if not handler:
            raise ValueError(f"Unknown image_sourcer action: {action}")
        return await handler(params)

    async def _action_generate_search_keywords(self, params: dict) -> dict:
        """슬라이드 내용에서 이미지 검색 키워드 추출."""
        slides = params.get("slides", [])

        prompt = f"""카드뉴스 슬라이드 내용을 보고, 각 슬라이드에 어울리는 투명 배경 이미지 검색 키워드를 영어로 만들어주세요.

슬라이드:
{slides}

규칙:
- 투명 PNG로 찾을 수 있는 구체적 오브젝트 (예: "airplane icon", "coffee cup cutout")
- 추상적 배경이 아닌 구체적 사물/아이콘
- 슬라이드당 키워드 2-3개

JSON으로 출력:
[{{"slide_index": 0, "keywords": ["keyword1", "keyword2"]}}, ...]"""

        try:
            return {"keyword_map": await self.ask_llm_json(prompt)}
        except Exception as e:
            logger.error(f"Keyword generation error: {e}")
            return {"keyword_map": [], "error": str(e)}

    async def _action_source_images(self, params: dict) -> dict:
        """키워드로 이미지를 검색하고 다운로드."""
        from app.services.image_processor import ImageProcessor

        keyword_map = params.get("keyword_map", [])
        processor = ImageProcessor()
        results = []

        for entry in keyword_map:
            slide_idx = entry.get("slide_index", 0)
            keywords = entry.get("keywords", [])

            for kw in keywords:
                try:
                    found = await processor.find_cutout_images(
                        query=kw,
                        limit=params.get("per_keyword", 2),
                    )
                    if found:
                        results.append({
                            "slide_index": slide_idx,
                            "keyword": kw,
                            "images": found,
                        })
                        break
                except Exception as e:
                    logger.warning(f"Image search failed for '{kw}': {e}")

        return {"sourced_images": results, "total": len(results)}


class PublisherWorker(BaseAgent):
    """완성된 캐러셀을 이미지로 렌더링하고 인스타그램에 발행한다."""

    def __init__(self):
        super().__init__(AgentRole.PUBLISHER)

    async def execute(self, action: str, params: dict, **kwargs) -> Any:
        handler = getattr(self, f"_action_{action}", None)
        if not handler:
            raise ValueError(f"Unknown publisher action: {action}")
        return await handler(params)

    async def _action_render_slides(self, params: dict) -> dict:
        """Fabric.js canvas JSON을 이미지 파일로 렌더링."""
        carousel_id = params.get("carousel_id")
        if not carousel_id:
            return {"error": "carousel_id 필요"}

        from sqlalchemy import select
        from app.database import async_session
        from app.models.carousel import GeneratedCarousel

        async with async_session() as db:
            result = await db.execute(
                select(GeneratedCarousel).where(GeneratedCarousel.id == carousel_id)
            )
            carousel = result.scalar_one_or_none()

        if not carousel:
            return {"error": f"캐러셀 {carousel_id}를 찾을 수 없습니다"}

        canvas_data = carousel.canvas_data or {}
        slides = canvas_data.get("canvas_slides", [])

        # TODO: Fabric.js 서버사이드 렌더링 (node canvas 또는 puppeteer)
        output_dir = f"data/images/output/{carousel_id}"
        return {
            "carousel_id": carousel_id,
            "slide_count": len(slides),
            "output_dir": output_dir,
            "rendered": False,
            "message": "서버사이드 렌더링 미구현 - 프론트엔드에서 내보내기 사용",
        }

    async def _action_publish_to_instagram(self, params: dict) -> dict:
        """Meta Graph API로 인스타그램에 캐러셀 발행."""
        from app.config import settings

        if not settings.INSTAGRAM_ACCESS_TOKEN:
            return {"error": "INSTAGRAM_ACCESS_TOKEN이 설정되지 않았습니다"}

        carousel_id = params.get("carousel_id")
        caption = params.get("caption", "")
        image_urls = params.get("image_urls", [])

        if not image_urls:
            return {"error": "발행할 이미지 URL이 없습니다"}

        # TODO: Meta Graph API 캐러셀 발행 구현
        # 1. 각 이미지를 media container로 생성
        # 2. 캐러셀 container 생성
        # 3. 발행
        return {
            "carousel_id": carousel_id,
            "published": False,
            "message": "Meta Graph API 발행 미구현",
        }

    async def _action_schedule_publish(self, params: dict) -> dict:
        """예약 발행 설정."""
        return {
            "carousel_id": params.get("carousel_id"),
            "scheduled_at": params.get("scheduled_at"),
            "scheduled": False,
            "message": "예약 발행 미구현",
        }
