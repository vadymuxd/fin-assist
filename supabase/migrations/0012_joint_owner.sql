-- Add owner tagging for joint household refactor (Phase 15 joint.14/15).
--
-- pension_accounts: add owner column, backfill all existing rows as 'vadym'.
-- savings_accounts: normalize existing owner values to lowercase
--   (old 'Personal' → 'vadym', old 'Joint' → 'joint').
-- savings_snapshots: rename personal_total → vadym_total, add lisa_total.
-- pension_snapshots: add vadym_total (backfill from total), add lisa_total.

-- pension_accounts
ALTER TABLE pension_accounts
  ADD COLUMN IF NOT EXISTS owner TEXT NOT NULL DEFAULT 'vadym';

-- savings_accounts (column already exists, just normalize values)
UPDATE savings_accounts SET owner = 'vadym' WHERE owner = 'Personal';
UPDATE savings_accounts SET owner = 'joint' WHERE owner = 'Joint';

-- savings_snapshots
ALTER TABLE savings_snapshots RENAME COLUMN personal_total TO vadym_total;
ALTER TABLE savings_snapshots ADD COLUMN IF NOT EXISTS lisa_total NUMERIC NOT NULL DEFAULT 0;

-- pension_snapshots
ALTER TABLE pension_snapshots ADD COLUMN IF NOT EXISTS vadym_total NUMERIC;
ALTER TABLE pension_snapshots ADD COLUMN IF NOT EXISTS lisa_total  NUMERIC NOT NULL DEFAULT 0;
UPDATE pension_snapshots SET vadym_total = total WHERE vadym_total IS NULL;
