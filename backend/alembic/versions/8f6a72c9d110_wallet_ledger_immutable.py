"""Forbid changes to committed wallet ledger rows.

Revision ID: 8f6a72c9d110
Revises: b30ce05cd3ac
"""

from alembic import op

revision = "8f6a72c9d110"
down_revision = "b30ce05cd3ac"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE FUNCTION hashti_reject_wallet_ledger_change() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'wallet_transactions is append-only';
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE TRIGGER wallet_ledger_immutable
        BEFORE UPDATE OR DELETE ON wallet_transactions
        FOR EACH ROW EXECUTE FUNCTION hashti_reject_wallet_ledger_change();
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER wallet_ledger_immutable ON wallet_transactions")
    op.execute("DROP FUNCTION hashti_reject_wallet_ledger_change()")
