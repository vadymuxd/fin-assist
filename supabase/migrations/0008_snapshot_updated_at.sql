-- Add updated_at to snapshot tables so the frontend can show when the data
-- was actually synced (not the month-end date stored in the 'date' column).
-- Workers explicitly write updated_at = NOW() on every upsert so the value
-- changes whenever the snapshot is refreshed, even for the same date row.

ALTER TABLE savings_snapshots  ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();
ALTER TABLE pension_snapshots  ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();
ALTER TABLE mortgage_snapshots ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();
