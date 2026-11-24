"""Mark imported historical events even when their date is unknown.

Revision ID: c41e9a7b2d10
Revises: 8f6a72c9d110
"""

import sqlalchemy as sa

from alembic import op

revision = "c41e9a7b2d10"
down_revision = "8f6a72c9d110"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("events", sa.Column("is_historical_import", sa.Boolean(),
                                      server_default=sa.text("false"), nullable=False))


def downgrade() -> None:
    op.drop_column("events", "is_historical_import")
