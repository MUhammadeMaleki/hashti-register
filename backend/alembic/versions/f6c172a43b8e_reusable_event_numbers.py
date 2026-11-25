"""Keep canceled event history while releasing future display numbers.

Revision ID: f6c172a43b8e
Revises: e53b72f6a0c4
"""

import sqlalchemy as sa

from alembic import op

revision = "f6c172a43b8e"
down_revision = "e53b72f6a0c4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("events", sa.Column("number_released", sa.Boolean(),
                                      server_default=sa.text("false"), nullable=False))
    op.drop_constraint("uq_events_event_number", "events", type_="unique")
    op.execute("""
        UPDATE events SET number_released = true
        WHERE is_cancelled = true AND is_historical_import = false
          AND (event_date IS NULL OR event_date > (now() AT TIME ZONE 'Asia/Tehran')::date
               OR (event_date = (now() AT TIME ZONE 'Asia/Tehran')::date
                   AND (start_time IS NULL OR start_time >=
                        (now() AT TIME ZONE 'Asia/Tehran')::time)))
    """)
    op.create_index("uq_events_active_event_number", "events", ["event_number"],
                    unique=True, postgresql_where=sa.text("number_released = false"))


def downgrade() -> None:
    # A released number may have been reused. Refuse to discard that history.
    op.execute("""
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM events GROUP BY event_number HAVING count(*) > 1) THEN
            RAISE EXCEPTION 'Cannot restore global event-number uniqueness';
          END IF;
        END $$;
    """)
    op.drop_index("uq_events_active_event_number", table_name="events")
    op.create_unique_constraint("uq_events_event_number", "events", ["event_number"])
    op.drop_column("events", "number_released")
