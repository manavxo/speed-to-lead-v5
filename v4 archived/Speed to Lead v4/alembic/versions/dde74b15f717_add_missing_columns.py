"""add missing columns to existing tables

Some columns were added to models after the initial Alembic migration
was already applied on production. This migration adds them via ALTER TABLE.

Revision ID: dde74b15f717
Revises: cba54ef9d496
Create Date: 2026-06-07 15:06:34.508602
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'dde74b15f717'
down_revision: Union[str, Sequence[str], None] = 'cba54ef9d496'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(table: str, column: str) -> bool:
    """Check if a column exists in a table (works for both SQLite and Postgres)."""
    bind = op.get_bind()
    if bind.dialect.name == 'postgresql':
        result = bind.execute(
            sa.text("SELECT 1 FROM information_schema.columns WHERE table_name=:t AND column_name=:c"),
            {"t": table, "c": column},
        ).fetchone()
        return result is not None
    else:
        result = bind.execute(sa.text(f"PRAGMA table_info({table})")).fetchall()
        return any(row[1] == column for row in result)


def _add_column_if_missing(table: str, column: str, col_type: sa.types.TypeEngine):
    """Add a column to a table if it doesn't already exist."""
    if not _column_exists(table, column):
        op.add_column(table, sa.Column(column, col_type, nullable=True))


def upgrade() -> None:
    """Add columns that may be missing from pre-Alembic production DBs."""

    # Lead table — columns added after initial deploy
    _add_column_if_missing('lead', 'assigned_rep', sa.String())
    _add_column_if_missing('lead', 'pass_count', sa.Integer())
    _add_column_if_missing('lead', 'consent', sa.Boolean())
    _add_column_if_missing('lead', 'vehicle_id', sa.Integer())
    _add_column_if_missing('lead', 'loss_reason', sa.String())

    # Dealer table — columns that may be missing
    _add_column_if_missing('dealer', 'sms_number', sa.String())
    _add_column_if_missing('dealer', 'whatsapp_sender', sa.String())
    _add_column_if_missing('dealer', 'web_form_token', sa.String())
    _add_column_if_missing('dealer', 'config', sa.JSON())
    _add_column_if_missing('dealer', 'round_robin_pointer', sa.Integer())
    _add_column_if_missing('dealer', 'timezone', sa.String())

    # If alembic_version table doesn't exist (pre-Alembic DB), stamp it
    bind = op.get_bind()
    if bind.dialect.name == 'postgresql':
        result = bind.execute(
            sa.text("SELECT 1 FROM information_schema.tables WHERE table_name='alembic_version'")
        ).fetchone()
        if result is None:
            # Tables exist but no alembic_version — create it and stamp
            op.create_table('alembic_version', sa.Column('version_num', sa.String(32), nullable=False))


def downgrade() -> None:
    """No-op — we don't remove columns."""
    pass
