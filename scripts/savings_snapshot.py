#!/usr/bin/env python3
"""
savings_snapshot.py

Reads the 'Savings Balance' tab from the portfolio Google Sheet and writes
per-account and aggregate savings data to Supabase.

Sheet format (wide time-series):
    Col A: Bank
    Col B: Account
    Col C: Type          (savings / isa / pot / current)
    Col D: Owner         (Personal / Joint)
    Col E+: [Month Year Balance]  e.g. "April 2026 Balance", "May 2026 Balance"

For each month column that has data, one row per account is upserted into
`savings_accounts`, and an aggregate row is upserted into `savings_snapshots`.

Run from repo root:
    python3 scripts/savings_snapshot.py
"""

import os
import sys
import calendar
import re
from datetime import date
from dotenv import load_dotenv
import gspread
from google.oauth2.service_account import Credentials

from lib.supabase_sink import write_savings_accounts, write_savings_snapshot

load_dotenv()

SHEET_ID  = os.getenv('PORTFOLIO_SHEET_ID')
SA_FILE   = os.getenv('GOOGLE_APPLICATION_CREDENTIALS', 'config/service_account.json')
SCOPES    = ['https://www.googleapis.com/auth/spreadsheets']
TAB_NAME  = 'Savings Balance'

MONTH_NAMES = {
    # full names
    'january': 1, 'february': 2, 'march': 3, 'april': 4,
    'may': 5, 'june': 6, 'july': 7, 'august': 8,
    'september': 9, 'october': 10, 'november': 11, 'december': 12,
    # 3-letter abbreviations
    'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4,
    'jun': 6, 'jul': 7, 'aug': 8,
    'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12,
}


def parse_month_header(header: str) -> str | None:
    """
    Parse month-year headers in multiple formats:
      'April 2026 Balance', 'April 2026', 'Apr 2026', 'Apr 2026 Balance'
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
    print(f"\nSavings snapshot — {date.today()}")

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
        """Return first column index whose lowercased name starts with any candidate."""
        for h_lower, i in zip(headers_lower, range(len(headers_lower))):
            for c in candidates:
                if h_lower.startswith(c.lower()):
                    return i
        return None

    bank_col    = find_col('bank')
    account_col = find_col('account')   # matches 'Account', 'Account Name', etc.
    type_col    = find_col('type')
    owner_col   = find_col('owner')

    if bank_col is None or account_col is None:
        print("  ERROR: Could not find 'Bank' or 'Account' columns in header row.")
        print(f"  Headers found: {headers}")
        sys.exit(1)

    if owner_col is None:
        print("  No 'Owner' column — will infer owner from 'Type' column if it contains Personal/Joint.")

    # Identify month columns
    month_cols: list[tuple[int, str]] = []  # (col_index, date_iso)
    for i, h in enumerate(headers):
        parsed = parse_month_header(h)
        if parsed:
            month_cols.append((i, parsed))

    if not month_cols:
        print("  No month columns found (expected format: 'April 2026 Balance').")
        sys.exit(1)

    print(f"  Found {len(month_cols)} month column(s): "
          f"{[d for _, d in month_cols]}")

    # Build per-account rows for all months
    account_rows: list[dict] = []
    data_rows = [r for r in all_rows[1:] if any(c.strip() for c in r)]

    for row in data_rows:
        def cell(idx):
            return row[idx].strip() if idx is not None and idx < len(row) else ''

        bank    = cell(bank_col)
        account = cell(account_col)
        raw_type = cell(type_col) if type_col is not None else ''
        type_lower = raw_type.lower().strip()

        if owner_col is not None:
            # Separate Owner column exists — ideal setup
            acct_type = type_lower or None
            owner = cell(owner_col).strip() or 'Personal'
        elif type_lower in ('personal', 'joint'):
            # Type column is being used for owner (Personal/Joint) — no separate account type
            acct_type = None
            owner = raw_type.strip()
        else:
            # Type column has real account type info, default owner to Personal
            acct_type = type_lower or None
            owner = 'Personal'

        if not bank or not account:
            continue

        for col_i, date_iso in month_cols:
            raw = row[col_i].strip() if col_i < len(row) else ''
            balance = parse_float(raw)
            if balance is None:
                continue

            account_rows.append({
                'date':         date_iso,
                'bank':         bank,
                'account_name': account,
                'account_type': acct_type,
                'owner':        owner,
                'balance_gbp':  balance,
            })

    if not account_rows:
        print("  No account balance data found.")
        return

    print(f"\n  {len(account_rows)} account-date rows to upsert...")
    ok = write_savings_accounts(account_rows)
    if not ok:
        print("  ERROR: savings_accounts write failed.")
        sys.exit(1)
    print("  savings_accounts — done.")

    # Build per-date aggregate snapshots
    from collections import defaultdict
    date_totals: dict[str, dict[str, float]] = defaultdict(lambda: {'total': 0.0, 'personal': 0.0, 'joint': 0.0})
    for row in account_rows:
        d = row['date']
        v = float(row['balance_gbp'])
        date_totals[d]['total'] += v
        if row['owner'].strip().lower() == 'joint':
            date_totals[d]['joint'] += v
        else:
            date_totals[d]['personal'] += v

    errors = 0
    for d, totals in sorted(date_totals.items()):
        ok2 = write_savings_snapshot(d, totals['total'], totals['personal'], totals['joint'])
        if ok2:
            print(f"  savings_snapshots {d} — £{totals['total']:,.2f} "
                  f"(personal £{totals['personal']:,.2f} / joint £{totals['joint']:,.2f})")
        else:
            print(f"  ERROR: savings_snapshots write failed for {d}")
            errors += 1

    if errors:
        sys.exit(1)

    print("\nAll done.")


if __name__ == '__main__':
    main()
