-- 0017_holding_price_history.sql
-- Per-ticker daily price history. One row per (ticker, date), upserted on
-- every daily_monitor run so the last write of the day wins.
-- Powers the trailing-stop sell signal in market_worker.py: a position that
-- has fallen >X% from its rolling high over the last N days is flagged.
-- Cost-basis stop-loss and concentration signals do NOT need this table —
-- if it is missing, trailing-stop simply stays quiet (writers fail open).

CREATE TABLE IF NOT EXISTS holding_price_history (
    id          BIGSERIAL PRIMARY KEY,
    ticker      TEXT NOT NULL,
    date        DATE NOT NULL,
    price       NUMERIC NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT now(),
    UNIQUE (ticker, date)
);

CREATE INDEX IF NOT EXISTS holding_price_history_ticker_date_idx
    ON holding_price_history (ticker, date DESC);

ALTER TABLE holding_price_history ENABLE ROW LEVEL SECURITY;

CREATE POLICY "public_select_holding_price_history"
    ON holding_price_history FOR SELECT USING (true);
