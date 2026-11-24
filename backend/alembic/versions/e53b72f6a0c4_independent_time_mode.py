"""Give event time its own announcement mode, independent of location.

Revision ID: e53b72f6a0c4
Revises: c41e9a7b2d10
"""

import sqlalchemy as sa

from alembic import op

revision = "e53b72f6a0c4"
down_revision = "c41e9a7b2d10"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("events", sa.Column("time_mode", sa.String(length=20),
                                      server_default=sa.text("'tba'"), nullable=False))
    op.execute("""
        UPDATE events SET time_mode = CASE
            WHEN event_date IS NOT NULL AND start_time IS NOT NULL THEN 'exact'
            WHEN NULLIF(BTRIM(time_text), '') IS NOT NULL THEN 'approximate'
            ELSE 'tba'
        END
    """)
    op.create_check_constraint(op.f("ck_events_time_mode_valid"), "events",
                               "time_mode IN ('exact', 'approximate', 'tba')")


def downgrade() -> None:
    op.drop_constraint(op.f("ck_events_time_mode_valid"), "events", type_="check")
    op.drop_column("events", "time_mode")
