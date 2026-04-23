-- Phase 6C: Add GBP-denominated value for accurate cross-currency allocation charts.
-- Pulled directly from Inv26 - Summary col G ("Current Value £").

ALTER TABLE holdings
    ADD COLUMN IF NOT EXISTS value_gbp NUMERIC;
