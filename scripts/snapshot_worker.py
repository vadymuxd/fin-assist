#!/usr/bin/env python3
"""
snapshot_worker.py — Daily snapshot worker for all domains.

Replaces: daily_portfolio_snapshot.py, savings_snapshot.py, pension_snapshot.py

Domains:
  --domain portfolio  Reads Inv26-Summary → portfolio_snapshots to Supabase
  --domain savings    Reads Savings Balance → savings_accounts + savings_snapshots
  --domain pensions   Reads Pension Balance → pension_accounts + pension_snapshots
  --domain all        Runs all three in sequence (default for scheduled runs)
"""

import os
import sys
import re
import calendar
import argparse
from collections import defaultdict
from datetime import date
from dotenv import load_dotenv
import gspread
from google.oauth2.service_account import Credentials

from lib.supabase_sink import (
    write_portfolio_snapshot,
    write_savings_accounts,
    write_savings_snapshot,
    write_pension_accounts,
    write_pension_snapshot,
)

load_dotenv()

SHEET_ID = os.getenv('PORTFOLIO_SHEET_ID')
SA_FILE  = os.getenv('GOOGLE_APPLICATION_CREDENTIALS', 'config/service_account.json')
SCOPES   = ['https://www.googleapis.com/auth/spreadsheets']

COL_VALUE_IDX   = 6  # 0-based → col G (Current Value)
COL_STARTED_IDX = 8  # 0-based → col I (Tracking Started Value)


def find_investment_rows(ws):
    """
    Dynamically locate key summary rows in the Investments tab.
    Returns a dict with 1-based row numbers. Robust to row inserts/deletes
    in the stocks section caused by log_trades.py add/remove operations.
    """
    all_rows = ws.get_all_values()
    rows = {}
    for i, row in enumerate(all_rows, start=1):
        a = (row[0] if row else '').strip().upper()
        if a == 'VADYM TOTAL' and 'vadym_total' not in rows:
            rows['vadym_total'] = i + 2        # label → header row → value row
        elif 'CASH FOR INVESTMENTS' in a and 'cash' not in rows:
            rows['cash'] = i + 1
        elif 'SELF-MANAGED STOCKS' in a and 'stocks_total' not in rows:
            rows['stocks_total'] = i + 1
        elif 'MANAGED FUNDS' in a and 'managed_total' not in rows:
            rows['managed_total'] = i + 1
        elif 'BENCHMARK' in a and 'sp500' not in rows:
            rows['sp500']      = i + 1
            rows['ftse100']    = i + 2
            rows['nasdaq100']  = i + 3
            rows['msci_world'] = i + 4
            rows['gold']       = i + 5
        elif a == 'LISA TOTAL' and 'lisa_total' not in rows:
            rows['lisa_total'] = i + 1
        elif a == 'JOINT TOTAL' and 'joint_total' not in rows:
            rows['joint_total'] = i + 1
    return rows

MONTH_NAMES = {
    'january': 1, 'february': 2, 'march': 3, 'april': 4,
    'may': 5, 'june': 6, 'july': 7, 'august': 8,
    'september': 9, 'october': 10, 'november': 11, 'december': 12,
    'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4,
    'jun': 6, 'jul': 7, 'aug': 8,
    'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12,
}


# ── Shared helpers ─────────────────────────────────────────────────────────────

def parse_float(val):
    if val is None or str(val).strip() == '':
        return None
    try:
        return float(str(val).replace('£', '').replace(',', '').replace('%', '').strip())
    except (ValueError, TypeError):
        return None


def parse_float_default(val, default=0.0):
    result = parse_float(val)
    return result if result is not None else default


def read_cell(ws, row, col_idx):
    row_vals = ws.row_values(row)
    return parse_float_default(row_vals[col_idx]) if len(row_vals) > col_idx else 0.0


def parse_month_header(header: str) -> str | None:
    """Parse sheet column headers → ISO date.
    - 'Apr 2026' / 'April 2026 Balance' → last day of month (no specific day given)
    - 'May 6, 2026' / '6 May 2026'       → exact date (2026-05-06)
    """
    m = re.match(
        r'(?:(?P<day_pre>\d{1,2})\s+)?(?P<month>\w+)(?:\s+(?P<day_post>\d{1,2}),?)?\s+(?P<year>\d{4})(?:\s+.*)?$',
        header.strip(), re.IGNORECASE,
    )
    if not m:
        return None
    month_num = MONTH_NAMES.get(m.group('month').lower())
    if not month_num:
        return None
    year = int(m.group('year'))
    day_str = m.group('day_pre') or m.group('day_post')
    day = int(day_str) if day_str else calendar.monthrange(year, month_num)[1]
    return date(year, month_num, day).isoformat()


def find_col(headers_lower, *candidates):
    """Return first column index whose lowercased name starts with any candidate."""
    for i, h in enumerate(headers_lower):
        for c in candidates:
            if h.startswith(c.lower()):
                return i
    return None


def open_sheet():
    creds = Credentials.from_service_account_file(SA_FILE, scopes=SCOPES)
    return gspread.authorize(creds).open_by_key(SHEET_ID)


# ── Domain: portfolio ──────────────────────────────────────────────────────────

def read_net_deposits(sh):
    ws   = sh.worksheet('InvTransactions')
    rows = ws.get_all_values()
    return sum(
        parse_float_default(row[6])
        for row in rows[1:]
        if len(row) > 6 and row[3].strip().upper() == 'DEPOSIT'
    )


def run_portfolio():
    today = date.today().isoformat()
    print(f"\n=== snapshot_worker --domain portfolio — {today} ===")

    print("\nConnecting to Google Sheets...")
    sh = open_sheet()
    ws = sh.worksheet('Investments')
    print(f"  Opened: {sh.title} / Investments")

    r = find_investment_rows(ws)
    print(f"  Row map: vadym={r.get('vadym_total')} cash={r.get('cash')} "
          f"managed={r.get('managed_total')} lisa={r.get('lisa_total')} joint={r.get('joint_total')}")

    totals = {
        'vadym_total':          read_cell(ws, r['vadym_total'],   COL_VALUE_IDX),
        'lisa_total':           read_cell(ws, r['lisa_total'],    COL_VALUE_IDX) if r.get('lisa_total')  else None,
        'joint_total':          read_cell(ws, r['joint_total'],   COL_VALUE_IDX) if r.get('joint_total') else None,
        'self_managed':         read_cell(ws, r['stocks_total'],  COL_VALUE_IDX),
        # Sum of every held stock's "Tracking Started Value" (sheet col I, R11).
        # Used by the web app to compute organic stocks performance:
        # performance = self_managed / stocks_started_value - 1.
        # Insulated from BUY/SELL inflows because each new position adds equal
        # amounts to numerator and denominator.
        'stocks_started_value': read_cell(ws, r['stocks_total'],  COL_STARTED_IDX),
        'managed':              read_cell(ws, r['managed_total'], COL_VALUE_IDX),
        'cash':                 read_cell(ws, r['cash'],          COL_VALUE_IDX),
        'spx':                  read_cell(ws, r['sp500'],         COL_VALUE_IDX),
        'ftse':                 read_cell(ws, r['ftse100'],       COL_VALUE_IDX),
        'ndx':                  read_cell(ws, r['nasdaq100'],     COL_VALUE_IDX),
        'msci':                 read_cell(ws, r['msci_world'],    COL_VALUE_IDX),
        'gold':                 read_cell(ws, r['gold'],          COL_VALUE_IDX),
    }

    print("\nReading net deposits from InvTransactions...")
    totals['net_deposits'] = read_net_deposits(sh)

    print(f"  Vadym total:  £{totals['vadym_total']:,.2f}")
    if totals['lisa_total'] is not None:
        print(f"  Lisa total:   £{totals['lisa_total']:,.2f}")
    if totals['joint_total'] is not None:
        print(f"  Joint total:  £{totals['joint_total']:,.2f}")
    print(f"  Self-managed: £{totals['self_managed']:,.2f}")
    print(f"  Stocks start: £{totals['stocks_started_value']:,.2f}")
    print(f"  Managed:      £{totals['managed']:,.2f}")
    print(f"  Cash:         £{totals['cash']:,.2f}")
    print(f"  Net deposits: £{totals['net_deposits']:,.2f}")
    print(f"  Benchmarks:   S&P {totals['spx']:.2f} | FTSE {totals['ftse']:.2f} | "
          f"NDX {totals['ndx']:.2f} | MSCI {totals['msci']:.2f} | Gold {totals['gold']:.2f}")

    print("\nWriting to Supabase portfolio_snapshots...")
    ok = write_portfolio_snapshot(today, totals)
    if ok:
        print(f"  Done — {today} upserted.")
    else:
        print("  Supabase write failed.")
        sys.exit(1)


# ── Domain: savings ────────────────────────────────────────────────────────────

def run_savings():
    print(f"\n=== snapshot_worker --domain savings — {date.today()} ===")

    print("\nConnecting to Google Sheets...")
    sh  = open_sheet()
    ws  = sh.worksheet('Savings Balance')
    print(f"  Opened: {sh.title} / Savings Balance")

    all_rows = ws.get_all_values()
    if not all_rows:
        print("  Sheet is empty — nothing to do.")
        return

    headers       = [h.strip() for h in all_rows[0]]
    headers_lower = [h.lower() for h in headers]

    bank_col    = find_col(headers_lower, 'bank')
    account_col = find_col(headers_lower, 'account')
    type_col    = find_col(headers_lower, 'type')
    owner_col   = find_col(headers_lower, 'owner')

    if bank_col is None or account_col is None:
        print(f"  ERROR: missing 'Bank' or 'Account' column. Headers: {headers}")
        sys.exit(1)

    if owner_col is None:
        print("  No 'Owner' column — will infer from Type column.")

    month_cols = [(i, parse_month_header(h)) for i, h in enumerate(headers)]
    month_cols = [(i, d) for i, d in month_cols if d]

    if not month_cols:
        print("  No month columns found.")
        sys.exit(1)
    print(f"  {len(month_cols)} month column(s): {[d for _, d in month_cols]}")

    account_rows = []
    for row in [r for r in all_rows[1:] if any(c.strip() for c in r)]:
        def cell(idx):
            return row[idx].strip() if idx is not None and idx < len(row) else ''

        bank      = cell(bank_col)
        account   = cell(account_col)
        raw_type  = cell(type_col) if type_col is not None else ''
        type_lower = raw_type.lower().strip()

        if not bank or not account:
            continue

        if owner_col is not None:
            acct_type = type_lower or None
            owner     = cell(owner_col).strip().lower() or 'vadym'
        elif type_lower == 'vadym personal':
            acct_type = None
            owner     = 'vadym'
        elif type_lower == 'lisa personal':
            acct_type = None
            owner     = 'lisa'
        elif type_lower == 'joint':
            acct_type = None
            owner     = 'joint'
        else:
            acct_type = type_lower or None
            owner     = 'vadym'

        for col_i, date_iso in month_cols:
            raw     = row[col_i].strip() if col_i < len(row) else ''
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
    if not write_savings_accounts(account_rows):
        print("  ERROR: savings_accounts write failed.")
        sys.exit(1)
    print("  savings_accounts — done.")

    date_totals: dict[str, dict[str, float]] = defaultdict(
        lambda: {'total': 0.0, 'vadym': 0.0, 'lisa': 0.0, 'joint': 0.0}
    )
    for row in account_rows:
        d     = row['date']
        v     = float(row['balance_gbp'])
        owner = row['owner'].strip().lower()
        date_totals[d]['total'] += v
        if owner == 'joint':
            date_totals[d]['joint'] += v
        elif owner == 'lisa':
            date_totals[d]['lisa'] += v
        else:
            date_totals[d]['vadym'] += v

    errors = 0
    for d, totals in sorted(date_totals.items()):
        ok = write_savings_snapshot(d, totals['total'], totals['vadym'], totals['lisa'], totals['joint'])
        if ok:
            print(f"  savings_snapshots {d} — £{totals['total']:,.2f} "
                  f"(vadym £{totals['vadym']:,.2f} / lisa £{totals['lisa']:,.2f} / joint £{totals['joint']:,.2f})")
        else:
            print(f"  ERROR: savings_snapshots write failed for {d}")
            errors += 1

    if errors:
        sys.exit(1)
    print("\nAll done.")


# ── Domain: pensions ───────────────────────────────────────────────────────────

def run_pensions():
    print(f"\n=== snapshot_worker --domain pensions — {date.today()} ===")

    print("\nConnecting to Google Sheets...")
    sh = open_sheet()
    ws = sh.worksheet('Pensions')
    print(f"  Opened: {sh.title} / Pensions")

    all_rows = ws.get_all_values()
    if not all_rows:
        print("  Sheet is empty — nothing to do.")
        return

    headers       = [h.strip() for h in all_rows[0]]
    headers_lower = [h.lower() for h in headers]

    owner_col    = find_col(headers_lower, 'owner')
    provider_col = find_col(headers_lower, 'provider')
    account_col  = find_col(headers_lower, 'employer', 'account')

    if provider_col is None or account_col is None:
        print(f"  ERROR: missing 'Provider' or 'Employer'/'Account' column. Headers: {headers}")
        sys.exit(1)

    if owner_col is None:
        print("  No 'Owner' column — all rows default to 'vadym'.")

    month_cols = [(i, parse_month_header(h)) for i, h in enumerate(headers)]
    month_cols = [(i, d) for i, d in month_cols if d]

    if not month_cols:
        print("  No month columns found.")
        sys.exit(1)
    print(f"  {len(month_cols)} month column(s): {[d for _, d in month_cols]}")

    account_rows = []
    for row in [r for r in all_rows[1:] if any(c.strip() for c in r)]:
        def cell(idx):
            return row[idx].strip() if idx is not None and idx < len(row) else ''

        owner    = cell(owner_col).lower() if owner_col is not None else 'vadym'
        provider = cell(provider_col)
        account  = cell(account_col)

        # skip subtotal/total rows (owner or provider signals a summary row)
        if not provider or not account:
            continue
        if provider.lower() in ('total', 'subtotal') or 'total' in owner:
            continue

        if owner not in ('vadym', 'lisa'):
            owner = 'vadym'

        for col_i, date_iso in month_cols:
            raw     = row[col_i].strip() if col_i < len(row) else ''
            balance = parse_float(raw)
            if balance is None:
                continue
            account_rows.append({
                'date':         date_iso,
                'provider':     provider,
                'account_name': account,
                'owner':        owner,
                'balance_gbp':  balance,
            })

    if not account_rows:
        print("  No pension balance data found.")
        return

    print(f"\n  {len(account_rows)} provider-date rows to upsert...")
    if not write_pension_accounts(account_rows):
        print("  ERROR: pension_accounts write failed.")
        sys.exit(1)
    print("  pension_accounts — done.")

    date_totals: dict[str, dict[str, float]] = defaultdict(
        lambda: {'total': 0.0, 'vadym': 0.0, 'lisa': 0.0}
    )
    for row in account_rows:
        d     = row['date']
        v     = float(row['balance_gbp'])
        owner = row['owner']
        date_totals[d]['total'] += v
        date_totals[d][owner]   += v

    errors = 0
    for d, totals in sorted(date_totals.items()):
        ok = write_pension_snapshot(d, totals['total'], totals['vadym'], totals['lisa'])
        if ok:
            print(f"  pension_snapshots {d} — £{totals['total']:,.2f} "
                  f"(vadym £{totals['vadym']:,.2f} / lisa £{totals['lisa']:,.2f})")
        else:
            print(f"  ERROR: pension_snapshots write failed for {d}")
            errors += 1

    if errors:
        sys.exit(1)
    print("\nAll done.")


# ── Entry point ────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='Snapshot worker — writes domain data to Supabase')
    parser.add_argument(
        '--domain',
        choices=['portfolio', 'savings', 'pensions', 'all'],
        required=True,
        help='portfolio|savings|pensions|all',
    )
    args = parser.parse_args()

    runners = {
        'portfolio': [run_portfolio],
        'savings':   [run_savings],
        'pensions':  [run_pensions],
        'all':       [run_portfolio, run_savings, run_pensions],
    }
    for fn in runners[args.domain]:
        fn()


if __name__ == '__main__':
    main()
