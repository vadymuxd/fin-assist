#!/usr/bin/env python3
"""
update_manual_prices.py

Fetches prices for tickers that aren't available via GOOGLEFINANCE() and writes
them to the Investments tab in Google Sheets.

Currently managed:
  SGLN  — iShares Physical Gold ETC  (LSE, GBX → ÷100 → GBP)
  UKRN  — HANetf Ukraine Reconstruction UCITS ETF  (LSE, GBX → ÷100 → GBP)

Writes a "Last updated" timestamp to cell B2 after all prices are updated.

Runs 3× daily via daily_monitor.yml (09:30 / 13:00 / 16:30 BST).
"""

import os
from datetime import datetime, timezone
import requests
from dotenv import load_dotenv
import gspread
from google.oauth2.service_account import Credentials

load_dotenv()

SHEET_ID = os.getenv('PORTFOLIO_SHEET_ID')
SA_FILE  = os.getenv('GOOGLE_APPLICATION_CREDENTIALS', 'config/service_account.json')
AV_KEY   = os.getenv('ALPHAVANTAGE_API_KEY')
SCOPES   = ['https://www.googleapis.com/auth/spreadsheets']

# Tickers managed by this script (not covered by GOOGLEFINANCE).
# Each entry: (av_symbol, gbx_to_gbp)
#   av_symbol   — Alpha Vantage symbol (e.g. SGLN.LON)
#   gbx_to_gbp  — True if AV returns GBX (pence) and we must divide by 100
MANUAL_TICKERS = {
    'SGLN': ('SGLN.LON', True),
    'UKRN': ('UKRN.LON', True),
}


def fetch_price(av_symbol: str, gbx_to_gbp: bool) -> float:
    """Fetch latest price from Alpha Vantage. Optionally converts GBX → GBP."""
    resp = requests.get('https://www.alphavantage.co/query', params={
        'function': 'GLOBAL_QUOTE',
        'symbol':   av_symbol,
        'apikey':   AV_KEY,
    }, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    price_str = data.get('Global Quote', {}).get('05. price')
    if not price_str:
        raise ValueError(f"No price in Alpha Vantage response for {av_symbol}: {data}")

    price = float(price_str)
    if gbx_to_gbp:
        price /= 100
    return round(price, 4)


def update_prices(ws) -> None:
    """Write each manual ticker's price to col F of its row in the Investments tab."""
    col_a = ws.col_values(1)

    for ticker, (av_symbol, gbx_to_gbp) in MANUAL_TICKERS.items():
        print(f"\nFetching {ticker} price ({av_symbol})...")
        try:
            price = fetch_price(av_symbol, gbx_to_gbp)
            raw_display = f"{price * 100:.2f}p" if gbx_to_gbp else f"£{price:.4f}"
            print(f"  {av_symbol}: raw {raw_display} → £{price:.4f}")
        except Exception as e:
            print(f"  WARNING: could not fetch {ticker}: {e} — skipping")
            continue

        try:
            row = col_a.index(ticker) + 1
        except ValueError:
            print(f"  WARNING: '{ticker}' not found in Investments col A — skipping")
            continue

        ws.update_cell(row, 6, price)
        print(f"  {ticker}: £{price:.4f} → row {row}, col F")


def update_timestamp(ws) -> None:
    """Write 'Last updated: <datetime>' to B2."""
    now = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
    ws.update_cell(2, 2, f'Last updated: {now}')
    print(f"\n  Timestamp → B2: {now}")


def main():
    if not AV_KEY:
        raise RuntimeError("ALPHAVANTAGE_API_KEY env var is not set")

    print("Connecting to Google Sheets...")
    creds = Credentials.from_service_account_file(SA_FILE, scopes=SCOPES)
    gc    = gspread.authorize(creds)
    sh    = gc.open_by_key(SHEET_ID)
    print(f"  Opened: {sh.title}")

    ws = sh.worksheet('Investments')

    update_prices(ws)
    update_timestamp(ws)

    print("\nDone.")


if __name__ == '__main__':
    main()
