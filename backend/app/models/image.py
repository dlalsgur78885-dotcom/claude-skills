from sqlalchemy import String, Integer, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class PostImage(Base):
    __tablename__ = "post_images"

    id: Mapped[int] = mapped_column(primary_key=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("collected_posts.id"))
    slide_index: Mapped[int] = mapped_column(Integer, default=0)
    # `raw_path` is the URL the UI loads from. After "이 게시물 쓸게요" downloads
    # the slide locally, raw_path points at /api/images/raw/... For the first
    # ~3 hours after that it serves the cached file; once the cleanup job runs
    # the file is gone and raw_path 404s. `source_url` keeps the original
    # Instagram CDN URL forever so the frontend can fall back to it (CDN links
    # are typically valid for at least a day).
    raw_path: Mapped[str] = mapped_column(String(1000), default="")
    source_url: Mapped[str] = mapped_column(String(1000), default="")
    processed_path: Mapped[str] = mapped_column(String(500), default="")
    width: Mapped[int] = mapped_column(Integer, default=0)
    height: Mapped[int] = mapped_column(Integer, default=0)

    post = relationship("CollectedPost", back_populates="images")
