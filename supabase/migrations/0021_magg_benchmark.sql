-- Add magg benchmark column to portfolio_snapshots.
-- Tracks the daily GOOGLEFINANCE("LON:MAGG","price") value from the
-- Investments tab Benchmarks section. Used by the comparison chart to show
-- MAGG (iShares Growth Portfolio) as a price-ratio series, replacing the
-- old "Managed Funds" (Nutmeg) TWR series removed in the Jun-2026 consolidation.
-- No backfill — MAGG was first bought 2026-06-25; prior rows stay NULL and
-- the chart starts the series from the first non-null date naturally.

ALTER TABLE portfolio_snapshots
  ADD COLUMN IF NOT EXISTS magg NUMERIC;
