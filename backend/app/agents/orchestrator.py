"""Orchestrator - coordinates Planner, Workers, and Evaluator in a loop."""

import asyncio
import logging
from datetime import datetime
from typing import Any

from app.agents.base import Plan, PlanStatus, StepStatus
from app.agents.planner import PlannerAgent
from app.agents.evaluator import EvaluatorAgent
from app.agents.workers import (
    ScraperWorker,
    ImageProcessorWorker,
    ContentGeneratorWorker,
    DesignerWorker,
    BenchmarkAnalystWorker,
    CopywriterWorker,
    ImageSourcerWorker,
    PublisherWorker,
)

logger = logging.getLogger(__name__)

MAX_RETRIES = 2


class Orchestrator:
    """Main orchestration loop: Plan → Execute → Evaluate → (Retry)."""

    def __init__(self):
        self.planner = PlannerAgent()
        self.evaluator = EvaluatorAgent()
        self.workers = {
            "scraper": ScraperWorker(),
            "image_processor": ImageProcessorWorker(),
            "content_generator": ContentGeneratorWorker(),
            "designer": DesignerWorker(),
            "benchmark_analyst": BenchmarkAnalystWorker(),
            "copywriter": CopywriterWorker(),
            "image_sourcer": ImageSourcerWorker(),
            "publisher": PublisherWorker(),
        }
        self._plan_history: list[Plan] = []

    async def run(
        self,
        user_request: str,
        context: dict | None = None,
        on_step_complete: Any = None,
    ) -> dict:
        """Execute the full orchestration loop.

        Args:
            user_request: Natural language user request
            context: Additional context (handle, topic, etc.)
            on_step_complete: Optional callback(step, result) for progress updates

        Returns:
            Final result dict with plan, evaluation, and all step results
        """
        context = context or {}
        retry_count = 0

        # Step 1: Planner creates the plan
        logger.info(f"[Orchestrator] Planning: {user_request}")
        plan = await self.planner.execute(user_request=user_request, context=context)
        self._plan_history.append(plan)

        while retry_count <= MAX_RETRIES:
            # Step 2: Execute the plan
            logger.info(f"[Orchestrator] Executing plan {plan.plan_id} (attempt {retry_count + 1})")
            plan.status = PlanStatus.EXECUTING
            await self._execute_plan(plan, on_step_complete)

            # Step 3: Evaluator reviews results
            logger.info(f"[Orchestrator] Evaluating plan {plan.plan_id}")
            plan.status = PlanStatus.EVALUATING
            evaluation = await self.evaluator.execute(plan=plan)
            plan.evaluation = {
                "overall_status": evaluation.overall_status,
                "overall_score": evaluation.overall_score,
                "step_evaluations": evaluation.step_evaluations,
                "summary": evaluation.summary,
                "retry_recommended": evaluation.retry_recommended,
                "retry_steps": evaluation.retry_steps,
            }

            # Step 4: Check if done or retry needed
            if evaluation.overall_status == "success" or not evaluation.retry_recommended:
                plan.status = PlanStatus.COMPLETED
                logger.info(f"[Orchestrator] Plan completed: {evaluation.summary}")
                break

            # Retry: revise plan based on feedback
            retry_count += 1
            if retry_count <= MAX_RETRIES:
                logger.info(
                    f"[Orchestrator] Retrying steps {evaluation.retry_steps} "
                    f"(attempt {retry_count + 1})"
                )
                plan = await self.planner.revise_plan(plan, plan.evaluation)
            else:
                plan.status = PlanStatus.FAILED
                logger.warning(f"[Orchestrator] Max retries exceeded for plan {plan.plan_id}")

        return self._build_result(plan)

    async def _execute_plan(self, plan: Plan, on_step_complete=None):
        """Execute plan steps respecting dependencies."""
        completed_step_ids: set[int] = set()
        step_results: dict[int, Any] = {}

        # Find steps that are already done (from previous run)
        for step in plan.steps:
            if step.status == StepStatus.SUCCESS:
                completed_step_ids.add(step.step_id)
                step_results[step.step_id] = step.result

        while True:
            # Find ready steps (dependencies satisfied, not yet done)
            ready_steps = [
                step
                for step in plan.steps
                if step.status == StepStatus.PENDING
                and all(dep in completed_step_ids for dep in step.depends_on)
            ]

            if not ready_steps:
                break  # No more steps to execute

            # Execute ready steps concurrently
            tasks = []
            for step in ready_steps:
                step.status = StepStatus.RUNNING
                step.started_at = datetime.now()

                # Resolve step references in params
                resolved_params = self._resolve_params(step.params, step_results)
                tasks.append(self._execute_step(step, resolved_params))

            results = await asyncio.gather(*tasks, return_exceptions=True)

            for step, result in zip(ready_steps, results):
                step.completed_at = datetime.now()

                if isinstance(result, Exception):
                    step.status = StepStatus.FAILED
                    step.error = str(result)
                    logger.error(f"[Orchestrator] Step {step.step_id} failed: {result}")
                else:
                    step.status = StepStatus.SUCCESS
                    step.result = result
                    completed_step_ids.add(step.step_id)
                    step_results[step.step_id] = result
                    logger.info(f"[Orchestrator] Step {step.step_id} completed")

                if on_step_complete:
                    on_step_complete(step, result)

    async def _execute_step(self, step, params: dict) -> Any:
        """Execute a single step via the appropriate worker."""
        worker = self.workers.get(step.worker)
        if not worker:
            raise ValueError(f"Unknown worker: {step.worker}")

        return await worker.execute(action=step.action, params=params)

    def _resolve_params(self, params: dict, step_results: dict[int, Any]) -> dict:
        """Replace step references like 'step_1' with actual results."""
        resolved = {}
        for key, value in params.items():
            if isinstance(value, str) and value.startswith("step_"):
                try:
                    ref_id = int(value.split("_")[1])
                    resolved[key] = step_results.get(ref_id, value)
                except (ValueError, IndexError):
                    resolved[key] = value
            else:
                resolved[key] = value
        return resolved

    def _build_result(self, plan: Plan) -> dict:
        """Build the final result dict."""
        return {
            "plan_id": plan.plan_id,
            "goal": plan.goal,
            "status": plan.status.value,
            "steps": [
                {
                    "step_id": s.step_id,
                    "worker": s.worker,
                    "action": s.action,
                    "status": s.status.value,
                    "result": s.result,
                    "error": s.error,
                    "duration_ms": (
                        int((s.completed_at - s.started_at).total_seconds() * 1000)
                        if s.started_at and s.completed_at
                        else None
                    ),
                }
                for s in plan.steps
            ],
            "evaluation": plan.evaluation,
        }
