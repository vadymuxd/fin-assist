#!/usr/bin/env python3
"""
fix_ukrn_price_and_tracking.py — one-off repair + schema bump.

1. ALTER holdings: add tracking_started_value + tracking_pnl_pct (Sheet cols I, K).
2. Re-backfill UKRN price history with USD→GBP conversion.
   UKRN.L is LSE-listed but quoted in USD by yfinance; the original
   backfill_price_history.py classified it as GBP (no conversion), so every
   stored price was ~1.26-1.36× too high. This re-fetches and overwrites.
3. Backfill tracking_started_value (col I) + tracking_pnl_pct (col K) per
   holding from the Investments sheet, so the app header matches the Sheet's
   "Tracking 26 P&L %" exactly.

Run once:  python3 scripts/fix_ukrn_price_and_tracking.py
"""
import os
import sys
import requests as _req

sys.path.insert(0, os.path.dirname(__file__))

import yfinance as yf
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials

_env_path = os.path.join(os.path.dirname(__file__), '..', '.env')
for line in open(_env_path).read().strip().splitlines():
    if '=' in line and not line.startswith('#'):
        k, v = line.split('=', 1)
        os.environ.setdefault(k.strip(), v.strip())

from lib.supabase_sink import write_holding_prices, _get_client

SUPABASE_URL = os.getenv('SUPABASE_URL', '')
ACCESS_TOKEN = os.getenv('SUPABASE_ACCESS_TOKEN', '')
PROJECT_REF  = SUPABASE_URL.replace('https://', '').split('.')[0]
SHEET_ID     = os.getenv('PORTFOLIO_SHEET_ID', '')
SA_FILE      = os.getenv('GOOGLE_APPLICATION_CREDENTIALS', 'config/service_account.json')


def run_sql(sql: str) -> None:
    resp = _req.post(
        f'https://api.supabase.com/v1/projects/{PROJECT_REF}/database/query',
        headers={'Authorization': f'Bearer {ACCESS_TOKEN}', 'Content-Type': 'application/json'},
        json={'query': sql},
        timeout=15,
    )
    if resp.status_code not in (200, 201):
        print(f'  SQL error {resp.status_code}: {resp.text}')
        sys.exit(1)


def parse_float(s) -> float:
    if s is None:
        return 0.0
    s = str(s).replace('£', '').replace(',', '').replace('%', '').strip()
    if not s or s in ('-', '—'):
        return 0.0
    try:
        return float(s)
    except ValueError:
        return 0.0


# ── 1. Schema ──────────────────────────────────────────────────────────────────
print('1. Adding tracking columns to holdings...')
run_sql("""
ALTER TABLE holdings ADD COLUMN IF NOT EXISTS tracking_started_value NUMERIC(18,2);
ALTER TABLE holdings ADD COLUMN IF NOT EXISTS tracking_pnl_pct       NUMERIC(10,4);
""")
print('   done.')

# ── 2. UKRN price history (USD → GBP) ───────────────────────────────────────────
print('2. Re-backfilling UKRN price history (USD→GBP)...')
start, end = '2026-03-01', (pd.Timestamp.today() + pd.Timedelta(days=1)).strftime('%Y-%m-%d')


def closes(sym):
    h = yf.download(sym, start=start, end=end, auto_adjust=True, progress=False)
    if isinstance(h.columns, pd.MultiIndex):
        h.columns = h.columns.get_level_values(0)
    return h['Close'].astype(float)


ukrn_usd = closes('UKRN.L')
fx = closes('GBPUSD=X').reindex(ukrn_usd.index, method='ffill')  # USD per GBP
ukrn_gbp = ukrn_usd / fx

count = 0
for idx, price in ukrn_gbp.items():
    if pd.isna(price) or price <= 0:
        continue
    d = idx.strftime('%Y-%m-%d')
    if write_holding_prices(d, {'UKRN': round(float(price), 4)}):
        count += 1
print(f'   {count} UKRN rows upserted (Apr13={ukrn_gbp.get(pd.Timestamp("2026-04-13")):.4f}, '
      f'last={ukrn_gbp.iloc[-1]:.4f}).')

# ── 3. Tracking started value + P&L % per holding (Sheet cols I, K) ─────────────
print('3. Syncing tracking_started_value (col I) + tracking_pnl_pct (col K)...')
creds = Credentials.from_service_account_file(SA_FILE, scopes=['https://www.googleapis.com/auth/spreadsheets'])
ws = gspread.authorize(creds).open_by_key(SHEET_ID).worksheet('Investments')
rows = ws.get_all_values()
client = _get_client()

SKIP = {'ticker', 'name', 'total', 'stocks', 'cash', 'managed', 'grand',
        'benchmark', 's&p', 'ftse', 'nasdaq', 'msci', 'gold', ''}
updated = 0
for row in rows:
    if len(row) < 11:
        continue
    ticker = row[0].strip()
    if not ticker or ticker.startswith('=') or ticker.lower() in SKIP:
        continue
    if parse_float(row[3]) <= 0:  # qty
        continue
    started = parse_float(row[8])   # col I
    pnl_pct = parse_float(row[10])  # col K
    client.table('holdings').update({
        'tracking_started_value': started,
        'tracking_pnl_pct': pnl_pct,
    }).eq('ticker', ticker).execute()
    updated += 1
    print(f'   {ticker:7} started=£{started:>10,.2f}  tracking={pnl_pct:>7.2f}%')

print(f'   {updated} holdings updated.')
print('\nDone.')
