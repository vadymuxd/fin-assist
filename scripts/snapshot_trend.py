#!/usr/bin/env python3
"""
snapshot_trend.py

Appends a monthly snapshot row to the 'Inv26 - Trend' tab.

Reads from 'Inv26 - Summary':
  - Self-managed stocks total (row 11, col G)
  - Managed funds total (row 28, col G)
  - Cash (row 9, col G)
  - Grand total (row 7, col G)
  - 5 benchmark values (rows 31-35, col G)
Reads from 'InvTransactions':
  - Net Deposits = SUMIF(Action == 'DEPOSIT')

Date label is the current month-year (e.g. "Apr 2026").
Formula columns (E, G, M–Q) are written as spreadsheet formulas
so % vs start computations happen automatically.

By default runs only on the last weekday of the month (mirrors the
GitHub Actions cron `0 16 28-31 * 1-5`). Pass --force to override.

Run from repo root:
    python3 scripts/snapshot_trend.py           # last-weekday guard active
    python3 scripts/snapshot_trend.py --force   # always append (manual use)
"""

import os
import sys
import calendar
from datetime import datetime, timezone, date
from dotenv import load_dotenv
import gspread
from google.oauth2.service_account import Credentials

load_dotenv()

SHEET_ID = os.getenv('PORTFOLIO_SHEET_ID')
SA_FILE  = os.getenv('GOOGLE_APPLICATION_CREDENTIALS', 'config/service_account.json')
SCOPES   = ['https://www.googleapis.com/auth/spreadsheets']

# Row numbers in Inv26 - Summary (1-based, as in the sheet)
ROW_GRAND_TOTAL   = 7
ROW_CASH          = 9
ROW_STOCKS_TOTAL  = 11
ROW_MANAGED_TOTAL = 28
ROW_SP500         = 31
ROW_FTSE100       = 32
ROW_NASDAQ100     = 33
ROW_MSCI_WORLD    = 34
ROW_GOLD          = 35
COL_VALUE_IDX     = 6   # 0-based index 6 = col G


# ---------------------------------------------------------------------------
# Date helpers
# ---------------------------------------------------------------------------

def is_last_weekday_of_month(today=None):
    """Return True if today is the last Monday–Friday of the current month."""
    if today is None:
        today = date.today()
    if today.weekday() >= 5:          # Saturday or Sunday
        return False
    # Check if any weekday follows in the rest of the month
    next_day = today.replace(day=today.day + 1) if today.day < calendar.monthrange(today.year, today.month)[1] else None
    while next_day and next_day.month == today.month:
        if next_day.weekday() < 5:    # another weekday exists → not the last
            return False
        next_day = next_day.replace(day=next_day.day + 1) if next_day.day < calendar.monthrange(next_day.year, next_day.month)[1] else None
    return True


def month_label(today=None):
    """Return 'Apr 2026' style label for the current month."""
    if today is None:
        today = date.today()
    return today.strftime('%b %Y')


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def parse_float(val):
    if val is None or val == '':
        return 0.0
    cleaned = str(val).replace('£', '').replace(',', '').replace('%', '').strip()
    try:
        return float(cleaned)
    except (ValueError, TypeError):
        return 0.0


def read_cell(ws, row, col_idx):
    """Read a single cell value from a worksheet (row 1-based, col 0-based index)."""
    row_vals = ws.row_values(row)
    return parse_float(row_vals[col_idx]) if len(row_vals) > col_idx else 0.0


# ---------------------------------------------------------------------------
# Sheet readers
# ---------------------------------------------------------------------------

def read_summary_values(sh):
    """Read portfolio totals and benchmark values from Inv26 - Summary."""
    ws = sh.worksheet('Inv26 - Summary')

    stocks_total  = read_cell(ws, ROW_STOCKS_TOTAL,  COL_VALUE_IDX)
    managed_total = read_cell(ws, ROW_MANAGED_TOTAL, COL_VALUE_IDX)
    cash          = read_cell(ws, ROW_CASH,          COL_VALUE_IDX)
    grand_total   = read_cell(ws, ROW_GRAND_TOTAL,   COL_VALUE_IDX)

    sp500      = read_cell(ws, ROW_SP500,      COL_VALUE_IDX)
    ftse100    = read_cell(ws, ROW_FTSE100,    COL_VALUE_IDX)
    nasdaq100  = read_cell(ws, ROW_NASDAQ100,  COL_VALUE_IDX)
    msci_world = read_cell(ws, ROW_MSCI_WORLD, COL_VALUE_IDX)
    gold       = read_cell(ws, ROW_GOLD,       COL_VALUE_IDX)

    print(f"  Self-managed stocks: £{stocks_total:,.2f}")
    print(f"  Managed funds:       £{managed_total:,.2f}")
    print(f"  Cash:                £{cash:,.2f}")
    print(f"  Grand total:         £{grand_total:,.2f}")
    print(f"  Benchmarks: S&P500={sp500:.2f}, FTSE100={ftse100:.2f}, "
          f"NASDAQ100={nasdaq100:.2f}, MSCI={msci_world:.2f}, Gold={gold:.2f}")

    return {
        'stocks_total':  stocks_total,
        'managed_total': managed_total,
        'cash':          cash,
        'grand_total':   grand_total,
        'sp500':         sp500,
        'ftse100':       ftse100,
        'nasdaq100':     nasdaq100,
        'msci_world':    msci_world,
        'gold':          gold,
    }


def read_net_deposits(sh):
    """Sum all DEPOSIT rows from InvTransactions col G."""
    ws   = sh.worksheet('InvTransactions')
    rows = ws.get_all_values()
    total = 0.0
    for row in rows[1:]:     # skip header
        if len(row) < 7:
            continue
        action = row[3].strip().upper() if len(row) > 3 else ''
        if action == 'DEPOSIT':
            total += parse_float(row[6])
    print(f"  Net deposits (cumulative):  £{total:,.2f}")
    return total


def find_next_trend_row(ws):
    """
    Find the next empty row to append to in Inv26 - Trend.
    Row 17 is the April baseline. Data rows start at 18.
    Returns 1-based row number.
    """
    col_a = ws.col_values(1)    # A column (1-based → list index 0-based)
    # Walk down from row 18 (index 17) to find first empty cell in col A
    for i in range(17, len(col_a)):
        if not col_a[i].strip():
            return i + 1        # convert 0-based index → 1-based row
    return len(col_a) + 1       # all occupied — append after last


# ---------------------------------------------------------------------------
# Trend writer
# ---------------------------------------------------------------------------

def append_trend_row(sh, values, net_deposits, label):
    """
    Append one row to Inv26 - Trend.

    Columns written:
      A  = Date label (e.g. "Apr 2026")
      B  = Self-Managed £ (raw value)
      C  = Managed Funds £ (raw value)
      D  = Cash £ (raw value)
      E  = =B{row}+C{row}+D{row}  (formula)
      F  = Net Deposits £ (raw value at snapshot time)
      G  = =IFERROR((E{row}-E$17)/E$17,"")  (formula — % vs start)
      H  = S&P 500 (raw index value)
      I  = FTSE 100
      J  = NASDAQ 100
      K  = MSCI World (IWDA)
      L  = Gold (SGLN)
      M  = =IFERROR((H{row}-H$17)/H$17,"")  S&P 500 % vs start
      N  = =IFERROR((I{row}-I$17)/I$17,"")  FTSE 100 % vs start
      O  = =IFERROR((J{row}-J$17)/J$17,"")  NASDAQ 100 % vs start
      P  = =IFERROR((K{row}-K$17)/K$17,"")  MSCI World % vs start
      Q  = =IFERROR((L{row}-L$17)/L$17,"")  Gold % vs start
      R  = (blank — Nutmeg Alpha % vs start, filled manually from managed fund apps)
      S  = (blank — Moneyfarm % vs start, filled manually)
      T  = Notes (empty — can be filled in manually)
    """
    ws       = sh.worksheet('Inv26 - Trend')
    next_row = find_next_trend_row(ws)
    r        = next_row  # alias for formula strings

    row_data = [
        label,                                              # A
        values['stocks_total'],                             # B
        values['managed_total'],                            # C
        values['cash'],                                     # D
        f'=B{r}+C{r}+D{r}',                               # E
        net_deposits,                                       # F
        f'=IFERROR((E{r}-E$17)/E$17,"")',                  # G
        values['sp500'],                                    # H
        values['ftse100'],                                  # I
        values['nasdaq100'],                                # J
        values['msci_world'],                               # K
        values['gold'],                                     # L
        f'=IFERROR((H{r}-H$17)/H$17,"")',                  # M  S&P 500 %
        f'=IFERROR((I{r}-I$17)/I$17,"")',                  # N  FTSE 100 %
        f'=IFERROR((J{r}-J$17)/J$17,"")',                  # O  NASDAQ 100 %
        f'=IFERROR((K{r}-K$17)/K$17,"")',                  # P  MSCI World %
        f'=IFERROR((L{r}-L$17)/L$17,"")',                  # Q  Gold %
        '',                                                 # R  Nutmeg % (manual)
        '',                                                 # S  Moneyfarm % (manual)
        '',                                                 # T  Notes
    ]

    ws.update(
        f'A{next_row}:T{next_row}',
        [row_data],
        value_input_option='USER_ENTERED',   # interprets formula strings
    )
    print(f"\n  Appended row {next_row}: {label} | Total £{values['grand_total']:,.2f}")
    print(f"  Note: cols R (Nutmeg %) and S (Moneyfarm %) left blank — fill manually from fund apps")
    return next_row


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    force = '--force' in sys.argv
    today = date.today()

    if not force:
        if not is_last_weekday_of_month(today):
            print(f"Today ({today}) is not the last weekday of the month — skipping.")
            print("Use --force to override.")
            sys.exit(0)
        print(f"Today is the last weekday of {today.strftime('%B %Y')} — proceeding.")

    label = month_label(today)
    print(f"\nSnapshot label: {label}")

    print("\nConnecting to Google Sheets...")
    creds = Credentials.from_service_account_file(SA_FILE, scopes=SCOPES)
    gc    = gspread.authorize(creds)
    sh    = gc.open_by_key(SHEET_ID)
    print(f"  Opened: {sh.title}")

    print("\nReading Inv26 - Summary...")
    values = read_summary_values(sh)

    print("\nReading InvTransactions for net deposits...")
    net_deposits = read_net_deposits(sh)

    print("\nAppending to Inv26 - Trend...")
    append_trend_row(sh, values, net_deposits, label)

    print("\nDone.")


if __name__ == '__main__':
    main()
