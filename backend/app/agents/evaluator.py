"""Evaluator agent - validates execution results and provides feedback."""

from typing import Any

from app.agents.base import (
    AgentRole,
    BaseAgent,
    Evaluation,
    Plan,
    StepStatus,
)


class EvaluatorAgent(BaseAgent):
    """Evaluates worker results against plan criteria."""

    def __init__(self):
        super().__init__(AgentRole.EVALUATOR)

    async def execute(self, plan: Plan, **kwargs) -> Evaluation:
        """Evaluate a completed plan's results."""
        evaluation = Evaluation(plan_id=plan.plan_id)
        step_evaluations = []

        for step in plan.steps:
            step_eval = self._evaluate_step(step)
            step_evaluations.append(step_eval)

        evaluation.step_evaluations = step_evaluations

        # Calculate overall score
        scores = [e["score"] for e in step_evaluations if e["score"] is not None]
        evaluation.overall_score = sum(scores) / len(scores) if scores else 0.0

        # Determine overall status
        if evaluation.overall_score >= 0.8:
            evaluation.overall_status = "success"
        elif evaluation.overall_score >= 0.5:
            evaluation.overall_status = "partial"
        else:
            evaluation.overall_status = "failed"

        # Identify retry candidates
        evaluation.retry_steps = [
            e["step_id"]
            for e in step_evaluations
            if e["status"] in ("failed", "partial") and e["score"] < 0.8
        ]
        evaluation.retry_recommended = len(evaluation.retry_steps) > 0

        evaluation.summary = self._generate_summary(evaluation)

        return evaluation

    def _evaluate_step(self, step) -> dict:
        """Evaluate a single plan step."""
        eval_result = {
            "step_id": step.step_id,
            "worker": step.worker,
            "action": step.action,
            "status": step.status.value,
            "score": None,
            "details": "",
            "issues": [],
            "suggestions": [],
        }

        if step.status == StepStatus.SUCCESS:
            eval_result["score"] = self._score_result(step)
            eval_result["details"] = self._detail_result(step)
        elif step.status == StepStatus.FAILED:
            eval_result["score"] = 0.0
            eval_result["details"] = f"실패: {step.error or '알 수 없는 오류'}"
            eval_result["issues"] = [step.error or "실행 실패"]
            eval_result["suggestions"] = self._suggest_fix(step)
        elif step.status == StepStatus.PENDING:
            eval_result["score"] = None
            eval_result["details"] = "미실행"
        else:
            eval_result["score"] = 0.0
            eval_result["details"] = f"상태: {step.status.value}"

        return eval_result

    def _score_result(self, step) -> float:
        """Score a successful step result based on worker-specific criteria."""
        result = step.result
        if result is None:
            return 0.5

        worker = step.worker
        action = step.action

        if worker == "scraper":
            return self._score_scrape(result, step.params)
        elif worker == "image_processor":
            return self._score_image_processing(result, step.params)
        elif worker == "content_generator":
            return self._score_content(result, step.params)
        elif worker == "designer":
            return self._score_design(result, step.params)

        return 0.8  # Default score for unknown workers

    def _score_scrape(self, result: Any, params: dict) -> float:
        """Evaluate scraping results."""
        if not isinstance(result, dict):
            return 0.5

        requested = params.get("limit", 10)
        collected = result.get("post_count", 0)

        if collected == 0:
            return 0.0

        ratio = min(collected / requested, 1.0)

        # Check data completeness
        has_images = result.get("images_found", 0) > 0
        has_captions = result.get("captions_found", 0) > 0

        score = ratio * 0.5
        if has_images:
            score += 0.3
        if has_captions:
            score += 0.2

        return min(score, 1.0)

    def _score_image_processing(self, result: Any, params: dict) -> float:
        """Evaluate image processing results."""
        if not isinstance(result, dict):
            return 0.5

        total = result.get("total_images", 0)
        processed = result.get("processed_count", 0)
        bg_removed = result.get("bg_removed_count", 0)

        if total == 0:
            return 0.0

        process_ratio = processed / total
        bg_ratio = bg_removed / total if total > 0 else 0

        return process_ratio * 0.6 + bg_ratio * 0.4

    def _score_content(self, result: Any, params: dict) -> float:
        """Evaluate content generation results."""
        if not isinstance(result, dict):
            return 0.5

        slides = result.get("slides", [])
        requested_count = params.get("slide_count", 8)

        if not slides:
            return 0.0

        # Slide count adequacy
        count_score = min(len(slides) / requested_count, 1.0)

        # Check structure completeness
        has_cover = any(s.get("type") == "cover" for s in slides)
        has_cta = any(s.get("type") == "cta" for s in slides)
        has_caption = bool(result.get("caption"))

        structure_score = sum([has_cover, has_cta, has_caption]) / 3

        return count_score * 0.5 + structure_score * 0.5

    def _score_design(self, result: Any, params: dict) -> float:
        """Evaluate design results."""
        if not isinstance(result, dict):
            return 0.5

        slides = result.get("canvas_slides", [])
        if not slides:
            return 0.0

        # Check each slide has required elements
        valid_slides = sum(
            1
            for s in slides
            if s.get("objects") and len(s["objects"]) > 0
        )

        return valid_slides / len(slides) if slides else 0.0

    def _detail_result(self, step) -> str:
        """Generate human-readable details for a step result."""
        result = step.result
        if not isinstance(result, dict):
            return "결과 확인 완료"

        worker = step.worker
        if worker == "scraper":
            return f"포스트 {result.get('post_count', 0)}개 수집, 이미지 {result.get('images_found', 0)}개 발견"
        elif worker == "image_processor":
            return f"이미지 {result.get('processed_count', 0)}/{result.get('total_images', 0)}개 처리, 배경제거 {result.get('bg_removed_count', 0)}개"
        elif worker == "content_generator":
            return f"슬라이드 {len(result.get('slides', []))}개 텍스트 생성"
        elif worker == "designer":
            return f"캐러셀 {len(result.get('canvas_slides', []))}장 디자인 생성"

        return "완료"

    def _suggest_fix(self, step) -> list[str]:
        """Suggest fixes for failed steps."""
        error = step.error or ""
        worker = step.worker

        if worker == "scraper":
            if "login" in error.lower() or "session" in error.lower():
                return ["인스타그램 세션 재설정 필요", "쿠키를 삭제하고 다시 로그인"]
            if "429" in error or "rate" in error.lower():
                return ["스크래핑 속도를 낮추세요", "30분 후 재시도 권장"]
            return ["네트워크 연결 확인", "채널 핸들이 올바른지 확인"]

        if worker == "image_processor":
            if "memory" in error.lower():
                return ["이미지 배치 크기를 줄이세요", "한 번에 5장씩 처리"]
            return ["이미지 URL이 유효한지 확인", "디스크 공간 확인"]

        if worker == "content_generator":
            if "api" in error.lower() or "key" in error.lower():
                return ["Google API 키 확인", ".env 파일에 GOOGLE_API_KEY 설정"]
            return ["입력 텍스트가 충분한지 확인", "다른 톤으로 재시도"]

        return ["로그를 확인하세요"]

    def _generate_summary(self, evaluation: Evaluation) -> str:
        """Generate a human-readable evaluation summary."""
        total = len(evaluation.step_evaluations)
        success = sum(1 for e in evaluation.step_evaluations if e["status"] == "success")
        failed = sum(1 for e in evaluation.step_evaluations if e["status"] == "failed")

        summary = f"전체 {total}단계 중 {success}단계 성공"
        if failed > 0:
            summary += f", {failed}단계 실패"
        summary += f" (점수: {evaluation.overall_score:.0%})"

        if evaluation.retry_recommended:
            summary += f" → {len(evaluation.retry_steps)}단계 재시도 권장"

        return summary
