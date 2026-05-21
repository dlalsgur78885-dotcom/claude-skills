"""AI content generation service — uses unified LLM client (CLI-first)."""

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


class ContentGenerator:
    """Generates carousel text content using the unified LLM client."""

    async def generate_slides(
        self,
        source_post_id: int | None = None,
        topic: str = "",
        tone: str = "professional",
        slide_count: int = 8,
    ) -> dict:
        """Generate slide text content for a carousel."""
        from app.agents.llm_client import llm_json

        try:
            prompt = self._build_slide_prompt(topic, tone, slide_count)
            slides = await llm_json(
                model="gemini-flash",
                messages=[{"role": "user", "content": prompt}],
            )

            if isinstance(slides, dict) and "raw" in slides:
                slides = self._fallback_slides(slide_count)

            if not isinstance(slides, list):
                slides = self._fallback_slides(slide_count)

            slides = self._normalize_slide_types(slides)

            return {
                "title": slides[0]["headline"] if slides else topic,
                "slides": slides,
                "caption": self._generate_caption_text(topic, slides),
                "hashtags": self._extract_hashtags(topic),
            }
        except Exception as e:
            logger.error(f"Content generation error: {e}")
            return {"error": str(e), "slides": []}

    def _build_slide_prompt(self, topic: str, tone: str, count: int) -> str:
        tone_map = {
            "professional": "전문적이고 신뢰감 있는",
            "casual": "친근하고 가벼운",
            "educational": "교육적이고 정보 중심의",
            "viral": "눈길을 끌고 공유하고 싶은",
        }
        tone_desc = tone_map.get(tone, tone)

        return f"""인스타그램 카드뉴스(캐러셀) 콘텐츠를 만들어주세요.

주제: {topic}
톤: {tone_desc}
슬라이드 수: {count}장

다음 JSON 형식으로 정확히 출력해주세요:
[
  {{"index": 0, "type": "cover", "headline": "표지 제목 (15자 이내)", "subtext": "부제목 (20자 이내)"}},
  {{"index": 1, "type": "content", "headline": "소제목 (15자 이내)", "body": "본문 (50자 이내)"}},
  ...
  {{"index": {count - 1}, "type": "cta", "headline": "CTA 제목", "body": "행동 유도 문구", "cta_text": "버튼 텍스트"}}
]

규칙:
- 첫 슬라이드는 반드시 type: "cover"
- 마지막 슬라이드는 반드시 type: "cta"
- 나머지는 type: "content"
- JSON만 출력, 다른 텍스트 없이"""

    def _normalize_slide_types(self, slides: list[dict]) -> list[dict]:
        """Force a sane `type` per slide POSITION, regardless of what the LLM
        returned.

        A cover is the title slide — only the slide at index 0 can be one. An
        LLM that labels every slide "cover" (it happens, especially for terse
        topics) would produce a carousel with zero content slides, which makes
        downstream layout picking meaningless — the exact failure already
        fixed for the Vision path in content_extractor. This is the LLM-path
        counterpart so BOTH carousel-creation paths are covered.

        Only `cover` is corrected here: index 0 is forced to cover, and any
        cover at index 1+ is demoted to content. `cta` is left to the LLM —
        the prompt already asks for a trailing cta and there's no positional
        rule that makes a middle slide definitely-not-cta.
        """
        for i, s in enumerate(slides):
            if not isinstance(s, dict):
                continue
            t = str(s.get("type") or "").strip().lower()
            if i == 0:
                t = "cover"
            elif t == "cover":
                t = "content"
            elif t not in ("content", "cta"):
                t = "content"
            s["type"] = t
        return slides

    def _fallback_slides(self, expected_count: int) -> list[dict]:
        """Generate default slides when LLM fails."""
        slides = [
            {"index": 0, "type": "cover", "headline": "제목을 입력하세요", "subtext": "부제목"},
        ]
        for i in range(1, expected_count - 1):
            slides.append({
                "index": i,
                "type": "content",
                "headline": f"포인트 {i}",
                "body": "내용을 입력하세요",
            })
        slides.append({
            "index": expected_count - 1,
            "type": "cta",
            "headline": "더 알아보기",
            "body": "팔로우하고 더 많은 정보를 받아보세요",
            "cta_text": "팔로우",
        })
        return slides

    def _generate_caption_text(self, topic: str, slides: list[dict]) -> str:
        headlines = [s.get("headline", "") for s in slides if s.get("headline")]
        return f"📌 {topic}\n\n" + "\n".join(f"✅ {h}" for h in headlines[:5])

    def _extract_hashtags(self, topic: str) -> list[str]:
        words = topic.replace(",", " ").split()
        return [f"#{w}" for w in words if len(w) > 1][:10]

    async def rewrite_slide(
        self, carousel_id: int, slide_index: int, instruction: str
    ) -> dict:
        """Rewrite a specific slide based on instruction."""
        return {"carousel_id": carousel_id, "slide_index": slide_index, "updated": True}

    async def generate_caption(
        self, carousel_id: int, tone: str = "professional", include_hashtags: bool = True
    ) -> dict:
        """Generate Instagram caption for a carousel."""
        return {"carousel_id": carousel_id, "caption": "", "hashtags": []}

    async def analyze_benchmark(self, post_ids: list[int]) -> dict:
        """Analyze benchmark posts for content patterns."""
        return {
            "post_count": len(post_ids),
            "avg_slide_count": 0,
            "common_structure": [],
            "tone_analysis": "",
        }
