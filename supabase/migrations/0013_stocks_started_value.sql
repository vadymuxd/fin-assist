-- 0013_stocks_started_value.sql
-- Tracks the sum of each held stock's "Tracking Started Value" (sheet col I).
-- Used to compute organic stocks performance:
--   performance = self_managed / stocks_started_value - 1
-- which strips out the inflation that would otherwise come from new BUYs
-- funded by deposits (because BUYs add cost basis to both numerator and
-- denominator equally, leaving the ratio unchanged).

ALTER TABLE portfolio_snapshots
  ADD COLUMN IF NOT EXISTS stocks_started_value NUMERIC;
