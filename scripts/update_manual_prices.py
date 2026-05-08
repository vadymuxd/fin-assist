#!/usr/bin/env python3
"""
update_manual_prices.py

Fetches latest prices for all portfolio tickers via Twelve Data API and writes
them directly to the Investments tab in Google Sheets.

Handles currency conversion to GBP:
  - LSE (.L)      — Twelve Data returns GBX (pence) → divide by 100
  - US            — Twelve Data returns USD → convert via GBP/USD
  - EU (.DE, .PA) — Twelve Data returns EUR → convert via GBP/EUR
  - CA (.TO)      — Twelve Data returns CAD → convert via GBP/CAD

Also writes "Last updated: YYYY-MM-DD HH:MM UTC" to cell A2.

Runs 3× daily via daily_monitor.yml (09:30 / 13:00 / 16:30 BST)
and once via price_refresh.yml (21:30 BST after US/CA close).
"""

import os
import requests
from datetime import datetime, timezone
from dotenv import load_dotenv
import gspread
from google.oauth2.service_account import Credentials

load_dotenv()

SHEET_ID        = os.getenv('PORTFOLIO_SHEET_ID')
SA_FILE         = os.getenv('GOOGLE_APPLICATION_CREDENTIALS', 'config/service_account.json')
TWELVE_DATA_KEY = os.getenv('TWELVE_DATA_API_KEY')
SCOPES          = ['https://www.googleapis.com/auth/spreadsheets']
BASE_URL        = 'https://api.twelvedata.com/price'

# sheet_ticker → (twelve_data_symbol, currency)
# currency: 'GBX' (pence→GBP ÷100), 'USD', 'EUR', 'CAD', 'GBP'
TICKERS = {
    'NVDA':   ('NVDA',        'USD'),
    'RTX':    ('RTX',         'USD'),
    'GOOG':   ('GOOG',        'USD'),
    'BRK.B':  ('BRK/B',       'USD'),
    'TECK.B': ('TECK/B:TSX',  'CAD'),
    'RIO':    ('RIO:LSE',     'GBX'),
    'SGLN':   ('SGLN:LSE',    'GBX'),
    'INRG':   ('INRG:LSE',    'GBX'),
    'IITU':   ('IITU:LSE',    'GBX'),
    'VGER':   ('VGER:LSE',    'GBP'),  # GBP-denominated ETF, not pence
    'RHM':    ('RHM:XETRA',   'EUR'),
}

# GBP/XXX pairs: 1 GBP = X foreign → gbp_per_unit = 1 / rate
FX_PAIRS = {
    'USD': 'GBP/USD',
    'EUR': 'GBP/EUR',
    'CAD': 'GBP/CAD',
}


def _batch_fetch(symbols: list[str]) -> dict:
    """Call Twelve Data /price with comma-separated symbols. Returns {symbol: price_str}."""
    resp = requests.get(BASE_URL, params={
        'symbol': ','.join(symbols),
        'apikey': TWELVE_DATA_KEY,
    }, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    # Single-symbol response: {"price": "123.45"}
    # Multi-symbol response:  {"NVDA": {"price": "123.45"}, ...}
    if 'price' in data:
        return {symbols[0]: data['price']}
    result = {sym: entry.get('price') for sym, entry in data.items() if isinstance(entry, dict)}
    if not any(result.values()):
        print(f"  [debug] raw Twelve Data response: {data}")
    return result


def fetch_fx_rates() -> dict:
    """Fetch GBP cost of 1 unit of each foreign currency."""
    raw = _batch_fetch(list(FX_PAIRS.values()))
    rates = {}
    for currency, pair in FX_PAIRS.items():
        price_str = raw.get(pair)
        if price_str is None:
            print(f"  Warning: no FX data for {pair}")
            continue
        try:
            rates[currency] = round(1.0 / float(price_str), 6)
            print(f"  FX {currency}: £{rates[currency]:.4f} per 1 {currency}")
        except (ValueError, ZeroDivisionError) as e:
            print(f"  FX fetch error for {pair}: {e}")
    return rates


def fetch_prices(fx_rates: dict) -> dict:
    """Fetch latest price for every ticker and convert to GBP."""
    td_symbols = [td_sym for _, (td_sym, _) in TICKERS.items()]
    raw = _batch_fetch(td_symbols)

    prices = {}
    for sheet_ticker, (td_symbol, currency) in TICKERS.items():
        price_str = raw.get(td_symbol)
        if price_str is None:
            print(f"  {sheet_ticker}: no data — skipping")
            continue
        try:
            value = float(price_str)
        except ValueError as e:
            print(f"  {sheet_ticker}: error — {e}")
            continue

        if currency == 'GBX':
            price_gbp = round(value / 100, 4)
        elif currency in fx_rates:
            price_gbp = round(value * fx_rates[currency], 4)
        else:
            price_gbp = round(value, 4)

        prices[sheet_ticker] = price_gbp
        print(f"  {sheet_ticker} ({td_symbol}): {value:.4f} {currency} → £{price_gbp:.4f}")
    return prices


def update_sheet(sh, prices: dict, timestamp: str) -> None:
    """Write prices to column F in the Investments tab and update timestamp in A2."""
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
    if not TWELVE_DATA_KEY:
        raise RuntimeError("TWELVE_DATA_API_KEY env var is not set")

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
