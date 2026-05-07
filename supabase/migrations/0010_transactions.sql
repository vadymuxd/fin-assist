-- Phase 12 data.11 — transactions table
-- Unified ledger for all financial events across every domain.
-- Written by: manual_web (app modal), nl_claude (Claude mobile),
--             scheduled (sync_worker from Cash Flow sheet), bank_api (future).

CREATE TABLE IF NOT EXISTS transactions (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  date             date        NOT NULL,
  domain           text        NOT NULL CHECK (domain IN (
                     'investments', 'savings', 'pensions', 'mortgage', 'expenses'
                   )),
  account_name     text,
  amount_gbp       numeric(12,2) NOT NULL,
  type             text        NOT NULL CHECK (type IN (
                     'deposit', 'withdrawal', 'payment', 'contribution', 'transfer'
                   )),
  notes            text,
  source           text        NOT NULL CHECK (source IN (
                     'manual_web', 'nl_claude', 'scheduled', 'bank_api'
                   )),
  synced_to_notion boolean     DEFAULT false,
  created_at       timestamptz DEFAULT now()
);

-- RLS
ALTER TABLE transactions ENABLE ROW LEVEL SECURITY;

CREATE POLICY "anon_read"    ON transactions FOR SELECT TO anon         USING (true);
CREATE POLICY "service_write" ON transactions FOR ALL   TO service_role USING (true);
