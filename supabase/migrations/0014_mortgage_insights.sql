-- Generated mortgage-market insight reports — history shown on the Insights page.
-- One row per run of scripts/mortgage_monitor.py (scheduled or manually triggered).
CREATE TABLE IF NOT EXISTS mortgage_insights (
  id               BIGSERIAL PRIMARY KEY,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  report_date      DATE NOT NULL,
  report_md        TEXT NOT NULL,            -- full markdown report
  telegram_text    TEXT,                     -- plain-text summary sent to Telegram
  base_rate        NUMERIC,                  -- BoE base rate at time of run
  fixed_2yr_rate   NUMERIC,                  -- best-buy 2yr fixed, 85% LTV
  fixed_2yr_lender TEXT,
  fixed_5yr_rate   NUMERIC,                  -- best-buy 5yr fixed, 85% LTV
  fixed_5yr_lender TEXT,
  next_mpc         DATE,                     -- next BoE MPC decision date
  triggered_by     TEXT NOT NULL DEFAULT 'schedule',  -- 'schedule' | 'manual'
  data             JSONB                     -- full structured data dict from the run
);

CREATE INDEX IF NOT EXISTS mortgage_insights_created_at_idx
  ON mortgage_insights (created_at DESC);

-- RLS: public SELECT (anon key), writes require the service-role key.
ALTER TABLE mortgage_insights ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "public read" ON mortgage_insights;
CREATE POLICY "public read" ON mortgage_insights FOR SELECT USING (true);
