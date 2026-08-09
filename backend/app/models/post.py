from datetime import datetime

from sqlalchemy import String, DateTime, Integer, Text, ForeignKey, JSON, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class CollectedPost(Base):
    __tablename__ = "collected_posts"

    id: Mapped[int] = mapped_column(primary_key=True)
    channel_id: Mapped[int] = mapped_column(ForeignKey("benchmark_channels.id"), index=True)
    instagram_post_id: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    post_url: Mapped[str] = mapped_column(String(500))
    caption: Mapped[str] = mapped_column(Text, default="")
    hashtags: Mapped[list] = mapped_column(JSON, default=list)
    post_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    like_count: Mapped[int] = mapped_column(Integer, default=0)
    comment_count: Mapped[int] = mapped_column(Integer, default=0)
    slide_count: Mapped[int] = mapped_column(Integer, default=1)
    # 릴스/영상 게시물. 커버 1장만 들어오므로 slide_count 로는 사진 1장짜리와
    # 구분되지 않아 별도 플래그가 필요하다. 채우는 건 GramSnap 경로뿐 — Hiker
    # fallback 이나 단건 URL 수집으로 들어온 건은 기본값 False 로 남는다.
    is_video: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    collected_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    # 5-day TTL: when set, this post's body/images/elements have been purged
    # but the row stays so instagram_post_id keeps the channel's dedupe history.
    expired_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    # User moved this post into "내 소재" — TTL no longer applies and the post
    # is hidden from /posts. Cleared only when the user manually deletes.
    saved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)

    channel = relationship("BenchmarkChannel", back_populates="posts")
    images = relationship("PostImage", back_populates="post")
