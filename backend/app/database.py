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
    """Schema bootstrap via Alembic.

    Past idempotent ALTER TABLE catch-ups (paraphrase_prompt, share_code,
    expired_at, etc.) are now folded into the baseline migration. Existing
    DBs that already had them applied get stamped to head on first boot
    after this rollout; future schema changes go through `alembic revision`.
    """
    from app.db_migrations import bootstrap_schema
    await bootstrap_schema()
    await _seed_system_templates()


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
