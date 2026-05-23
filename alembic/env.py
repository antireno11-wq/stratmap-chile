"""Alembic environment.

Lee DATABASE_URL desde env (Railway lo provee). No usamos SQLAlchemy ORM:
las migraciones son SQL crudo via op.execute / op.add_column / etc.
"""
import os

from alembic import context
from sqlalchemy import engine_from_config, pool


config = context.config

db_url = os.getenv("DATABASE_URL", "")
if db_url:
    # Forzar driver psycopg (no psycopg2)
    if db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+psycopg://", 1)
    config.set_main_option("sqlalchemy.url", db_url)

target_metadata = None  # raw SQL, no autogenerate basado en SQLAlchemy models


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
