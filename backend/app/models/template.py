from datetime import datetime

from sqlalchemy import String, DateTime, Integer, Boolean, ForeignKey, JSON, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class CarouselTemplate(Base):
    """A reusable rendering template (positions/colors/fonts).

    - System templates: user_id is NULL (shared across all users).
    - User templates: bound to user, optionally tied to a benchmark channel.
    """

    __tablename__ = "carousel_templates"
    __table_args__ = (
        UniqueConstraint("user_id", "slug", name="uq_template_user_slug"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    channel_id: Mapped[int | None] = mapped_column(
        ForeignKey("benchmark_channels.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    slug: Mapped[str] = mapped_column(String(100), index=True)
    name: Mapped[str] = mapped_column(String(255), default="")

    # Template content (Pydantic Template fields stored as JSON)
    canvas: Mapped[dict] = mapped_column(JSON, default=dict)
    brand: Mapped[dict] = mapped_column(JSON, default=dict)
    layouts: Mapped[dict] = mapped_column(JSON, default=dict)

    source_post_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_by: Mapped[str] = mapped_column(String(50), default="manual")  # "manual" | "gemini_vision" | "system"

    # Sharing — when share_code is set, anyone with the code can fetch + clone
    # this template. Toggle via POST/DELETE /api/templates/{id}/share.
    share_code: Mapped[str | None] = mapped_column(String(32), nullable=True, unique=True, index=True)
    is_public: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, onupdate=datetime.now
    )

    channel = relationship("BenchmarkChannel", back_populates="templates", foreign_keys=[channel_id])
