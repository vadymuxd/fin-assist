ALTER TABLE mortgage_snapshots
  ADD COLUMN IF NOT EXISTS deal_expires     DATE,
  ADD COLUMN IF NOT EXISTS deal_term_years  SMALLINT;

-- Backfill all Co-operative Bank rows with the known deal details
UPDATE mortgage_snapshots
SET deal_expires    = '2027-01-31',
    deal_term_years = 32
WHERE lender = 'Co-operative Bank';
