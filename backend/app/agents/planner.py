"""Planner agent - creates execution plans and delegates to workers."""

from typing import Any

from app.agents.base import (
    AgentRole,
    BaseAgent,
    Plan,
    PlanStep,
    PlanStatus,
    StepStatus,
)


class PlannerAgent(BaseAgent):
    """Analyzes user requests and creates structured execution plans."""

    def __init__(self):
        super().__init__(AgentRole.PLANNER)

    async def execute(self, user_request: str, context: dict | None = None) -> Plan:
        """Create an execution plan from a user request."""
        plan = self._parse_request(user_request, context or {})
        plan.status = PlanStatus.CREATED
        return plan

    async def revise_plan(self, plan: Plan, evaluation: dict) -> Plan:
        """Revise a plan based on evaluator feedback."""
        retry_steps = evaluation.get("retry_steps", [])

        for step in plan.steps:
            if step.step_id in retry_steps:
                step.status = StepStatus.PENDING
                step.result = None
                step.error = None

                # Apply suggestions from evaluation
                step_eval = next(
                    (
                        e
                        for e in evaluation.get("step_evaluations", [])
                        if e.get("step_id") == step.step_id
                    ),
                    None,
                )
                if step_eval and step_eval.get("suggestions"):
                    step.params["_retry_hints"] = step_eval["suggestions"]

        plan.status = PlanStatus.CREATED
        return plan

    def _parse_request(self, request: str, context: dict) -> Plan:
        """Parse a user request into a structured plan.

        This implements rule-based plan generation. For complex requests,
        this can be extended to use LLM-based planning.
        """
        request_lower = request.lower()

        # Pattern: scrape/collect from channel
        if any(kw in request_lower for kw in ["수집", "스크래핑", "scrape", "크롤링"]):
            return self._plan_scrape(request, context)

        # Pattern: generate/create carousel
        if any(kw in request_lower for kw in ["만들", "생성", "generate", "create"]):
            return self._plan_generate(request, context)

        # Pattern: process images
        if any(kw in request_lower for kw in ["이미지", "누끼", "배경", "image", "process"]):
            return self._plan_process_images(request, context)

        # Pattern: discover/find channels
        if any(kw in request_lower for kw in ["찾", "탐색", "discover", "search"]):
            return self._plan_discover(request, context)

        # Default: full pipeline
        return self._plan_full_pipeline(request, context)

    def _plan_scrape(self, request: str, context: dict) -> Plan:
        handle = context.get("handle", "")
        limit = context.get("limit", 10)

        return Plan(
            goal=f"채널 '{handle}' 소재 수집" if handle else "채널 소재 수집",
            steps=[
                PlanStep(
                    step_id=1,
                    worker="scraper",
                    action="scrape_channel_posts",
                    params={"handle": handle, "limit": limit},
                    priority="high",
                ),
                PlanStep(
                    step_id=2,
                    worker="image_processor",
                    action="download_and_process",
                    params={"source": "step_1"},
                    depends_on=[1],
                    priority="high",
                ),
            ],
            success_criteria="포스트 수집 완료 및 이미지 처리 성공률 80% 이상",
        )

    def _plan_generate(self, request: str, context: dict) -> Plan:
        source_post_id = context.get("source_post_id")
        topic = context.get("topic", "")
        template = context.get("template", "minimal")

        return Plan(
            goal=f"'{topic}' 주제 캐러셀 생성",
            steps=[
                PlanStep(
                    step_id=1,
                    worker="content_generator",
                    action="generate_slide_text",
                    params={
                        "source_post_id": source_post_id,
                        "topic": topic,
                        "tone": context.get("tone", "professional"),
                    },
                    priority="high",
                ),
                PlanStep(
                    step_id=2,
                    worker="designer",
                    action="create_carousel",
                    params={"template": template},
                    depends_on=[1],
                    priority="high",
                ),
            ],
            success_criteria="슬라이드 텍스트 생성 및 디자인 데이터 생성 완료",
        )

    def _plan_process_images(self, request: str, context: dict) -> Plan:
        post_ids = context.get("post_ids", [])

        return Plan(
            goal="이미지 처리 (리사이즈 + 배경 제거)",
            steps=[
                PlanStep(
                    step_id=1,
                    worker="image_processor",
                    action="download_and_process",
                    params={"post_ids": post_ids},
                    priority="high",
                ),
            ],
            success_criteria="모든 이미지 처리 완료, 배경 제거 성공률 90% 이상",
        )

    def _plan_discover(self, request: str, context: dict) -> Plan:
        keywords = context.get("keywords", [])
        style = context.get("style", "")

        return Plan(
            goal="벤치마크 채널 탐색",
            steps=[
                PlanStep(
                    step_id=1,
                    worker="scraper",
                    action="discover_channels",
                    params={"keywords": keywords, "style": style},
                    priority="medium",
                ),
            ],
            success_criteria="관련 채널 5개 이상 발견",
        )

    def _plan_full_pipeline(self, request: str, context: dict) -> Plan:
        handle = context.get("handle", "")
        topic = context.get("topic", "")

        return Plan(
            goal=f"전체 파이프라인: '{handle}' 수집 → '{topic}' 캐러셀 생성",
            steps=[
                PlanStep(
                    step_id=1,
                    worker="scraper",
                    action="scrape_channel_posts",
                    params={"handle": handle, "limit": 5},
                    priority="high",
                ),
                PlanStep(
                    step_id=2,
                    worker="image_processor",
                    action="download_and_process",
                    params={"source": "step_1"},
                    depends_on=[1],
                    priority="high",
                ),
                PlanStep(
                    step_id=3,
                    worker="content_generator",
                    action="generate_slide_text",
                    params={"topic": topic},
                    depends_on=[1],
                    priority="high",
                ),
                PlanStep(
                    step_id=4,
                    worker="designer",
                    action="create_carousel",
                    params={"template": "minimal"},
                    depends_on=[2, 3],
                    priority="high",
                ),
            ],
            success_criteria="소재 수집, 이미지 처리, 텍스트 생성, 디자인 모두 완료",
        )
