-- Add managed_started_value to portfolio_snapshots.
-- Tracks the MANAGED FUNDS "Tracking Started Value" (sheet col I on the aggregate
-- row), bumped by deposits. Lets the web compute organic managed performance
-- (managed / managed_started_value) so a contribution doesn't spike the
-- comparison chart or the daily delta — mirrors stocks_started_value / lisa_started_value.
-- Backfill with 2489.41 — the managed Col I value before the 2026-06-20 Nutmeg
-- deposit; the post-deposit row (5257.00) is rewritten by snapshot_worker.

ALTER TABLE portfolio_snapshots
  ADD COLUMN IF NOT EXISTS managed_started_value NUMERIC;

UPDATE portfolio_snapshots
  SET managed_started_value = 2489.41
  WHERE managed_started_value IS NULL;
