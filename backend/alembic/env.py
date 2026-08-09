"""Alembic environment — async (aiosqlite) + reads DB URL from app settings.

`render_as_batch=True` because SQLite can't ALTER most things in place;
batch_alter_table copies-rebuilds the table under the hood.
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# Pull URL from the same Settings the app uses so dev/prod can't drift.
from app.config import settings
from app.database import Base
import app.models  # noqa: F401 — registers every ORM model on Base.metadata

config = context.config
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

if config.config_file_name is not None:
    # disable_existing_loggers=False 필수. 기본값(True)이면 이 시점에 이미 살아있는
    # uvicorn/앱 로거가 전부 죽어서, 기동 중 발생하는 예외 트레이스백이 통째로
    # 삼켜진다(컨테이너가 exit 3 으로 죽는데 로그에 아무것도 안 남음).
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=settings.DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
