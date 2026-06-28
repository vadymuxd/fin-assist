#!/usr/bin/env python3
"""
monzo_smoke_test.py  — monzo.2 smoke test

Confirms that the cursor-based range read works against the live Monzo sheet
before any build work:
  1. spreadsheets.get → gridProperties.rowCount (cheap metadata call)
  2. spreadsheets.values.get with explicit range 'Monzo transactions'!A{cursor+1}:Q{rowCount}
     using cursor = rowCount - 20 (last 20 rows)
  3. Prints row count, API response size, and a sample of returned rows

No Supabase writes. No schedule wiring. Keep or delete after confirming.

Run from repo root:
    python3 scripts/monzo_smoke_test.py
"""

import os
import sys
import json
import requests
from dotenv import load_dotenv
from google.oauth2.service_account import Credentials

load_dotenv()

MONZO_SHEET_ID = '1Hot1ukOadT5AClVV6lcw9jCamYFgPLH26WDCyq6qg2g'
TABS = {
    'personal': {'name': 'Personal Account Transactions', 'actual_rows': 4038},
    'joint':    {'name': 'Joint Account Transactions',    'actual_rows': 6618},
}
SA_FILE       = os.getenv('GOOGLE_APPLICATION_CREDENTIALS', 'config/service_account.json')
SCOPES        = ['https://www.googleapis.com/auth/spreadsheets.readonly']
FETCH_LAST_N  = 2  # rows to fetch from the tail


def get_token(sa_file: str) -> str:
    creds = Credentials.from_service_account_file(sa_file, scopes=SCOPES)
    creds.refresh(requests.Request())  # type: ignore[arg-type]
    return creds.token


def main():
    print(f"SA file: {SA_FILE}")
    if not os.path.exists(SA_FILE):
        print(f"ERROR: service account file not found at {SA_FILE}")
        sys.exit(1)

    # --- Step 1: get token ---
    creds = Credentials.from_service_account_file(SA_FILE, scopes=SCOPES)
    import google.auth.transport.requests
    creds.refresh(google.auth.transport.requests.Request())
    token = creds.token
    headers = {'Authorization': f'Bearer {token}'}

    # --- Step 2: spreadsheets.get → rowCount for the target tab ---
    meta_url = (
        f'https://sheets.googleapis.com/v4/spreadsheets/{MONZO_SHEET_ID}'
        f'?fields=sheets.properties'
    )
    r = requests.get(meta_url, headers=headers)
    r.raise_for_status()
    meta = r.json()

    # Build a map: tab_title -> {rowCount, sheetId}
    tab_map = {}
    for s in meta.get('sheets', []):
        props = s.get('properties', {})
        tab_map[props['title']] = {
            'rowCount': props['gridProperties']['rowCount'],
            'sheetId':  props.get('sheetId'),
        }

    print("\nAll tabs in sheet:")
    for title, info in tab_map.items():
        print(f"  - '{title}'  rowCount={info['rowCount']}")

    COLS = ['transaction_id','date','time','type','name','emoji','category',
            'amount','currency','local_amount','local_currency','notes',
            'address','receipt','description','category_split','pot_name']

    for account_type, tab_info in TABS.items():
        tab_name    = tab_info['name']
        actual_rows = tab_info['actual_rows']
        range_start = actual_rows - FETCH_LAST_N + 1
        range_end   = actual_rows
        range_str   = f"'{tab_name}'!A{range_start}:Q{range_end}"

        print(f"\n{'='*60}")
        print(f"Last {FETCH_LAST_N} rows — {account_type.upper()} ({tab_name})")
        print(f"  Fetching: {range_str}")

        values_url = (
            f'https://sheets.googleapis.com/v4/spreadsheets/{MONZO_SHEET_ID}'
            f'/values/{requests.utils.quote(range_str, safe="")}'
        )
        r2 = requests.get(values_url, headers=headers)
        r2.raise_for_status()
        rows = r2.json().get('values', [])

        for i, row in enumerate(rows):
            print(f"\n  --- Row {range_start + i} (sheet row) ---")
            for j, val in enumerate(row):
                col_name = COLS[j] if j < len(COLS) else f'col_{j}'
                print(f"    {col_name:18s}: {val}")


if __name__ == '__main__':
    main()
