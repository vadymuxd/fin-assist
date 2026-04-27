#!/usr/bin/env python3
"""
pension_snapshot.py

Reads the 'Pension Balance' tab from the portfolio Google Sheet and writes
per-provider and aggregate pension data to Supabase.

Sheet format (wide time-series):
    Col A: Provider      e.g. "Nest", "Nutmeg"
    Col B: Account       e.g. "Workplace Pension", "Personal Pension"
    Col C: Type          e.g. "workplace" / "personal" / "sipp" / "lisa"
    Col D+: [Month Year] e.g. "April 2026 Balance", "May 2026 Balance"

For each month column that has data, one row per provider/account is upserted
into `pension_accounts`, and an aggregate row into `pension_snapshots`.

Run from repo root:
    python3 scripts/pension_snapshot.py
"""

import os
import sys
import calendar
import re
from datetime import date
from dotenv import load_dotenv
import gspread
from google.oauth2.service_account import Credentials

from lib.supabase_sink import write_pension_accounts, write_pension_snapshot

load_dotenv()

SHEET_ID  = os.getenv('PORTFOLIO_SHEET_ID')
SA_FILE   = os.getenv('GOOGLE_APPLICATION_CREDENTIALS', 'config/service_account.json')
SCOPES    = ['https://www.googleapis.com/auth/spreadsheets']
TAB_NAME  = 'Pension Balance'

MONTH_NAMES = {
    'january': 1, 'february': 2, 'march': 3, 'april': 4,
    'may': 5, 'june': 6, 'july': 7, 'august': 8,
    'september': 9, 'october': 10, 'november': 11, 'december': 12,
    'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4,
    'jun': 6, 'jul': 7, 'aug': 8,
    'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12,
}


def parse_month_header(header: str) -> str | None:
    """
    Parse month-year headers: 'April 2026 Balance', 'April 2026', 'Apr 2026'.
    Returns ISO date string for last day of that month, or None if unrecognised.
    """
    m = re.match(r'(\w+)\s+(\d{4})(?:\s+.*)?$', header.strip(), re.IGNORECASE)
    if not m:
        return None
    month_name, year_str = m.group(1).lower(), int(m.group(2))
    month_num = MONTH_NAMES.get(month_name)
    if not month_num:
        return None
    last_day = calendar.monthrange(year_str, month_num)[1]
    return date(year_str, month_num, last_day).isoformat()


def parse_float(val) -> float | None:
    if val is None or str(val).strip() == '':
        return None
    try:
        return float(str(val).replace('£', '').replace(',', '').replace('%', '').strip())
    except (ValueError, TypeError):
        return None


def main():
    print(f"\nPension snapshot — {date.today()}")

    print("\nConnecting to Google Sheets...")
    creds = Credentials.from_service_account_file(SA_FILE, scopes=SCOPES)
    gc    = gspread.authorize(creds)
    sh    = gc.open_by_key(SHEET_ID)
    ws    = sh.worksheet(TAB_NAME)
    print(f"  Opened: {sh.title} / {TAB_NAME}")

    all_rows = ws.get_all_values()
    if not all_rows:
        print("  Sheet is empty — nothing to do.")
        return

    headers = [h.strip() for h in all_rows[0]]
    headers_lower = [h.lower() for h in headers]

    def find_col(*candidates: str) -> int | None:
        for h_lower, i in zip(headers_lower, range(len(headers_lower))):
            for c in candidates:
                if h_lower.startswith(c.lower()):
                    return i
        return None

    provider_col = find_col('provider')
    account_col  = find_col('account')
    type_col     = find_col('type')

    if provider_col is None or account_col is None:
        print("  ERROR: Could not find 'Provider' or 'Account' columns in header row.")
        print(f"  Headers found: {headers}")
        sys.exit(1)

    # Identify month columns
    month_cols: list[tuple[int, str]] = []
    for i, h in enumerate(headers):
        parsed = parse_month_header(h)
        if parsed:
            month_cols.append((i, parsed))

    if not month_cols:
        print("  No month columns found (expected format: 'April 2026 Balance').")
        sys.exit(1)

    print(f"  Found {len(month_cols)} month column(s): {[d for _, d in month_cols]}")

    account_rows: list[dict] = []
    data_rows = [r for r in all_rows[1:] if any(c.strip() for c in r)]

    for row in data_rows:
        def cell(idx):
            return row[idx].strip() if idx is not None and idx < len(row) else ''

        provider     = cell(provider_col)
        account      = cell(account_col)
        acct_type    = cell(type_col).lower() if type_col is not None else None
        acct_type    = acct_type or None

        if not provider or not account:
            continue

        for col_i, date_iso in month_cols:
            raw = row[col_i].strip() if col_i < len(row) else ''
            balance = parse_float(raw)
            if balance is None:
                continue

            account_rows.append({
                'date':         date_iso,
                'provider':     provider,
                'account_name': account,
                'account_type': acct_type,
                'balance_gbp':  balance,
            })

    if not account_rows:
        print("  No pension balance data found.")
        return

    print(f"\n  {len(account_rows)} provider-date rows to upsert...")
    ok = write_pension_accounts(account_rows)
    if not ok:
        print("  ERROR: pension_accounts write failed.")
        sys.exit(1)
    print("  pension_accounts — done.")

    # Build per-date aggregate snapshots
    from collections import defaultdict
    date_totals: dict[str, float] = defaultdict(float)
    for row in account_rows:
        date_totals[row['date']] += float(row['balance_gbp'])

    errors = 0
    for d, total in sorted(date_totals.items()):
        ok2 = write_pension_snapshot(d, total)
        if ok2:
            print(f"  pension_snapshots {d} — £{total:,.2f}")
        else:
            print(f"  ERROR: pension_snapshots write failed for {d}")
            errors += 1

    if errors:
        sys.exit(1)

    print("\nAll done.")


if __name__ == '__main__':
    main()
