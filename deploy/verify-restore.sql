-- Run only against a newly restored, disposable database.
SELECT version_num AS migration FROM alembic_version;
SELECT 'guests' AS entity, count(*) AS rows FROM guests
UNION ALL SELECT 'registrations', count(*) FROM registrations
UNION ALL SELECT 'payments', count(*) FROM payment_submissions
UNION ALL SELECT 'wallets', count(*) FROM wallets
UNION ALL SELECT 'transactions', count(*) FROM wallet_transactions;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM wallets w
        LEFT JOIN (
            SELECT wallet_id, COALESCE(SUM(amount), 0) AS ledger_balance
            FROM wallet_transactions GROUP BY wallet_id
        ) t ON t.wallet_id = w.id
        WHERE w.balance <> COALESCE(t.ledger_balance, 0) OR w.balance < 0
    ) THEN
        RAISE EXCEPTION 'Wallet balance does not match ledger';
    END IF;
    IF EXISTS (
        SELECT 1 FROM guests g LEFT JOIN wallets w ON w.guest_id = g.id
        WHERE w.id IS NULL
    ) THEN
        RAISE EXCEPTION 'Guest without wallet';
    END IF;
END $$;

SELECT 'ledger_and_wallets_ok' AS result;
