from datetime import datetime

from sqlalchemy import String, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default="worker")  # "admin" | "worker"
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    # User-supplied prompt that replaces the default "병렬 치환" instructions.
    # NULL or empty string → carousels/paraphrase falls back to the built-in
    # prompt so existing accounts behave exactly as before.
    paraphrase_prompt: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    # Feedback #11-13: 제목·캡션은 속지와 글의 성격이 달라 치환 프롬프트를 따로 둔다.
    # paraphrase_prompt = 속지(body)용. 아래 둘이 제목·캡션용. NULL/빈값 → 기본값.
    title_paraphrase_prompt: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    caption_paraphrase_prompt: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)

    channels = relationship("BenchmarkChannel", back_populates="user")
    carousels = relationship("GeneratedCarousel", back_populates="user")
