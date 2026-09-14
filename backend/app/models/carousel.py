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

    # ⚠ AUTOINCREMENT 가 **반드시** 필요하다.
    #
    # SQLite 는 이것이 없으면 새 id 를 `max(id)+1` 로 준다 — 그래서 **가장 최근 캐러셀을
    # 지우면 다음에 만드는 것이 그 번호를 그대로 다시 쓴다.** 번호는 이력·링크·대화에
    # 남는데 가리키는 대상이 바뀌어 버린다.
    # 실제로 그렇게 됐다: 제작 이력엔 13건이 적혀 있는데 남아 있는 캐러셀은 5개뿐이고,
    # 438 번이 서로 다른 회차 세 곳에 적혀 있었다. 2026-09-02 에 439 번이 다른 캐러셀로
    # 덮이는 것을 직접 재현했다.
    # AUTOINCREMENT 를 걸면 sqlite_sequence 가 최고값을 기억해 **번호를 다시 쓰지 않는다.**
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
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
