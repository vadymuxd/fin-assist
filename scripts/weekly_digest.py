#!/usr/bin/env python3
"""
weekly_digest.py

Sunday 09:00 BST Telegram digest. Summarises:
  1. Portfolio totals (Grand Total, stocks P&L, benchmarks)
  2. Top FAS signals from the week (from data/analysis_results.json)
  3. Prospect highlights from the week (from data/prospect_results.json)
  4. Fundamental snapshot: full refresh of analyst ratings (weekly cadence)

Also triggers a full yfinance fundamental refresh for all held positions
(P/E, revenue/EPS trend, analyst price targets) — weekly-only data.

Run from repo root:
    python3 scripts/weekly_digest.py
"""

import os
import json
import requests
import yfinance as yf
from datetime import datetime, timezone
from dotenv import load_dotenv
import gspread
from google.oauth2.service_account import Credentials

load_dotenv()

SHEET_ID      = os.getenv('PORTFOLIO_SHEET_ID')
SA_FILE       = os.getenv('GOOGLE_APPLICATION_CREDENTIALS', 'config/service_account.json')
SCOPES        = ['https://www.googleapis.com/auth/spreadsheets']
RESULTS_PATH  = 'data/analysis_results.json'
PROSPECT_PATH = 'data/prospect_results.json'

TELEGRAM_TOKEN   = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

# 1-based row numbers in Inv26 - Summary
ROW_GRAND_TOTAL   = 7
ROW_CASH          = 9
ROW_STOCKS_TOTAL  = 11
ROW_MANAGED_TOTAL = 28
ROW_SP500         = 31
ROW_FTSE100       = 32
ROW_NASDAQ100     = 33
ROW_MSCI_WORLD    = 34
ROW_GOLD          = 35
COL_VALUE_IDX     = 6   # 0-based = col G


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


def pct_str(val, suffix='%'):
    sign = '+' if val >= 0 else ''
    return f'{sign}{val:.1f}{suffix}'


def send_telegram(text):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("  WARNING: Telegram credentials not set — message not sent")
        print(f"  Preview:\n{text[:400]}")
        return False
    try:
        resp = requests.post(
            f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage',
            json={'chat_id': TELEGRAM_CHAT_ID, 'text': text, 'parse_mode': 'HTML'},
            timeout=10,
        )
        resp.raise_for_status()
        return True
    except Exception as e:
        print(f"  Telegram error: {e}")
        return False


# ---------------------------------------------------------------------------
# Sheet reader
# ---------------------------------------------------------------------------

def read_portfolio_summary(sh):
    ws = sh.worksheet('Inv26 - Summary')

    def _val(row):
        r = ws.row_values(row)
        return parse_float(r[COL_VALUE_IDX]) if len(r) > COL_VALUE_IDX else 0.0

    def _pnl_row(row):
        """Return (pnl_gbp, pnl_pct) from a row — cols L and M (0-based 11, 12)."""
        r = ws.row_values(row)
        pnl_gbp = parse_float(r[11]) if len(r) > 11 else 0.0
        pnl_pct = parse_float(r[12]) if len(r) > 12 else 0.0
        return pnl_gbp, pnl_pct

    grand_total   = _val(ROW_GRAND_TOTAL)
    cash          = _val(ROW_CASH)
    stocks_total  = _val(ROW_STOCKS_TOTAL)
    managed_total = _val(ROW_MANAGED_TOTAL)
    stocks_pnl_gbp, stocks_pnl_pct = _pnl_row(ROW_STOCKS_TOTAL)

    sp500      = _val(ROW_SP500)
    ftse100    = _val(ROW_FTSE100)
    nasdaq100  = _val(ROW_NASDAQ100)
    msci_world = _val(ROW_MSCI_WORLD)
    gold       = _val(ROW_GOLD)

    return {
        'grand_total':    grand_total,
        'cash':           cash,
        'stocks_total':   stocks_total,
        'managed_total':  managed_total,
        'stocks_pnl_gbp': stocks_pnl_gbp,
        'stocks_pnl_pct': stocks_pnl_pct,
        'sp500':          sp500,
        'ftse100':        ftse100,
        'nasdaq100':      nasdaq100,
        'msci_world':     msci_world,
        'gold':           gold,
    }


# ---------------------------------------------------------------------------
# Fundamental refresh (weekly cadence)
# ---------------------------------------------------------------------------

# Same ticker config as claude_analyst.py — yf symbols for all held positions
YF_SYMBOLS = {
    'NVDA':   'NVDA',
    'RTX':    'RTX',
    'GOOG':   'GOOG',
    'BRK.B':  'BRK-B',
    'TECK.B': 'TECK-B.TO',
    'RIO':    'RIO.L',
    'SGLN':   'SGLN.L',
    'INRG':   'INRG.L',
    'IITU':   'IITU.L',
    'VGER':   'VGER.L',
    'BA.':    'BA.L',
    'VUSA':   'VUSA.L',
    'ISP6':   'ISP6.L',
    'LGEN':   'LGEN.L',
    'EUE':    'EUE.L',
    'RHM':    'RHM.DE',
    'HO':     'HO.PA',
}


def fetch_fundamentals(ticker, yf_sym):
    """Fetch P/E, revenue trend, analyst targets from yfinance. Weekly-only."""
    try:
        t    = yf.Ticker(yf_sym)
        info = t.info
        return {
            'trailingPE':              info.get('trailingPE'),
            'forwardPE':               info.get('forwardPE'),
            'revenueGrowth':           info.get('revenueGrowth'),
            'earningsGrowth':          info.get('earningsGrowth'),
            'targetMeanPrice':         info.get('targetMeanPrice'),
            'recommendationKey':       info.get('recommendationKey'),
            'numberOfAnalystOpinions': info.get('numberOfAnalystOpinions'),
            'marketCap':               info.get('marketCap'),
        }
    except Exception as e:
        print(f"  Fundamental fetch failed for {ticker}: {e}")
        return {}


# ---------------------------------------------------------------------------
# Message builders
# ---------------------------------------------------------------------------

def build_portfolio_section(summary):
    s           = summary
    pnl_sign    = '+' if s['stocks_pnl_gbp'] >= 0 else ''
    pnl_pct_str = pct_str(s['stocks_pnl_pct'])

    lines = [
        '📊 <b>WEEKLY DIGEST</b>',
        f'<i>{datetime.now(timezone.utc).strftime("%d %b %Y")}</i>',
        '',
        '— Portfolio —',
        f'Grand Total:     <b>£{s["grand_total"]:,.2f}</b>',
        f'Self-Managed:    £{s["stocks_total"]:,.2f}  ({pnl_sign}£{s["stocks_pnl_gbp"]:,.2f} / {pnl_pct_str})',
        f'Managed Funds:   £{s["managed_total"]:,.2f}',
        f'Cash:            £{s["cash"]:,.2f}',
    ]
    return '\n'.join(lines)


def build_benchmarks_section(summary):
    lines = [
        '',
        '— Benchmarks (live) —',
        f'S&P 500:     {summary["sp500"]:,.2f}',
        f'FTSE 100:    {summary["ftse100"]:,.2f}',
        f'NASDAQ 100:  {summary["nasdaq100"]:,.2f}',
        f'MSCI World:  {summary["msci_world"]:.2f}',
        f'Gold (SGLN): £{summary["gold"]:.2f}',
    ]
    return '\n'.join(lines)


def build_fas_section(results):
    if not results:
        return '\n— FAS Signals —\nNo recent scores available.'

    sorted_items = sorted(results.items(), key=lambda x: x[1].get('score', 5), reverse=True)
    lines        = ['', '— Top FAS Signals (latest run) —']

    for ticker, r in sorted_items:
        score = r.get('score', 5)
        rec   = r.get('recommendation', '')
        conf  = r.get('confidence', '')
        if score >= 7:
            emoji = '🟢'
        elif score <= 4:
            emoji = '🔴'
        else:
            emoji = '⚪'
        lines.append(f'{emoji} {ticker}: {score}/10 {rec} ({conf})')

    return '\n'.join(lines)


def build_prospects_section(prospect_results):
    if not prospect_results:
        return ''
    top = [(t, r) for t, r in prospect_results.items() if r.get('score', 0) >= 7]
    if not top:
        return ''
    top.sort(key=lambda x: x[1].get('score', 0), reverse=True)
    lines = ['', '— Prospect Signals (score ≥ 7) —']
    for ticker, r in top[:5]:
        score = r.get('score', 5)
        rec   = r.get('recommendation', '')
        notes = r.get('notes', '')
        line  = f'🟡 {ticker}: {score}/10 {rec}'
        if notes:
            line += f' — {notes}'
        lines.append(line)
    return '\n'.join(lines)


def build_fundamentals_section(fund_data):
    if not fund_data:
        return ''
    lines = ['', '— Fundamentals (weekly refresh) —']
    for ticker, data in fund_data.items():
        parts = []
        if data.get('trailingPE'):
            parts.append(f'P/E {data["trailingPE"]:.1f}')
        if data.get('recommendationKey'):
            parts.append(f'Rec: {data["recommendationKey"]}')
        if data.get('targetMeanPrice'):
            parts.append(f'Target £{data["targetMeanPrice"]:.2f}')
        if data.get('earningsGrowth') is not None:
            parts.append(f'EPS growth: {pct_str(data["earningsGrowth"]*100)}')
        if parts:
            lines.append(f'{ticker}: ' + ' | '.join(parts))
    return '\n'.join(lines) if len(lines) > 1 else ''


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("Connecting to Google Sheets...")
    creds = Credentials.from_service_account_file(SA_FILE, scopes=SCOPES)
    gc    = gspread.authorize(creds)
    sh    = gc.open_by_key(SHEET_ID)
    print(f"  Opened: {sh.title}")

    print("\nReading portfolio summary...")
    summary = read_portfolio_summary(sh)
    print(f"  Grand Total: £{summary['grand_total']:,.2f}")

    # Load latest FAS scores
    results = {}
    if os.path.exists(RESULTS_PATH):
        with open(RESULTS_PATH) as f:
            results = json.load(f)
        print(f"\nLoaded {len(results)} FAS results from {RESULTS_PATH}")
    else:
        print(f"\nNo FAS results file found at {RESULTS_PATH} — signals section will be empty")

    # Load prospect scores
    prospect_results = {}
    if os.path.exists(PROSPECT_PATH):
        with open(PROSPECT_PATH) as f:
            prospect_results = json.load(f)
        print(f"Loaded {len(prospect_results)} prospect results")

    # Weekly fundamental refresh
    print("\nFetching weekly fundamentals...")
    fund_data = {}
    for ticker, yf_sym in YF_SYMBOLS.items():
        fund_data[ticker] = fetch_fundamentals(ticker, yf_sym)
        print(f"  {ticker}: PE={fund_data[ticker].get('trailingPE')} "
              f"Rec={fund_data[ticker].get('recommendationKey')}")

    # Build message
    sections = [
        build_portfolio_section(summary),
        build_benchmarks_section(summary),
        build_fas_section(results),
        build_prospects_section(prospect_results),
        build_fundamentals_section(fund_data),
    ]
    message = '\n'.join(s for s in sections if s)

    print(f"\nSending digest ({len(message)} chars)...")
    if len(message) > 4096:
        # Telegram limit: split at section boundaries
        parts = message.split('\n\n—')
        chunk = parts[0]
        for part in parts[1:]:
            candidate = chunk + '\n\n—' + part
            if len(candidate) <= 4096:
                chunk = candidate
            else:
                send_telegram(chunk)
                chunk = '—' + part
        send_telegram(chunk)
    else:
        send_telegram(message)

    print("Done.")


if __name__ == '__main__':
    main()
