#!/usr/bin/env python3
"""
update_manual_prices.py

Fetches latest prices for all portfolio tickers via yfinance and writes
them directly to the Investments tab in Google Sheets.

Handles currency conversion to GBP:
  - LSE (.L)      — Yahoo returns GBX (pence) → divide by 100
  - US            — Yahoo returns USD → convert via GBPUSD=X
  - EU (.DE, .PA) — Yahoo returns EUR → convert via GBPEUR=X
  - CA (.TO)      — Yahoo returns CAD → convert via GBPCAD=X

Also writes "Last updated: YYYY-MM-DD HH:MM UTC" to cell A2.

Runs 3× daily via daily_monitor.yml (09:30 / 13:00 / 16:30 BST).
"""

import os
from datetime import datetime, timezone
import yfinance as yf
from dotenv import load_dotenv
import gspread
from google.oauth2.service_account import Credentials

load_dotenv()

SHEET_ID = os.getenv('PORTFOLIO_SHEET_ID')
SA_FILE  = os.getenv('GOOGLE_APPLICATION_CREDENTIALS', 'config/service_account.json')
SCOPES   = ['https://www.googleapis.com/auth/spreadsheets']

# sheet_ticker → (yfinance_symbol, currency)
# currency: 'GBX' (pence→GBP ÷100), 'USD', 'EUR', 'CAD'
TICKERS = {
    'NVDA':   ('NVDA',      'USD'),
    'RTX':    ('RTX',       'USD'),
    'GOOG':   ('GOOG',      'USD'),
    'BRK.B':  ('BRK-B',     'USD'),
    'TECK.B': ('TECK-B.TO', 'CAD'),
    'RIO':    ('RIO.L',     'GBX'),
    'SGLN':   ('SGLN.L',    'GBX'),
    'INRG':   ('INRG.L',    'GBX'),
    'IITU':   ('IITU.L',    'GBX'),
    'VGER':   ('VGER.L',    'GBP'),  # Yahoo returns GBP directly, not GBX
    'BA.':    ('BA.L',      'GBX'),
    'VUSA':   ('VUSA.L',    'GBP'),  # Yahoo returns GBP directly, not GBX
    'ISP6':   ('ISP6.L',    'GBX'),
    'LGEN':   ('LGEN.L',    'GBX'),
    'EUE':    ('EUE.L',     'GBX'),
    'RHM':    ('RHM.DE',    'EUR'),
    'HO':     ('HO.PA',     'EUR'),
}

# GBPXXX=X pairs: 1 GBP = X foreign → gbp_per_unit = 1 / rate
FX_PAIRS = {
    'USD': 'GBPUSD=X',
    'EUR': 'GBPEUR=X',
    'CAD': 'GBPCAD=X',
}


def fetch_fx_rates():
    """Fetch GBP cost of 1 unit of each foreign currency."""
    rates = {}
    for currency, pair in FX_PAIRS.items():
        try:
            hist = yf.Ticker(pair).history(period='2d')
            if not hist.empty:
                rates[currency] = round(1.0 / float(hist['Close'].iloc[-1]), 6)
                print(f"  FX {currency}: £{rates[currency]:.4f} per 1 {currency}")
            else:
                print(f"  Warning: no FX data for {pair}")
        except Exception as e:
            print(f"  FX fetch error for {pair}: {e}")
    return rates


def fetch_prices(fx_rates):
    """Fetch latest close price for every ticker and convert to GBP."""
    prices = {}
    for sheet_ticker, (yf_symbol, currency) in TICKERS.items():
        try:
            hist = yf.Ticker(yf_symbol).history(period='5d')
            if hist.empty:
                print(f"  {sheet_ticker}: no data — skipping")
                continue
            raw = float(hist['Close'].iloc[-1])

            if currency == 'GBX':
                price_gbp = round(raw / 100, 4)
            elif currency in fx_rates:
                price_gbp = round(raw * fx_rates[currency], 4)
            else:
                price_gbp = round(raw, 4)

            prices[sheet_ticker] = price_gbp
            print(f"  {sheet_ticker} ({yf_symbol}): {raw:.4f} {currency} → £{price_gbp:.4f}")
        except Exception as e:
            print(f"  {sheet_ticker}: error — {e}")
    return prices


def update_sheet(sh, prices, timestamp):
    """
    Write prices to column F in the Investments tab.
    Write sheet-level timestamp to cell A2.
    """
    ws    = sh.worksheet('Investments')
    col_a = ws.col_values(1)

    ws.update_cell(2, 1, f'Last updated: {timestamp}')

    updated = 0
    for sheet_ticker, price_gbp in prices.items():
        try:
            row = col_a.index(sheet_ticker) + 1
        except ValueError:
            print(f"  Warning: '{sheet_ticker}' not found in Investments col A — skipping")
            continue
        ws.update_cell(row, 6, price_gbp)
        updated += 1

    print(f"  Investments: {updated}/{len(prices)} rows updated")


def main():
    print("Connecting to Google Sheets...")
    creds = Credentials.from_service_account_file(SA_FILE, scopes=SCOPES)
    gc    = gspread.authorize(creds)
    sh    = gc.open_by_key(SHEET_ID)
    print(f"  Opened: {sh.title}")

    print("\nFetching FX rates...")
    fx_rates = fetch_fx_rates()

    print("\nFetching ticker prices...")
    prices = fetch_prices(fx_rates)

    if not prices:
        print("  Nothing to update.")
        return

    timestamp = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
    print(f"\nWriting to Investments tab (timestamp: {timestamp})...")
    update_sheet(sh, prices, timestamp)

    print("\nDone.")


if __name__ == '__main__':
    main()
