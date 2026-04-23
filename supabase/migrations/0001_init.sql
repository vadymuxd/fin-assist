-- Phase 6A: Initial schema
-- Public SELECT via anon key; INSERT/UPDATE/DELETE require service-role key.

-- ─── TABLES ──────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS holdings (
    ticker              TEXT PRIMARY KEY,
    name                TEXT,
    platform            TEXT,
    qty                 NUMERIC,
    avg_buy             NUMERIC,
    current_price       NUMERIC,
    pnl_abs             NUMERIC,
    pnl_pct             NUMERIC,
    sector              TEXT,
    market              TEXT,
    last_updated        TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS portfolio_snapshots (
    id              BIGSERIAL PRIMARY KEY,
    date            DATE UNIQUE NOT NULL,
    grand_total     NUMERIC,
    self_managed    NUMERIC,
    managed         NUMERIC,
    cash            NUMERIC,
    net_deposits    NUMERIC,
    spx             NUMERIC,
    ftse            NUMERIC,
    ndx             NUMERIC,
    msci            NUMERIC,
    gold            NUMERIC,
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS trend_snapshots (
    id                  BIGSERIAL PRIMARY KEY,
    snapshot_date       DATE UNIQUE NOT NULL,
    grand_total         NUMERIC,
    self_managed        NUMERIC,
    managed             NUMERIC,
    net_deposits        NUMERIC,
    spx                 NUMERIC,
    ftse                NUMERIC,
    ndx                 NUMERIC,
    msci                NUMERIC,
    gold                NUMERIC,
    grand_total_pct     NUMERIC,
    self_managed_pct    NUMERIC,
    managed_pct         NUMERIC,
    spx_pct             NUMERIC,
    ftse_pct            NUMERIC,
    ndx_pct             NUMERIC,
    msci_pct            NUMERIC,
    gold_pct            NUMERIC,
    created_at          TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS discoveries (
    id                      BIGSERIAL PRIMARY KEY,
    run_id                  TEXT NOT NULL,
    run_time                TIMESTAMPTZ NOT NULL,
    ticker                  TEXT NOT NULL,
    score                   INTEGER,
    recommendation          TEXT,
    sources                 TEXT[],
    rationale               TEXT,
    filtered_reason         TEXT,
    surfaced_to_telegram    BOOLEAN DEFAULT false,
    created_at              TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS holdings_alerts (
    id              BIGSERIAL PRIMARY KEY,
    run_id          TEXT NOT NULL,
    run_time        TIMESTAMPTZ NOT NULL,
    ticker          TEXT NOT NULL,
    alert_level     TEXT NOT NULL,  -- NONE / WATCH / ACT
    score           INTEGER,
    event           TEXT,
    rationale       TEXT,
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS news_items (
    id              TEXT PRIMARY KEY,
    published_at    TIMESTAMPTZ,
    tickers         TEXT[],
    source          TEXT,
    title           TEXT,
    url             TEXT UNIQUE,
    image_url       TEXT,
    snippet         TEXT,
    sentiment       TEXT,   -- bullish / bearish / neutral
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS sectors (
    ticker          TEXT PRIMARY KEY,
    sector          TEXT,
    market          TEXT,
    last_updated    TIMESTAMPTZ DEFAULT now()
);

-- ─── INDEXES ─────────────────────────────────────────────────────────────────

CREATE INDEX IF NOT EXISTS discoveries_run_time_idx   ON discoveries (run_time DESC);
CREATE INDEX IF NOT EXISTS discoveries_ticker_idx     ON discoveries (ticker);
CREATE INDEX IF NOT EXISTS holdings_alerts_run_time_idx ON holdings_alerts (run_time DESC);
CREATE INDEX IF NOT EXISTS holdings_alerts_ticker_idx ON holdings_alerts (ticker);
CREATE INDEX IF NOT EXISTS news_items_published_at_idx ON news_items (published_at DESC);
CREATE INDEX IF NOT EXISTS news_items_tickers_idx     ON news_items USING GIN (tickers);
CREATE INDEX IF NOT EXISTS portfolio_snapshots_date_idx ON portfolio_snapshots (date DESC);

-- ─── RLS ─────────────────────────────────────────────────────────────────────

ALTER TABLE holdings           ENABLE ROW LEVEL SECURITY;
ALTER TABLE portfolio_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE trend_snapshots    ENABLE ROW LEVEL SECURITY;
ALTER TABLE discoveries        ENABLE ROW LEVEL SECURITY;
ALTER TABLE holdings_alerts    ENABLE ROW LEVEL SECURITY;
ALTER TABLE news_items         ENABLE ROW LEVEL SECURITY;
ALTER TABLE sectors            ENABLE ROW LEVEL SECURITY;

-- Public read for all tables (anon key)
CREATE POLICY "public_select_holdings"            ON holdings            FOR SELECT USING (true);
CREATE POLICY "public_select_portfolio_snapshots" ON portfolio_snapshots FOR SELECT USING (true);
CREATE POLICY "public_select_trend_snapshots"     ON trend_snapshots     FOR SELECT USING (true);
CREATE POLICY "public_select_discoveries"         ON discoveries         FOR SELECT USING (true);
CREATE POLICY "public_select_holdings_alerts"     ON holdings_alerts     FOR SELECT USING (true);
CREATE POLICY "public_select_news_items"          ON news_items          FOR SELECT USING (true);
CREATE POLICY "public_select_sectors"             ON sectors             FOR SELECT USING (true);

-- Writes: service-role only (bypasses RLS automatically — no policy needed)
