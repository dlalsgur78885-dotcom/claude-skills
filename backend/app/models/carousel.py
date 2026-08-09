from datetime import datetime

from sqlalchemy import String, DateTime, Integer, ForeignKey, JSON, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
import enum

from app.database import Base


class CarouselStatus(str, enum.Enum):
    DRAFT = "draft"
    EDITING = "editing"
    FINALIZED = "finalized"


class GeneratedCarousel(Base):
    __tablename__ = "generated_carousels"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    source_post_id: Mapped[int | None] = mapped_column(
        ForeignKey("collected_posts.id"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(500), default="")
    canvas_data: Mapped[dict] = mapped_column(JSON, default=dict)
    template_id: Mapped[str] = mapped_column(String(100), default="minimal")
    status: Mapped[str] = mapped_column(
        SQLEnum(CarouselStatus), default=CarouselStatus.DRAFT
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, onupdate=datetime.now
    )

    user = relationship("User", back_populates="carousels")
