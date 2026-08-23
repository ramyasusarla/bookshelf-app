"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-08-23

There's no existing deployed Postgres database to incrementally migrate —
this is a fresh install (previously the app only ran against local SQLite).
So rather than hand-writing op.create_table() calls that could drift from
app/models.py through transcription error, this bootstrap migration builds
the schema directly from the app's own SQLAlchemy metadata — the same
metadata the app runs against — which is correct by construction. Future
schema changes should be normal incremental Alembic migrations from here on.
"""

from typing import Sequence, Union

from alembic import op

from app import models  # noqa: F401 - importing registers every table on Base.metadata
from app.database import Base

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Must exist before any column can use the vector(n) type.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind())
    op.execute("DROP EXTENSION IF EXISTS vector")
