#!/usr/bin/env python3
"""
migrate_holding_trades.py

1. Creates the holding_trades table in Supabase (idempotent).
2. Reads all BUY/SELL rows from InvTransactions Google Sheet.
3. Upserts them into holding_trades.

Run once to bootstrap; log_trades.py will maintain the table going forward.
"""

import os
import sys
import requests as _req
from dotenv import load_dotenv
import gspread
from google.oauth2.service_account import Credentials

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

SUPABASE_URL   = os.getenv('SUPABASE_URL', '')
SERVICE_KEY    = os.getenv('SUPABASE_SERVICE_ROLE_KEY', '')
ACCESS_TOKEN   = os.getenv('SUPABASE_ACCESS_TOKEN', '')
SHEET_ID       = os.getenv('PORTFOLIO_SHEET_ID', '')
SA_FILE        = os.getenv('GOOGLE_SHEETS_CREDS', 'config/service_account.json')
PROJECT_REF    = SUPABASE_URL.replace('https://', '').split('.')[0]

SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly']

CREATE_SQL = """
CREATE TABLE IF NOT EXISTS holding_trades (
    id         SERIAL PRIMARY KEY,
    date       DATE          NOT NULL,
    ticker     TEXT          NOT NULL,
    action     TEXT          NOT NULL CHECK (action IN ('BUY', 'SELL')),
    qty        NUMERIC(18,8) NOT NULL,
    price_gbp  NUMERIC(18,6) NOT NULL,
    total_gbp  NUMERIC(18,2) NOT NULL,
    platform   TEXT,
    notes      TEXT,
    created_at TIMESTAMPTZ   DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_holding_trades_ticker_date
    ON holding_trades(ticker, date);
"""


def run_sql(sql: str) -> dict:
    resp = _req.post(
        f'https://api.supabase.com/v1/projects/{PROJECT_REF}/database/query',
        headers={
            'Authorization': f'Bearer {ACCESS_TOKEN}',
            'Content-Type': 'application/json',
        },
        json={'query': sql},
        timeout=15,
    )
    if resp.status_code not in (200, 201):
        print(f'SQL error {resp.status_code}: {resp.text}')
        sys.exit(1)
    return resp.json()


def supabase_upsert(rows: list[dict]) -> None:
    if not rows:
        return
    resp = _req.post(
        f'{SUPABASE_URL}/rest/v1/holding_trades',
        headers={
            'apikey': SERVICE_KEY,
            'Authorization': f'Bearer {SERVICE_KEY}',
            'Content-Type': 'application/json',
            'Prefer': 'resolution=merge-duplicates',
        },
        json=rows,
        timeout=20,
    )
    if resp.status_code not in (200, 201):
        print(f'Upsert error {resp.status_code}: {resp.text[:400]}')
        sys.exit(1)


def open_sheet():
    sa_path = SA_FILE if os.path.isabs(SA_FILE) else os.path.join(
        os.path.dirname(__file__), '..', SA_FILE)
    creds = Credentials.from_service_account_file(sa_path, scopes=SCOPES)
    gc = gspread.authorize(creds)
    return gc.open_by_key(SHEET_ID)


def parse_float(val):
    if val is None or str(val).strip() == '':
        return 0.0
    try:
        return float(str(val).replace('£', '').replace(',', '').strip())
    except (ValueError, TypeError):
        return 0.0


def main():
    print(f'Project ref: {PROJECT_REF}')

    # 1. Create table
    print('\nCreating holding_trades table (idempotent)...')
    run_sql(CREATE_SQL)
    print('  Done.')

    # 2. Read InvTransactions
    print('\nReading InvTransactions from Google Sheets...')
    sh = open_sheet()
    ws = sh.worksheet('InvTransactions')
    rows = ws.get_all_values()
    print(f'  {len(rows)} total rows (incl. header)')

    # Row format: date, ticker, name, action, qty, price, total, platform, notes
    trades = []
    skipped = 0
    for i, row in enumerate(rows[1:], start=2):
        if len(row) < 4:
            continue
        action = row[3].strip().upper()
        if action not in ('BUY', 'SELL'):
            skipped += 1
            continue
        date   = row[0].strip()
        ticker = row[1].strip()
        qty    = parse_float(row[4] if len(row) > 4 else '')
        price  = parse_float(row[5] if len(row) > 5 else '')
        total  = parse_float(row[6] if len(row) > 6 else '')
        platform = row[7].strip() if len(row) > 7 else ''
        notes    = row[8].strip() if len(row) > 8 else ''

        if not date or not ticker or qty <= 0:
            print(f'  Row {i}: skipping (incomplete: date={date!r} ticker={ticker!r} qty={qty})')
            skipped += 1
            continue

        trades.append({
            'date':      date,
            'ticker':    ticker,
            'action':    action,
            'qty':       qty,
            'price_gbp': price,
            'total_gbp': total,
            'platform':  platform or None,
            'notes':     notes or None,
        })

    print(f'  {len(trades)} BUY/SELL trades to insert ({skipped} non-stock rows skipped)')

    # 3. Upsert to Supabase (delete existing rows first for a clean backfill)
    print('\nClearing existing rows...')
    _req.delete(
        f'{SUPABASE_URL}/rest/v1/holding_trades',
        headers={
            'apikey': SERVICE_KEY,
            'Authorization': f'Bearer {SERVICE_KEY}',
            'Prefer': 'return=minimal',
        },
        params={'id': 'gte.0'},
        timeout=15,
    )

    print('Inserting trades...')
    # Insert in batches of 200
    for i in range(0, len(trades), 200):
        batch = trades[i:i + 200]
        supabase_upsert(batch)
        print(f'  Inserted rows {i+1}–{i+len(batch)}')

    # 4. Summary by ticker
    from collections import Counter
    counts = Counter(t['ticker'] for t in trades)
    print('\nTrades by ticker:')
    for ticker, n in sorted(counts.items()):
        print(f'  {ticker}: {n}')

    print('\n✓ Done. holding_trades is populated.')


if __name__ == '__main__':
    main()
