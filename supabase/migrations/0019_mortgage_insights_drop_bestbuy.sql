-- Hotfix (2026-06): Mortgage Insights — remove unreliable best-buy figures,
-- add week-over-week comparison on the BoE market-average rates.
--
-- The Moneyfacts best-buy scrape produced misleading picks (e.g. 4.66% vs the
-- actual Nationwide 4.99%), so best-buy is dropped entirely. The insight now
-- carries only the BoE-derived market averages, plus their WoW bps deltas.

ALTER TABLE mortgage_insights
  DROP COLUMN IF EXISTS fixed_2yr_rate,
  DROP COLUMN IF EXISTS fixed_2yr_lender,
  DROP COLUMN IF EXISTS fixed_5yr_rate,
  DROP COLUMN IF EXISTS fixed_5yr_lender;

ALTER TABLE mortgage_insights
  ADD COLUMN IF NOT EXISTS avg_2yr_wow_bps INTEGER,  -- 2yr avg change vs prior week, basis points
  ADD COLUMN IF NOT EXISTS avg_5yr_wow_bps INTEGER;  -- 5yr avg change vs prior week, basis points
