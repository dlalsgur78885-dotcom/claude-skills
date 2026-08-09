"""Per-call LLM token usage log — survives restart so cost is auditable.

Append-only. One row per LLM API call where we get back a usage object
(CLI calls have no token counts so they're skipped). `model` is the full
upstream model ID (e.g. `gemini/gemini-2.5-pro-preview-03-25`) so cost
math can be plugged in later without losing fidelity. `call_type`
distinguishes "vision" (image input — heavy) vs "text" (regular chat).
"""

from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class UsageLog(Base):
    __tablename__ = "usage_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    model: Mapped[str] = mapped_column(String(120), index=True)
    call_type: Mapped[str] = mapped_column(String(20), default="text")
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, index=True
    )
