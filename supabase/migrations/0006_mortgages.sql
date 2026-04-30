-- Monthly mortgage balance snapshot (one row per calendar month, on the 1st)
CREATE TABLE mortgage_snapshots (
  id              BIGSERIAL PRIMARY KEY,
  date            DATE UNIQUE NOT NULL,
  balance         NUMERIC NOT NULL,           -- remaining balance after that month's payment
  property_value  NUMERIC NOT NULL DEFAULT 660000,
  equity          NUMERIC NOT NULL,           -- property_value - balance
  equity_half     NUMERIC NOT NULL,           -- equity / 2 (Vadym's share of joint mortgage)
  monthly_payment NUMERIC NOT NULL DEFAULT 3072,
  rate            NUMERIC NOT NULL DEFAULT 0.0526, -- annual rate
  lender          TEXT NOT NULL DEFAULT 'Co-operative Bank',
  created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX mortgage_snapshots_date_idx ON mortgage_snapshots (date DESC);

-- RLS: public SELECT (anon key), writes require service-role key
ALTER TABLE mortgage_snapshots ENABLE ROW LEVEL SECURITY;
CREATE POLICY "public read" ON mortgage_snapshots FOR SELECT USING (true);
