"""Record event-specific discounts separately from wallet payments.

Revision ID: a7b61c4d92e0
Revises: f6c172a43b8e
"""

import sqlalchemy as sa

from alembic import op

revision = "a7b61c4d92e0"
down_revision = "f6c172a43b8e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "event_discounts",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("registration_id", sa.BigInteger(), sa.ForeignKey(
            "registrations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("original_discount_id", sa.BigInteger(), sa.ForeignKey(
            "event_discounts.id", ondelete="RESTRICT")),
        sa.Column("amount", sa.BigInteger(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("actor_id", sa.BigInteger(), sa.ForeignKey(
            "users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("idempotency_key", sa.String(100), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
        sa.CheckConstraint("amount <> 0", name="ck_event_discounts_amount_nonzero"),
        sa.CheckConstraint("NULLIF(BTRIM(reason), '') IS NOT NULL",
                           name="ck_event_discounts_reason_required"),
        sa.CheckConstraint("(amount > 0 AND original_discount_id IS NULL) OR "
                           "(amount < 0 AND original_discount_id IS NOT NULL)",
                           name="ck_event_discounts_reversal_link_valid"),
    )
    op.create_index("ix_event_discounts_registration", "event_discounts", ["registration_id"])
    op.execute("""
        CREATE FUNCTION hashti_reject_event_discount_change() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'event_discounts is append-only';
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE TRIGGER event_discounts_immutable
        BEFORE UPDATE OR DELETE ON event_discounts
        FOR EACH ROW EXECUTE FUNCTION hashti_reject_event_discount_change()
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER event_discounts_immutable ON event_discounts")
    op.execute("DROP FUNCTION hashti_reject_event_discount_change()")
    op.drop_index("ix_event_discounts_registration", table_name="event_discounts")
    op.drop_table("event_discounts")
