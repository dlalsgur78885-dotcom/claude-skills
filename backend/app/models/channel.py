from datetime import datetime

from sqlalchemy import String, DateTime, Boolean, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class BenchmarkChannel(Base):
    __tablename__ = "benchmark_channels"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    instagram_handle: Mapped[str] = mapped_column(String(255), index=True)
    display_name: Mapped[str] = mapped_column(String(255), default="")
    category: Mapped[str] = mapped_column(String(100), default="")
    style_tags: Mapped[dict] = mapped_column(JSON, default=list)
    last_scraped_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    # Brand identity (overrides any color/logo Gemini Vision might guess from a single post)
    brand_primary_color: Mapped[str | None] = mapped_column(String(20), nullable=True)
    brand_logo_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Default template applied by the daily pipeline for this channel's new posts
    default_template_id: Mapped[int | None] = mapped_column(
        ForeignKey("carousel_templates.id"), nullable=True
    )

    user = relationship("User", back_populates="channels")
    posts = relationship("CollectedPost", back_populates="channel")
    # No cascade — templates survive their parent channel. When a channel is
    # deleted, the API layer (channels._purge_channel_children) nulls out
    # template.channel_id explicitly. The CarouselTemplate.channel_id FK also
    # carries ondelete=SET NULL for defense-in-depth when SQLite FK enforcement
    # is enabled. Saved templates are user work product — never auto-delete.
    templates = relationship(
        "CarouselTemplate",
        back_populates="channel",
        foreign_keys="CarouselTemplate.channel_id",
    )
