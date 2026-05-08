#!/usr/bin/env python3
"""
update_manual_prices.py

Fetches the SGLN (iShares Physical Gold ETC) price via Alpha Vantage
and writes it to the Investments tab in Google Sheets.

SGLN is not available via GOOGLEFINANCE() — all other tickers in the
Investments tab use GOOGLEFINANCE() formulas written directly in the sheet.

Runs 3× daily via daily_monitor.yml (09:30 / 13:00 / 16:30 BST).
"""

import os
import requests
from dotenv import load_dotenv
import gspread
from google.oauth2.service_account import Credentials

load_dotenv()

SHEET_ID = os.getenv('PORTFOLIO_SHEET_ID')
SA_FILE  = os.getenv('GOOGLE_APPLICATION_CREDENTIALS', 'config/service_account.json')
AV_KEY   = os.getenv('ALPHAVANTAGE_API_KEY')
SCOPES   = ['https://www.googleapis.com/auth/spreadsheets']


def fetch_sgln_price() -> float:
    """Fetch SGLN latest price from Alpha Vantage. LSE returns GBX (pence) → ÷100 → GBP."""
    resp = requests.get('https://www.alphavantage.co/query', params={
        'function': 'GLOBAL_QUOTE',
        'symbol':   'SGLN.LON',
        'apikey':   AV_KEY,
    }, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    price_str = data.get('Global Quote', {}).get('05. price')
    if not price_str:
        raise ValueError(f"No price in Alpha Vantage response: {data}")

    return round(float(price_str) / 100, 4)  # GBX → GBP


def update_sheet(sh, price_gbp: float) -> None:
    """Write SGLN price to column F in the Investments tab."""
    ws    = sh.worksheet('Investments')
    col_a = ws.col_values(1)

    try:
        row = col_a.index('SGLN') + 1
    except ValueError:
        print("  Warning: 'SGLN' not found in Investments col A — skipping")
        return

    ws.update_cell(row, 6, price_gbp)
    print(f"  SGLN: £{price_gbp:.4f} → row {row}")


def main():
    if not AV_KEY:
        raise RuntimeError("ALPHAVANTAGE_API_KEY env var is not set")

    print("Connecting to Google Sheets...")
    creds = Credentials.from_service_account_file(SA_FILE, scopes=SCOPES)
    gc    = gspread.authorize(creds)
    sh    = gc.open_by_key(SHEET_ID)
    print(f"  Opened: {sh.title}")

    print("\nFetching SGLN price (Alpha Vantage)...")
    price = fetch_sgln_price()
    print(f"  SGLN.LON: raw {price * 100:.2f}p → £{price:.4f}")

    print("\nWriting to Investments tab...")
    update_sheet(sh, price)

    print("\nDone.")


if __name__ == '__main__':
    main()
