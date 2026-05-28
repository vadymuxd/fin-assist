-- Add lisa_started_value to portfolio_snapshots.
-- Tracks total capital Lisa has invested in her GIC ISA (updated when she deposits).
-- Used as denominator for organic performance: (lisa_total - lisa_started_value) / lisa_started_value.
-- Backfill with 14044 — the Col I value from the Investments sheet at the time of this migration.

ALTER TABLE portfolio_snapshots
  ADD COLUMN IF NOT EXISTS lisa_started_value NUMERIC;

UPDATE portfolio_snapshots
  SET lisa_started_value = 14044
  WHERE lisa_started_value IS NULL;
