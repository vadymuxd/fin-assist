-- Extend portfolio_snapshots for joint household:
--   grand_total → vadym_total (it was always Vadym-only)
--   + lisa_total, joint_total (new columns)
--   Backfill joint_total from vadym_total for existing rows.

ALTER TABLE portfolio_snapshots RENAME COLUMN grand_total TO vadym_total;
ALTER TABLE portfolio_snapshots ADD COLUMN IF NOT EXISTS lisa_total  NUMERIC;
ALTER TABLE portfolio_snapshots ADD COLUMN IF NOT EXISTS joint_total NUMERIC;

UPDATE portfolio_snapshots SET joint_total = vadym_total WHERE joint_total IS NULL;
