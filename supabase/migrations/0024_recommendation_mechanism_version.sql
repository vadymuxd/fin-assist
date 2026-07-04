-- Migration 0024: holdings_alerts.mechanism_version (Work 4 follow-up)
--
-- Work 4 (2026-07-04) backtested every ACT-level holdings_alerts row and found
-- real weaknesses in the recommendation mechanism: the score field clustered
-- at 8/10 with no real spread, the deterministic stop-loss SELL had zero
-- trend awareness (fired right before rebounds twice), and BUY_MORE fired on
-- positive news even when the stock was already in a confirmed downtrend.
--
-- market_worker.py was rebuilt the same session (trend-aware AI confirmation
-- layer, catalyst-level dedup) — see Scripts & Automation for the mechanism
-- detail. This column tags which mechanism version produced each row, so a
-- future re-run of scripts/analyze_recommendations.py can cleanly compare
-- "did v2 actually do better than v1" without the manual archaeology
-- (checking row ids / dates against session notes) this session needed to
-- confirm all 20 existing rows were pre-rebuild.
--
-- All 20 existing rows (2026-05-18 -> 2026-06-29) predate the rebuild and are
-- backfilled as 'v1_price_or_news' (deterministic price signal OR standalone
-- Claude news judgment, whichever fired first, no trend input, no AI
-- confirmation of price-triggered signals). New rows from market_worker.py
-- going forward are tagged 'v2_trend_confirmed' by the script itself.

ALTER TABLE holdings_alerts
    ADD COLUMN IF NOT EXISTS mechanism_version TEXT;

UPDATE holdings_alerts
    SET mechanism_version = 'v1_price_or_news'
    WHERE mechanism_version IS NULL;
