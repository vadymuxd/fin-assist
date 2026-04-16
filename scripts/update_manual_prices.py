#!/usr/bin/env python3
"""
update_manual_prices.py

Fetches prices for tickers not available via GOOGLEFINANCE
and writes them directly to the Inv26 - Summary tab in Google Sheets.

Currently handles:
  - SGLN (iShares Physical Gold ETC) via Yahoo Finance (SGLN.L)

Add more tickers to MANUAL_TICKERS as needed.

Run from repo root:
    python3 scripts/update_manual_prices.py

Can be added to GitHub Actions alongside holdings_monitor.py.
"""

import os
from datetime import datetime, timezone
import yfinance as yf
from dotenv import load_dotenv
import gspread
from google.oauth2.service_account import Credentials

load_dotenv()

SHEET_ID = os.getenv('PORTFOLIO_SHEET_ID')
SA_FILE = os.getenv('GOOGLE_APPLICATION_CREDENTIALS', 'config/service_account.json')
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']

# Yahoo Finance ticker → (Inv26 ticker in col A, price_in_gbx)
# gbx=True  → Yahoo returns pence, divide by 100 to get £
# gbx=False → Yahoo returns £ directly
MANUAL_TICKERS = {
    'SGLN.L': ('SGLN', True),   # iShares Physical Gold ETC — LSE, priced in GBX
}


def fetch_price(yahoo_ticker, gbx=False):
    """Fetch latest closing price from Yahoo Finance. Returns GBP."""
    ticker = yf.Ticker(yahoo_ticker)
    hist = ticker.history(period='5d')
    if hist.empty:
        raise ValueError(f"No price data returned for {yahoo_ticker}")
    raw = float(hist['Close'].iloc[-1])
    return round(raw / 100 if gbx else raw, 4)


def update_inv26(sh, prices):
    """
    Locate each ticker in Inv26 column A, write price to column F,
    and timestamp to column M (Last Updated by Script).
    Uses dynamic row lookup so it's safe if row order ever changes.
    """
    ws = sh.worksheet('Inv26 - Summary')
    col_a = ws.col_values(1)  # All values in column A
    now = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')

    for sheet_ticker, price_gbp in prices.items():
        try:
            row = col_a.index(sheet_ticker) + 1  # 1-based
        except ValueError:
            print(f"  Warning: '{sheet_ticker}' not found in Inv26 — skipping")
            continue
        ws.update_cell(row, 6, price_gbp)   # F: Current Price £
        ws.update_cell(row, 13, now)         # M: Last Updated by Script
        print(f"  {sheet_ticker}: £{price_gbp:.4f} written to row {row}")


def main():
    print("Connecting to Google Sheets...")
    creds = Credentials.from_service_account_file(SA_FILE, scopes=SCOPES)
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(SHEET_ID)
    print(f"  Opened: {sh.title}")

    print("\nFetching prices from Yahoo Finance...")
    prices = {}
    for yahoo_ticker, (sheet_ticker, gbx) in MANUAL_TICKERS.items():
        try:
            price = fetch_price(yahoo_ticker, gbx=gbx)
            prices[sheet_ticker] = price
            print(f"  {yahoo_ticker}: raw→ £{price:.4f} ({'GBX÷100' if gbx else 'GBP direct'})")
        except Exception as e:
            print(f"  Error fetching {yahoo_ticker}: {e}")

    if not prices:
        print("  Nothing to update.")
        return

    print("\nWriting to Inv26 - Summary...")
    update_inv26(sh, prices)

    print("\nDone.")


if __name__ == '__main__':
    main()
