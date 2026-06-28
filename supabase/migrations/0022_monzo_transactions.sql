-- Migration 0022: monzo_transactions table
-- Full-fidelity mirror of both Monzo auto-export tabs (Personal + Joint).
-- account_type distinguishes the source tab.
-- row_index is the sheet row number — used as the sync cursor.
-- transaction_id is the Monzo-assigned unique ID — idempotency safety net.

CREATE TABLE IF NOT EXISTS monzo_transactions (
    id                BIGSERIAL PRIMARY KEY,
    transaction_id    TEXT        NOT NULL,
    account_type      TEXT        NOT NULL CHECK (account_type IN ('personal', 'joint')),
    row_index         INTEGER     NOT NULL,
    date              DATE,
    time              TEXT,
    type              TEXT,
    name              TEXT,
    emoji             TEXT,
    category          TEXT,
    amount            NUMERIC(12, 2),
    currency          TEXT,
    local_amount      NUMERIC(12, 2),
    local_currency    TEXT,
    notes             TEXT,
    address           TEXT,
    receipt           TEXT,
    description       TEXT,
    category_split    TEXT,
    pot_name          TEXT,
    synced_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (transaction_id, account_type)
);

-- Index for cursor queries (MAX row_index per account_type)
CREATE INDEX IF NOT EXISTS idx_monzo_transactions_cursor
    ON monzo_transactions (account_type, row_index DESC);

-- Index for dashboard queries (date, category, type filters)
CREATE INDEX IF NOT EXISTS idx_monzo_transactions_date
    ON monzo_transactions (account_type, date DESC);

CREATE INDEX IF NOT EXISTS idx_monzo_transactions_category
    ON monzo_transactions (account_type, category);
