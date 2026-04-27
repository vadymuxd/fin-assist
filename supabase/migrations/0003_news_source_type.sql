-- Phase 6E: Distinguish per-holding news fetches from broad market scans.
-- Without this, market-wide AlphaVantage articles tagged with multiple
-- tickers leaked into the holdings news feed via .overlaps() — including
-- articles from years ago that happen to mention a holding ticker.

ALTER TABLE news_items
    ADD COLUMN IF NOT EXISTS source_type TEXT NOT NULL DEFAULT 'market_scan'
        CHECK (source_type IN ('per_holding', 'market_scan'));

-- Backfill: rows from finnhub/yfinance per-ticker fetches were the only ones
-- writing single-ticker arrays from holdings_monitor. Mark those as
-- per_holding; everything else stays market_scan.
UPDATE news_items
SET source_type = 'per_holding'
WHERE source NOT IN ('alphavantage', 'marketaux');

CREATE INDEX IF NOT EXISTS news_items_published_at_idx
    ON news_items (published_at DESC);

CREATE INDEX IF NOT EXISTS news_items_source_type_published_idx
    ON news_items (source_type, published_at DESC);
