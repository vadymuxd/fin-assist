-- Migration 0023: monzo_transactions balance_processed_at (feature.1)
--
-- feature.1 (monzo_balance_sync.py) scans monzo_transactions for savings-pot
-- transfers and investment-platform deposits, and auto-creates Financial
-- Updates DB entries for them. This column marks which rows it has already
-- considered, so:
--   1. It never re-scans the ~10,600-row historical backfill (which would
--      produce false positives — the same reason monzo.7 balance writers
--      were originally deferred in Phase 18).
--   2. It never double-counts a transaction across runs, including the real
--      £2,000 Monzo Flexible Fund transfer already reflected via the manual
--      £12,000 BALANCE_UPDATE entry fixed in hotfix.1 — that transaction is
--      already present in this table as of this migration, so backfilling
--      balance_processed_at=NOW() for all existing rows excludes it from
--      re-processing.
--
-- Only rows inserted by monzo_sync.py AFTER this migration lands will have
-- balance_processed_at IS NULL and be considered by monzo_balance_sync.py.

ALTER TABLE monzo_transactions
    ADD COLUMN IF NOT EXISTS balance_processed_at TIMESTAMPTZ;

UPDATE monzo_transactions
    SET balance_processed_at = NOW()
    WHERE balance_processed_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_monzo_transactions_balance_unprocessed
    ON monzo_transactions (row_index)
    WHERE balance_processed_at IS NULL;
