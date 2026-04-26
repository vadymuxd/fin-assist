-- Per-account balance snapshot (one row per account per date)
CREATE TABLE savings_accounts (
  id           BIGSERIAL PRIMARY KEY,
  date         DATE NOT NULL,
  bank         TEXT NOT NULL,
  account_name TEXT NOT NULL,
  account_type TEXT,          -- 'savings', 'isa', 'pot', 'current'
  owner        TEXT NOT NULL, -- 'Personal' | 'Joint'
  balance_gbp  NUMERIC NOT NULL,
  created_at   TIMESTAMPTZ DEFAULT NOW()
);

CREATE UNIQUE INDEX savings_accounts_date_bank_account
  ON savings_accounts (date, bank, account_name);

CREATE INDEX savings_accounts_date_idx ON savings_accounts (date DESC);
CREATE INDEX savings_accounts_bank_idx ON savings_accounts (bank);

-- Daily aggregate totals (used for charts and KPI cards)
CREATE TABLE savings_snapshots (
  id             BIGSERIAL PRIMARY KEY,
  date           DATE UNIQUE NOT NULL,
  total          NUMERIC NOT NULL,
  personal_total NUMERIC NOT NULL,
  joint_total    NUMERIC NOT NULL,
  created_at     TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX savings_snapshots_date_idx ON savings_snapshots (date DESC);

-- RLS: public SELECT (anon key), writes require service-role key
ALTER TABLE savings_accounts  ENABLE ROW LEVEL SECURITY;
ALTER TABLE savings_snapshots ENABLE ROW LEVEL SECURITY;

CREATE POLICY "public read" ON savings_accounts  FOR SELECT USING (true);
CREATE POLICY "public read" ON savings_snapshots FOR SELECT USING (true);
