#!/usr/bin/env python3
"""
daily_portfolio_snapshot.py

Reads portfolio totals + benchmark index values from Inv26 - Summary and
inserts one row into the Supabase `portfolio_snapshots` table.
Runs daily after the 15:30 UTC close via GitHub Actions (or manual dispatch).

Run from repo root:
    python3 scripts/daily_portfolio_snapshot.py
"""

import os
import sys
from datetime import date, datetime, timezone
from dotenv import load_dotenv
import gspread
from google.oauth2.service_account import Credentials

from lib.supabase_sink import write_portfolio_snapshot

load_dotenv()

SHEET_ID = os.getenv('PORTFOLIO_SHEET_ID')
SA_FILE  = os.getenv('GOOGLE_APPLICATION_CREDENTIALS', 'config/service_account.json')
SCOPES   = ['https://www.googleapis.com/auth/spreadsheets']

# Row numbers in Inv26 - Summary (1-based)
ROW_GRAND_TOTAL   = 7
ROW_CASH          = 9
ROW_STOCKS_TOTAL  = 11
ROW_MANAGED_TOTAL = 28
ROW_SP500         = 32
ROW_FTSE100       = 33
ROW_NASDAQ100     = 34
ROW_MSCI_WORLD    = 35
ROW_GOLD          = 36
COL_VALUE_IDX     = 6   # 0-based index → col G


def parse_float(val):
    if val is None or val == '':
        return 0.0
    try:
        return float(str(val).replace('£', '').replace(',', '').replace('%', '').strip())
    except (ValueError, TypeError):
        return 0.0


def read_cell(ws, row, col_idx):
    row_vals = ws.row_values(row)
    return parse_float(row_vals[col_idx]) if len(row_vals) > col_idx else 0.0


def read_net_deposits(sh):
    ws   = sh.worksheet('InvTransactions')
    rows = ws.get_all_values()
    return sum(
        parse_float(row[6])
        for row in rows[1:]
        if len(row) > 6 and row[3].strip().upper() == 'DEPOSIT'
    )


def main():
    today = date.today().isoformat()
    print(f"\nPortfolio snapshot — {today}")

    print("\nConnecting to Google Sheets...")
    creds = Credentials.from_service_account_file(SA_FILE, scopes=SCOPES)
    gc    = gspread.authorize(creds)
    sh    = gc.open_by_key(SHEET_ID)
    print(f"  Opened: {sh.title}")

    ws = sh.worksheet('Inv26 - Summary')

    totals = {
        'grand_total':  read_cell(ws, ROW_GRAND_TOTAL,   COL_VALUE_IDX),
        'self_managed': read_cell(ws, ROW_STOCKS_TOTAL,  COL_VALUE_IDX),
        'managed':      read_cell(ws, ROW_MANAGED_TOTAL, COL_VALUE_IDX),
        'cash':         read_cell(ws, ROW_CASH,          COL_VALUE_IDX),
        'spx':          read_cell(ws, ROW_SP500,         COL_VALUE_IDX),
        'ftse':         read_cell(ws, ROW_FTSE100,       COL_VALUE_IDX),
        'ndx':          read_cell(ws, ROW_NASDAQ100,     COL_VALUE_IDX),
        'msci':         read_cell(ws, ROW_MSCI_WORLD,    COL_VALUE_IDX),
        'gold':         read_cell(ws, ROW_GOLD,          COL_VALUE_IDX),
    }

    print("\nReading net deposits from InvTransactions...")
    totals['net_deposits'] = read_net_deposits(sh)

    print(f"\n  Grand total:    £{totals['grand_total']:,.2f}")
    print(f"  Self-managed:   £{totals['self_managed']:,.2f}")
    print(f"  Managed:        £{totals['managed']:,.2f}")
    print(f"  Cash:           £{totals['cash']:,.2f}")
    print(f"  Net deposits:   £{totals['net_deposits']:,.2f}")
    print(f"  Benchmarks: S&P {totals['spx']:.2f} | FTSE {totals['ftse']:.2f} | "
          f"NDX {totals['ndx']:.2f} | MSCI {totals['msci']:.2f} | Gold {totals['gold']:.2f}")

    print("\nWriting to Supabase portfolio_snapshots...")
    ok = write_portfolio_snapshot(today, totals)
    if ok:
        print(f"  Done — {today} upserted.")
    else:
        print("  Supabase write failed (check logs). Sheet data unchanged.")
        sys.exit(1)


if __name__ == '__main__':
    main()
