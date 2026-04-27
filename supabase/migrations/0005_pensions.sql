-- Per-provider pension balance (one row per provider/account per date)
CREATE TABLE pension_accounts (
  id           BIGSERIAL PRIMARY KEY,
  date         DATE NOT NULL,
  provider     TEXT NOT NULL,
  account_name TEXT NOT NULL,
  account_type TEXT,          -- 'workplace', 'personal', 'sipp', 'lisa'
  balance_gbp  NUMERIC NOT NULL,
  created_at   TIMESTAMPTZ DEFAULT NOW()
);

CREATE UNIQUE INDEX pension_accounts_date_provider_account
  ON pension_accounts (date, provider, account_name);

CREATE INDEX pension_accounts_date_idx     ON pension_accounts (date DESC);
CREATE INDEX pension_accounts_provider_idx ON pension_accounts (provider);

-- Monthly aggregate totals (used for charts and KPI cards)
CREATE TABLE pension_snapshots (
  id          BIGSERIAL PRIMARY KEY,
  date        DATE UNIQUE NOT NULL,
  total       NUMERIC NOT NULL,
  created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX pension_snapshots_date_idx ON pension_snapshots (date DESC);

-- RLS: public SELECT (anon key), writes require service-role key
ALTER TABLE pension_accounts  ENABLE ROW LEVEL SECURITY;
ALTER TABLE pension_snapshots ENABLE ROW LEVEL SECURITY;

CREATE POLICY "public read" ON pension_accounts  FOR SELECT USING (true);
CREATE POLICY "public read" ON pension_snapshots FOR SELECT USING (true);
