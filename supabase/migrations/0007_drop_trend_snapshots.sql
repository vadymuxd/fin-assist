-- Drop trend_snapshots table — superseded by portfolio_snapshots.
-- Trend data now lives entirely in portfolio_snapshots (daily Supabase writes
-- via daily_portfolio_snapshot.py). snapshot_trend.py and monthly_trend.yml
-- were deleted in Phase 11 eng.4.
DROP TABLE IF EXISTS trend_snapshots;
