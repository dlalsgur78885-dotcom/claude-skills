from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

engine = create_async_engine(settings.DATABASE_URL, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await _add_missing_columns(conn)
    await _seed_system_templates()


async def _add_missing_columns(conn) -> None:
    """Idempotent SQLite column adds for tables created in earlier deploys."""
    from sqlalchemy import text

    result = await conn.execute(text("PRAGMA table_info(element_image_pool)"))
    cols = {row[1] for row in result.fetchall()}
    if "quality_score" not in cols:
        await conn.execute(text(
            "ALTER TABLE element_image_pool ADD COLUMN quality_score REAL NOT NULL DEFAULT 0.0"
        ))

    result = await conn.execute(text("PRAGMA table_info(extracted_elements)"))
    cols = {row[1] for row in result.fetchall()}
    if "selected" not in cols:
        await conn.execute(text(
            "ALTER TABLE extracted_elements ADD COLUMN selected INTEGER NOT NULL DEFAULT 1"
        ))

    # benchmark_channels: brand identity + default template
    result = await conn.execute(text("PRAGMA table_info(benchmark_channels)"))
    cols = {row[1] for row in result.fetchall()}
    if "brand_primary_color" not in cols:
        await conn.execute(text(
            "ALTER TABLE benchmark_channels ADD COLUMN brand_primary_color VARCHAR(20)"
        ))
    if "brand_logo_path" not in cols:
        await conn.execute(text(
            "ALTER TABLE benchmark_channels ADD COLUMN brand_logo_path VARCHAR(500)"
        ))
    if "default_template_id" not in cols:
        await conn.execute(text(
            "ALTER TABLE benchmark_channels ADD COLUMN default_template_id INTEGER REFERENCES carousel_templates(id)"
        ))

    # carousel_templates: sharing fields (added in 템플릿 공유 feature)
    result = await conn.execute(text("PRAGMA table_info(carousel_templates)"))
    cols = {row[1] for row in result.fetchall()}
    if "share_code" not in cols:
        await conn.execute(text(
            "ALTER TABLE carousel_templates ADD COLUMN share_code VARCHAR(32)"
        ))
        # Unique partial index — only enforce uniqueness when share_code is set.
        await conn.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS ix_carousel_templates_share_code "
            "ON carousel_templates(share_code) WHERE share_code IS NOT NULL"
        ))
    if "is_public" not in cols:
        await conn.execute(text(
            "ALTER TABLE carousel_templates ADD COLUMN is_public INTEGER NOT NULL DEFAULT 0"
        ))

    # collected_posts: expired_at marks rows whose body+children were purged by
    # the 5-day TTL job. saved_at moves a post into "내 소재" (TTL-immune,
    # hidden from /posts). Row stays so instagram_post_id keeps channel dedupe.
    result = await conn.execute(text("PRAGMA table_info(collected_posts)"))
    cols = {row[1] for row in result.fetchall()}
    if "expired_at" not in cols:
        await conn.execute(text(
            "ALTER TABLE collected_posts ADD COLUMN expired_at DATETIME"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_collected_posts_expired_at "
            "ON collected_posts(expired_at)"
        ))
    if "saved_at" not in cols:
        await conn.execute(text(
            "ALTER TABLE collected_posts ADD COLUMN saved_at DATETIME"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_collected_posts_saved_at "
            "ON collected_posts(saved_at)"
        ))

    # users: per-account override for the /paraphrase prompt so each user can
    # tune the rewrite voice without touching server code or affecting others.
    result = await conn.execute(text("PRAGMA table_info(users)"))
    cols = {row[1] for row in result.fetchall()}
    if "paraphrase_prompt" not in cols:
        await conn.execute(text(
            "ALTER TABLE users ADD COLUMN paraphrase_prompt TEXT"
        ))

    # post_images: source_url stores the original Instagram CDN URL so the UI
    # has a fallback once the local /api/images/raw/... cache is cleaned up
    # by the 3-hour TTL job.
    result = await conn.execute(text("PRAGMA table_info(post_images)"))
    cols = {row[1] for row in result.fetchall()}
    if "source_url" not in cols:
        await conn.execute(text(
            "ALTER TABLE post_images ADD COLUMN source_url VARCHAR(1000) NOT NULL DEFAULT ''"
        ))
        # Backfill: rows whose raw_path is still a remote http URL (i.e. the
        # post was ingested but never went through use_post) — copy that into
        # source_url so future fallbacks have something.
        await conn.execute(text(
            "UPDATE post_images SET source_url = raw_path "
            "WHERE source_url = '' AND raw_path LIKE 'http%'"
        ))


async def _seed_system_templates() -> None:
    """Seed templates/*.json into carousel_templates as system rows (user_id NULL).

    Runs every boot but is idempotent — only inserts slugs not already present
    as system templates.
    """
    import json
    from pathlib import Path
    import logging

    log = logging.getLogger(__name__)
    templates_dir = Path(__file__).parent / "templates"
    if not templates_dir.exists():
        return

    from sqlalchemy import select, delete
    from app.models.template import CarouselTemplate

    # Drop any previously-seeded legacy rows (where layouts only has _legacy_slides)
    async with async_session() as session:
        legacy = await session.execute(
            select(CarouselTemplate).where(CarouselTemplate.user_id.is_(None))
        )
        for row in legacy.scalars().all():
            keys = list((row.layouts or {}).keys())
            if keys == ["_legacy_slides"] or not keys:
                await session.execute(
                    delete(CarouselTemplate).where(CarouselTemplate.id == row.id)
                )
                log.info(f"[seed] dropped legacy seed {row.slug}")
        await session.commit()

    async with async_session() as session:
        for f in templates_dir.glob("*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
            except Exception as e:
                log.warning(f"[seed] skip malformed {f.name}: {e}")
                continue

            slug = data.get("id") or f.stem
            # Skip legacy templates that only have `slides` (no `layouts`).
            # The new editor only understands the layouts schema.
            if "layouts" not in data:
                log.info(f"[seed] skip legacy-only template {slug}")
                continue

            existing = await session.execute(
                select(CarouselTemplate).where(
                    CarouselTemplate.slug == slug,
                    CarouselTemplate.user_id.is_(None),
                )
            )
            if existing.scalar_one_or_none():
                continue

            row = CarouselTemplate(
                user_id=None,
                channel_id=None,
                slug=slug,
                name=data.get("name", slug),
                canvas=data.get("canvas") or {},
                brand=data.get("brand") or {},
                layouts=data["layouts"],
                source_post_url=data.get("source_post_url"),
                created_by=data.get("created_by") or "system",
            )
            session.add(row)
            log.info(f"[seed] inserted system template {slug}")
        await session.commit()
