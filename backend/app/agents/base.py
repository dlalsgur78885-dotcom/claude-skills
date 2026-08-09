"""Base agent class and shared types for the orchestration system."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any
import uuid


class AgentRole(str, Enum):
    # Core orchestration
    PLANNER = "planner"
    EVALUATOR = "evaluator"

    # Workers
    SCRAPER = "scraper"
    IMAGE_PROCESSOR = "image_processor"
    CONTENT_GENERATOR = "content_generator"
    DESIGNER = "designer"

    # New workers
    BENCHMARK_ANALYST = "benchmark_analyst"
    COPYWRITER = "copywriter"
    IMAGE_SOURCER = "image_sourcer"
    PUBLISHER = "publisher"


# ─── Agent ↔ LLM mapping ───

AGENT_LLM_CONFIG: dict[str, dict[str, Any]] = {
    # Core: high-capability models (CLI-first, no API key needed)
    "planner":            {"model": "sonnet",                "needs_llm": True},
    "evaluator":          {"models": ["sonnet", "gemini-flash-thinking"], "needs_llm": True, "consensus": True},

    # Workers: task-specific
    "scraper":            {"model": None,                    "needs_llm": False},  # API calls only
    "image_processor":    {"model": None,                    "needs_llm": False},  # API calls only
    "content_generator":  {"model": "gemini-flash",          "needs_llm": True},
    "designer":           {"model": "gemini-flash",          "needs_llm": True},

    # New workers
    "benchmark_analyst":  {"model": "sonnet",                "needs_llm": True},   # 패턴 분석에 고성능 필요
    "copywriter":         {"model": "sonnet",                "needs_llm": True},   # 카피 품질이 핵심
    "image_sourcer":      {"model": "gemini-flash",          "needs_llm": True},   # 키워드 생성 + 결과 평가
    "publisher":          {"model": None,                    "needs_llm": False},  # Meta API 호출만
}


class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"


class PlanStatus(str, Enum):
    CREATED = "created"
    EXECUTING = "executing"
    EVALUATING = "evaluating"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class PlanStep:
    step_id: int
    worker: str
    action: str
    params: dict = field(default_factory=dict)
    depends_on: list[int] = field(default_factory=list)
    priority: str = "medium"
    status: StepStatus = StepStatus.PENDING
    result: Any = None
    error: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None


@dataclass
class Plan:
    plan_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    goal: str = ""
    steps: list[PlanStep] = field(default_factory=list)
    success_criteria: str = ""
    status: PlanStatus = PlanStatus.CREATED
    created_at: datetime = field(default_factory=datetime.now)
    evaluation: dict | None = None


@dataclass
class Evaluation:
    plan_id: str = ""
    overall_status: str = "pending"
    overall_score: float = 0.0
    step_evaluations: list[dict] = field(default_factory=list)
    summary: str = ""
    retry_recommended: bool = False
    retry_steps: list[int] = field(default_factory=list)


PROMPTS_DIR = Path(__file__).parent / "prompts"


class BaseAgent(ABC):
    """Base class for all agents in the orchestration system."""

    def __init__(self, role: AgentRole):
        self.role = role
        self.prompt = self._load_prompt()
        self.llm_config = AGENT_LLM_CONFIG.get(role.value, {})

    def _load_prompt(self) -> str:
        """Load the agent's .md prompt file."""
        prompt_file = PROMPTS_DIR / f"{self.role.value}.md"
        if not prompt_file.exists():
            prompt_file = PROMPTS_DIR / f"{self.role.value}_worker.md"
        if prompt_file.exists():
            return prompt_file.read_text(encoding="utf-8")
        return ""

    @property
    def needs_llm(self) -> bool:
        return self.llm_config.get("needs_llm", False)

    @property
    def default_model(self) -> str | None:
        return self.llm_config.get("model")

    @property
    def uses_consensus(self) -> bool:
        return self.llm_config.get("consensus", False)

    @property
    def consensus_models(self) -> list[str]:
        return self.llm_config.get("models", [])

    async def ask_llm(self, prompt: str, model: str | None = None, **kwargs) -> str:
        """Call the agent's assigned LLM."""
        from app.agents.llm_client import llm_call
        model = model or self.default_model
        if not model:
            raise ValueError(f"Agent {self.role.value} has no LLM configured")
        return await llm_call(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            system=self.prompt,
            **kwargs,
        )

    async def ask_llm_json(self, prompt: str, model: str | None = None, **kwargs) -> dict | list:
        """Call LLM and parse JSON response."""
        from app.agents.llm_client import llm_json
        model = model or self.default_model
        if not model:
            raise ValueError(f"Agent {self.role.value} has no LLM configured")
        return await llm_json(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            system=self.prompt,
            **kwargs,
        )

    async def ask_consensus(self, prompt: str, **kwargs) -> list[dict]:
        """Call multiple models and return all responses (for Evaluator)."""
        from app.agents.llm_client import llm_consensus
        if not self.consensus_models:
            raise ValueError(f"Agent {self.role.value} has no consensus models")
        return await llm_consensus(
            models=self.consensus_models,
            messages=[{"role": "user", "content": prompt}],
            system=self.prompt,
            **kwargs,
        )

    @abstractmethod
    async def execute(self, **kwargs) -> Any:
        """Execute the agent's main task."""
        pass
