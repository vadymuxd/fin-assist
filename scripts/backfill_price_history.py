#!/usr/bin/env python3
"""
One-time backfill of holding_price_history for all 15 current holdings.
Fetches ~13 months of daily closes from yfinance, converts to GBP (matching
what T212 shows and what market_worker writes), and upserts into Supabase.

Run locally (Yahoo blocks Azure/GHA IPs):
    python3 scripts/backfill_price_history.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))

from datetime import date, timedelta

import yfinance as yf
import pandas as pd

# Load env
_env_path = os.path.join(os.path.dirname(__file__), '..', '.env')
for line in open(_env_path).read().strip().splitlines():
    if '=' in line and not line.startswith('#'):
        k, v = line.split('=', 1)
        os.environ.setdefault(k.strip(), v.strip())

from lib.supabase_sink import write_holding_prices

LOOKBACK_DAYS = 430  # ~14 months — covers all buy dates

# (yf_symbol, pence_to_gbp, native_currency)
# pence_to_gbp = True  → yfinance returns GBX (pence), divide by 100 to get GBP
# native_currency      → ISO code for FX conversion to GBP (None = already GBP)
TICKERS: dict[str, tuple[str, bool, str | None]] = {
    'NVDA':   ('NVDA',       False, 'USD'),
    'RTX':    ('RTX',        False, 'USD'),
    'GOOG':   ('GOOG',       False, 'USD'),
    'TECK.B': ('TECK-B.TO',  False, 'CAD'),
    'RIO':    ('RIO.L',      True,  None),   # pence → GBP
    'SGLN':   ('SGLN.L',     True,  None),   # pence → GBP
    'INRG':   ('INRG.L',     True,  None),   # pence → GBP
    'IITU':   ('IITU.L',     True,  None),   # pence → GBP
    'RHM':    ('RHM.DE',     False, 'EUR'),
    'MAGG':   ('MAGG.L',     False, None),   # GBP already
    'PCGH':   ('PCGH.L',     True,  None),   # pence → GBP
    'UKRN':   ('UKRN.L',     False, 'USD'),  # LSE-listed but quoted in USD → convert
    'KYIV':   ('KYIV',       False, 'USD'),
    'PLTR':   ('PLTR',       False, 'USD'),
    'SWMR':   ('SWMR',       False, 'USD'),
}

start = (date.today() - timedelta(days=LOOKBACK_DAYS)).isoformat()
end   = date.today().isoformat()

# ── Fetch FX rates ────────────────────────────────────────────────────────────
# GBPUSD=X: how many USD per 1 GBP.  price_gbp = price_usd / GBPUSD
# Same logic for EUR and CAD.
print("Fetching FX rates...")
fx_series: dict[str, pd.Series] = {}
for pair, currency in [('GBPUSD=X', 'USD'), ('GBPEUR=X', 'EUR'), ('GBPCAD=X', 'CAD')]:
    hist = yf.download(pair, start=start, end=end, auto_adjust=True, progress=False)
    if isinstance(hist.columns, pd.MultiIndex):
        hist.columns = hist.columns.get_level_values(0)
    if 'Close' in hist.columns and len(hist) > 0:
        fx_series[currency] = hist['Close'].astype(float)
        print(f"  {pair}: {len(fx_series[currency])} trading days")
    else:
        print(f"  WARNING: no FX data for {pair}")

# ── Fetch price history per ticker ────────────────────────────────────────────
# date → {ticker: gbp_price}
all_rows: dict[str, dict[str, float]] = {}

for ticker, (yf_sym, is_pence, currency) in TICKERS.items():
    print(f"Fetching {ticker} ({yf_sym})...", end='  ')
    hist = yf.download(yf_sym, start=start, end=end, auto_adjust=True, progress=False)
    if isinstance(hist.columns, pd.MultiIndex):
        hist.columns = hist.columns.get_level_values(0)
    if 'Close' not in hist.columns or len(hist) == 0:
        print("NO DATA — skipping")
        continue

    prices: pd.Series = hist['Close'].astype(float)

    if is_pence:
        prices = prices / 100.0
    elif currency and currency in fx_series:
        fx = fx_series[currency].reindex(prices.index, method='ffill')
        prices = prices / fx   # price_native / (native_per_GBP) = price_gbp

    count = 0
    for idx, price in prices.items():
        if pd.isna(price) or price <= 0:
            continue
        d = idx.strftime('%Y-%m-%d') if hasattr(idx, 'strftime') else str(idx)[:10]
        all_rows.setdefault(d, {})[ticker] = round(float(price), 4)
        count += 1
    print(f"{count} rows")

# ── Write to Supabase ─────────────────────────────────────────────────────────
print(f"\nWriting {sum(len(v) for v in all_rows.values())} price records across {len(all_rows)} dates...")
success = 0
for d in sorted(all_rows.keys()):
    prices_for_day = all_rows[d]
    if prices_for_day:
        ok = write_holding_prices(d, prices_for_day)
        if ok:
            success += len(prices_for_day)

print(f"Done: {success} records upserted.")
