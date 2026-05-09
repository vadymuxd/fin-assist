"""
backfill_lisa_total.py

One-off: reads Lisa's starting investment value from cell I39 of the
Investments sheet, then fills every portfolio_snapshots row where
lisa_total IS NULL (all historical rows before ROW_LISA_TOTAL was wired up).

Run once from the repo root:
    python scripts/backfill_lisa_total.py
"""

import os
import sys
from dotenv import load_dotenv
import gspread
from google.oauth2.service_account import Credentials
from supabase import create_client

load_dotenv()

SHEET_ID = os.getenv('PORTFOLIO_SHEET_ID')
SA_FILE  = os.getenv('GOOGLE_APPLICATION_CREDENTIALS', 'config/service_account.json')
SCOPES   = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']

LISA_ROW       = 39   # 1-based row in Investments sheet
LISA_START_COL = 9    # column I (1-based) — starting value column

def parse_float(val):
    if val is None or val == '':
        return None
    try:
        return float(str(val).replace('£', '').replace(',', '').strip())
    except ValueError:
        return None

def main():
    # ── 1. Read Lisa's start value from the sheet ────────────────────────────
    print("Connecting to Google Sheets...")
    creds = Credentials.from_service_account_file(SA_FILE, scopes=SCOPES)
    sh = gspread.authorize(creds).open_by_key(SHEET_ID)
    ws = sh.worksheet('Investments')

    raw = ws.cell(LISA_ROW, LISA_START_COL).value
    lisa_start = parse_float(raw)
    if lisa_start is None:
        print(f"ERROR: cell I{LISA_ROW} is empty or unparseable (raw={raw!r}). Aborting.")
        sys.exit(1)
    print(f"  Lisa starting value from I{LISA_ROW}: £{lisa_start:,.2f}")

    # ── 2. Connect to Supabase ───────────────────────────────────────────────
    url = os.getenv('SUPABASE_URL', '')
    key = os.getenv('SUPABASE_SERVICE_ROLE_KEY', '')
    if not url or not key:
        print("ERROR: SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY not set.")
        sys.exit(1)
    client = create_client(url, key)

    # ── 3. Find rows where lisa_total is NULL ────────────────────────────────
    resp = (
        client.table('portfolio_snapshots')
        .select('date')
        .is_('lisa_total', 'null')
        .order('date')
        .execute()
    )
    null_rows = resp.data or []
    if not null_rows:
        print("No rows with NULL lisa_total found — nothing to backfill.")
        return

    dates = [r['date'] for r in null_rows]
    print(f"\n  Found {len(dates)} rows with NULL lisa_total:")
    print(f"  {dates[0]} → {dates[-1]}")

    # ── 4. Upsert lisa_total = lisa_start for all NULL rows ──────────────────
    updates = [{'date': d, 'lisa_total': lisa_start} for d in dates]
    print(f"\n  Backfilling {len(updates)} rows with £{lisa_start:,.2f}...")

    client.table('portfolio_snapshots').upsert(updates, on_conflict='date').execute()
    print(f"  Done. All {len(updates)} rows now have lisa_total = £{lisa_start:,.2f}")
    print("\nNote: historical rows use the starting value (flat line). Real per-day")
    print("tracking begins from the first sync after ROW_LISA_TOTAL was set (2026-05-09).")

if __name__ == '__main__':
    main()
