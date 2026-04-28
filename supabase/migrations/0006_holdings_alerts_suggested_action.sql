-- Phase 9 pipeline refactor: add suggested_action to holdings_alerts.
-- The new alert_dispatcher.py only logs ACT-level alerts (no NONE/WATCH noise),
-- and records the specific action recommended (SELL, TRIM, EXIT, BUY_MORE).
-- Existing rows from the old holdings_monitor.py auto-mode get NULL here — fine.

ALTER TABLE holdings_alerts
    ADD COLUMN IF NOT EXISTS suggested_action TEXT;

CREATE INDEX IF NOT EXISTS holdings_alerts_suggested_action_idx
    ON holdings_alerts (suggested_action);
