from datetime import datetime

from sqlalchemy import String, DateTime, Integer, Boolean, Float, Text, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ExtractedElement(Base):
    """Element/keyword extracted from a benchmark post (caption + slide OCR)."""

    __tablename__ = "extracted_elements"

    id: Mapped[int] = mapped_column(primary_key=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("collected_posts.id"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    search_query: Mapped[str] = mapped_column(String(500), default="")
    source_text: Mapped[str] = mapped_column(Text, default="")
    selected: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    images = relationship("ElementImagePool", back_populates="element", cascade="all, delete-orphan")


class ElementImagePool(Base):
    """Bing-collected image candidates for an element. Employee picks from this pool."""

    __tablename__ = "element_image_pool"

    id: Mapped[int] = mapped_column(primary_key=True)
    element_id: Mapped[int] = mapped_column(ForeignKey("extracted_elements.id"), index=True)
    source_url: Mapped[str] = mapped_column(String(1000))
    local_path: Mapped[str] = mapped_column(String(500), default="")
    thumbnail_url: Mapped[str] = mapped_column(String(1000), default="")
    width: Mapped[int] = mapped_column(Integer, default=0)
    height: Mapped[int] = mapped_column(Integer, default=0)
    rank: Mapped[int] = mapped_column(Integer, default=0)
    source: Mapped[str] = mapped_column(String(50), default="bing")
    quality_score: Mapped[float] = mapped_column(Float, default=0.0)
    collected_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    element = relationship("ExtractedElement", back_populates="images")


class PostUsageJob(Base):
    """Tracks the '쓸게요' pipeline run for a post."""

    __tablename__ = "post_usage_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("collected_posts.id"), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(50), default="pending")
    stage: Mapped[str] = mapped_column(String(100), default="")
    error: Mapped[str] = mapped_column(Text, default="")
    slide_texts: Mapped[list] = mapped_column(JSON, default=list)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
