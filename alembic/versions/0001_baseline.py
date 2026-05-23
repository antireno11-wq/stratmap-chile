"""baseline — schema is created by db.init_db_safe() at app startup.

This empty migration exists so that production DBs with an already-built
schema can be stamped at this revision:

    alembic stamp 0001_baseline

After stamping, future schema changes go through Alembic:

    alembic revision -m "describe change"   # edit the generated file
    alembic upgrade head

Until we flip the cutover (drop the init_*_db functions and let Alembic
take over fresh installs too), both systems coexist: init_*_db keeps the
schema idempotent on startup, Alembic tracks new migrations from here on.

Revision ID: 0001_baseline
Revises:
Create Date: 2026-05-23
"""
from alembic import op  # noqa: F401
import sqlalchemy as sa  # noqa: F401


revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Baseline: nothing to apply. Schema already in place via db.init_*_db().
    pass


def downgrade() -> None:
    pass
