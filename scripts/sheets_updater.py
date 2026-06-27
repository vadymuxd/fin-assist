#!/usr/bin/env python3
"""
sheets_updater.py

Reads data/analysis_results.json (written by holdings_monitor.py) and:
  1. Writes Score (col K), Recommendation (col L), Last Updated (col M)
     to matching rows in Investments

Also handles the daily Notion Investments Context update (after 15:30 UTC run).
That block only runs when --snapshot flag is passed or when called from the
16:30 BST GitHub Actions workflow.

Run from repo root:
    python3 scripts/sheets_updater.py            # scores only
    python3 scripts/sheets_updater.py --snapshot  # scores + Notion snapshot
"""

import os
import sys
import json
import requests
from datetime import datetime, timezone
from dotenv import load_dotenv
import gspread
from google.oauth2.service_account import Credentials
from lib.supabase_sink import write_holdings
from lib.sheets_layout import find_investment_rows as find_inv_rows
from lib.notion_writer import (
    notion_headers,
    paragraph,
    heading2,
    divider,
    table,
    rebuild_page,
    INVESTMENTS_CONTEXT_ID,
)

load_dotenv()

SHEET_ID     = os.getenv('PORTFOLIO_SHEET_ID')
SA_FILE      = os.getenv('GOOGLE_APPLICATION_CREDENTIALS', 'config/service_account.json')
SCOPES       = ['https://www.googleapis.com/auth/spreadsheets']
RESULTS_PATH = 'data/analysis_results.json'


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def parse_float(val):
    if not val and val != 0:
        return 0.0
    cleaned = str(val).replace('£', '').replace(',', '').strip()
    try:
        return float(cleaned)
    except (ValueError, TypeError):
        return 0.0


# ---------------------------------------------------------------------------
# Sheet writers
# ---------------------------------------------------------------------------

def write_scores_to_inv26(sh, results):
    """
    Write Score (K), Recommendation (L), Last Updated (M) to Investments.
    Looks up each ticker dynamically in col A — safe if row order ever changes.
    """
    ws = sh.worksheet('Investments')
    col_a = ws.col_values(1)
    updated = 0

    for ticker, result in results.items():
        try:
            row = col_a.index(ticker) + 1  # 1-based
        except ValueError:
            print(f"  {ticker}: not found in Investments col A — skipping")
            continue

        score = result.get('score', '')
        rec   = result.get('recommendation', '')
        ts    = result.get('run_time', datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC'))

        ws.update_cell(row, 14, score)  # N: Score
        ws.update_cell(row, 15, rec)    # O: Recommendation
        ws.update_cell(row, 16, ts)     # P: Last Updated by Script

        print(f"  {ticker} row {row}: Score={score}, Rec={rec}")
        updated += 1

    print(f"  Investments: {updated} rows updated")
    return updated



# ---------------------------------------------------------------------------
# Notion Investments Context (daily, after close run)
# ---------------------------------------------------------------------------

# Investments Context page ID — also exported via lib.notion_writer for shared use
NOTION_PAGE_ID = INVESTMENTS_CONTEXT_ID


def update_notion_snapshot(sh, results):
    """
    Rebuild the Investments Context Notion page with current portfolio totals
    and latest FAS scores. Runs after the 15:30 UTC (16:30 BST) close run.
    Uses the Notion REST API directly — no MCP required.
    """
    notion_key = os.getenv('NOTION_API_KEY', '')
    if not notion_key:
        print("  NOTION_API_KEY not set — skipping snapshot")
        return

    headers = notion_headers(notion_key)
    run_time = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')

    try:
        ws = sh.worksheet('Investments')
        inv_rows = find_inv_rows(ws)

        def _rv(row_num):
            return ws.row_values(row_num) if row_num else []

        r_vadym   = _rv(inv_rows.get('vadym_total'))
        r_cash    = _rv(inv_rows.get('cash'))
        r_stocks  = _rv(inv_rows.get('stocks_total'))
        r_managed = _rv(inv_rows.get('managed_total'))

        vadym_total    = parse_float(r_vadym[6])    if len(r_vadym)   > 6  else 0
        cash           = parse_float(r_cash[6])     if len(r_cash)    > 6  else 0
        stocks_total   = parse_float(r_stocks[6])   if len(r_stocks)  > 6  else 0
        stocks_pnl     = parse_float(r_stocks[11])  if len(r_stocks)  > 11 else 0
        stocks_pnl_pct = parse_float(r_stocks[12])  if len(r_stocks)  > 12 else 0
        managed_total  = parse_float(r_managed[6])  if len(r_managed) > 6  else 0

        # Read individual stock positions (col A=Ticker, B=Name, C=Platform,
        # D=Qty, E=Avg Buy, F=Current Price, G=Current Value, L=P&L£, M=P&L%)
        all_rows = ws.get_all_values()
        positions = []
        for row in all_rows:
            if len(row) < 7:
                continue
            ticker = row[0].strip()
            if not ticker or ticker.startswith('=') or ticker.lower() in (
                'ticker', 'name', 'total', 'stocks', 'cash', 'managed', 'grand',
                'benchmark', 's&p', 'ftse', 'nasdaq', 'msci', 'gold', '',
            ):
                continue
            qty = parse_float(row[3]) if len(row) > 3 else 0
            if qty <= 0:
                continue
            # Actual sheet columns (0-indexed):
            # A=Ticker B=Name C=Platform D=Qty E=Avg Buy £ F=Current Price £
            # G=Current Value £  H=Initially Invested £
            # I=Tracking 26 Started Value £  J=Tracking 26 P&L £  K=Tracking 26 P&L %
            # L=Total P&L £  M=Total P&L %
            # N=Score  O=Recommendation  P=Last Updated
            positions.append({
                'ticker':      ticker,
                'name':        row[1].strip() if len(row) > 1 else '',
                'platform':    row[2].strip() if len(row) > 2 else '',
                'qty':         qty,
                'avg_buy':     parse_float(row[4]) if len(row) > 4 else 0,
                'price':       parse_float(row[5]) if len(row) > 5 else 0,
                'value':       parse_float(row[6]) if len(row) > 6 else 0,
                'tracking_started': parse_float(row[8]) if len(row) > 8 else 0,
                'tracking_pnl':    parse_float(row[9])  if len(row) > 9  else 0,
                'tracking_pct':    parse_float(row[10]) if len(row) > 10 else 0,
                'total_pnl':   parse_float(row[11]) if len(row) > 11 else 0,
                'total_pnl_pct': parse_float(row[12]) if len(row) > 12 else 0,
            })
    except Exception as e:
        print(f"  Could not read summary rows: {e}")
        vadym_total = cash = stocks_total = stocks_pnl = stocks_pnl_pct = managed_total = 0
        positions = []

    if positions:
        write_holdings([
            {
                'ticker':        p['ticker'],
                'name':          p['name'],
                'platform':      p['platform'],
                'qty':           p['qty'],
                'avg_buy':       p['avg_buy'],
                'current_price': p['price'],
                'value_gbp':     p['value'],
                'pnl_abs':       p['total_pnl'],
                'pnl_pct':       p['total_pnl_pct'],
                'tracking_started_value': p['tracking_started'],
                'tracking_pnl_pct':       p['tracking_pct'],
                'last_updated':  run_time,
            }
            for p in positions
        ])
        print(f"  Supabase holdings: {len(positions)} row(s) upserted")

    pnl_sign = '+' if stocks_pnl >= 0 else ''

    # --- Build page blocks ---
    blocks = []

    # Header
    blocks.append(paragraph(f'⚠️ Auto-updated by sheets_updater.py — {run_time}'))
    blocks.append(paragraph('Source of truth: Google Sheet Investments'))
    blocks.append(divider())

    # Summary table
    blocks.append(heading2('Summary'))
    pnl_pct_str = f'{pnl_sign}{stocks_pnl_pct:.1f}%' if stocks_pnl_pct else 'n/a'
    blocks.append(table([
        ['Metric', 'Value'],
        ['Self-Managed Stocks', f'£{stocks_total:,.2f}'],
        ['Managed Funds', f'£{managed_total:,.2f}'],
        ['Cash', f'£{cash:,.2f}'],
        ['Vadym Total', f'£{vadym_total:,.2f}'],
        ['Stocks P&L £', f'{pnl_sign}£{stocks_pnl:,.2f}'],
        ['Stocks P&L %', pnl_pct_str],
    ]))
    blocks.append(divider())

    # Individual positions table
    if positions:
        blocks.append(heading2('Stock Positions'))
        pos_rows = [['Ticker', 'Name', 'Platform', 'Value £', 'Since Apr 13 £', 'Since Apr 13 %', 'Total P&L £', 'Total P&L %']]
        for p in sorted(positions, key=lambda x: x['tracking_pct'], reverse=True):
            ts = '+' if p['tracking_pnl'] >= 0 else ''
            tp = '+' if p['total_pnl'] >= 0 else ''
            pos_rows.append([
                p['ticker'],
                p['name'],
                p['platform'],
                f"£{p['value']:,.2f}",
                f"{ts}£{p['tracking_pnl']:,.2f}",
                f"{ts}{p['tracking_pct']:.1f}%",
                f"{tp}£{p['total_pnl']:,.2f}",
                f"{tp}{p['total_pnl_pct']:.1f}%",
            ])
        blocks.append(table(pos_rows))
        blocks.append(divider())

    # FAS Scores table (if results available)
    if results:
        blocks.append(heading2('FAS Scores (latest run)'))
        score_rows = [['Ticker', 'Score', 'Rec', 'Confidence', 'Reason']]
        for ticker, r in sorted(results.items(), key=lambda x: x[1].get('score', 5), reverse=True):
            score_rows.append([
                ticker,
                str(r.get('score', '')),
                r.get('recommendation', ''),
                r.get('confidence', ''),
                (r.get('reason', '') or '')[:120],
            ])
        blocks.append(table(score_rows))
        blocks.append(divider())

    # Footer
    blocks.append(paragraph('Source of truth: Google Sheet Investments'))

    # --- Write to Notion ---
    if rebuild_page(NOTION_PAGE_ID, blocks, headers):
        print(f"  Notion Investments Context updated — Vadym Total £{vadym_total:,.2f}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def send_bot_confirmation(vadym_total):
    """Send a brief snapshot confirmation to Telegram when triggered via bot command."""
    token   = os.getenv('TELEGRAM_BOT_TOKEN')
    chat_id = os.getenv('TELEGRAM_CHAT_ID')
    if not token or not chat_id:
        return
    now_str = datetime.now(timezone.utc).strftime('%d %b %Y, %H:%M UTC')
    text = (
        f'✅ <b>Portfolio snapshot refreshed</b>\n'
        f'Vadym Total: <b>£{vadym_total:,.2f}</b>\n'
        f'<i>{now_str}</i>'
    )
    try:
        resp = requests.post(
            f'https://api.telegram.org/bot{token}/sendMessage',
            json={'chat_id': chat_id, 'text': text, 'parse_mode': 'HTML'},
            timeout=10,
        )
        resp.raise_for_status()
        print("  Bot confirmation sent.")
    except Exception as e:
        print(f"  Bot confirmation failed: {e}")


def main():
    do_snapshot = '--snapshot' in sys.argv
    do_bot      = '--bot' in sys.argv

    print("\nConnecting to Google Sheets...")
    creds = Credentials.from_service_account_file(SA_FILE, scopes=SCOPES)
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(SHEET_ID)
    print(f"  Opened: {sh.title}")

    if not os.path.exists(RESULTS_PATH):
        # Daily pipeline (news_fetcher → stock_assessor → alert_dispatcher) doesn't
        # produce analysis_results.json — this script's score-write path is now
        # only used by the /holdings bot command. Exit cleanly so missing file
        # never fails the daily monitor workflow.
        if do_snapshot:
            print(f"No results file at {RESULTS_PATH} — skipping score write, doing snapshot only")
            results = {}
        else:
            print(f"No results file at {RESULTS_PATH} — nothing to update, exiting cleanly")
            return
    else:
        with open(RESULTS_PATH) as f:
            results = json.load(f)
        print(f"Loaded {len(results)} results from {RESULTS_PATH}")

        print("\nWriting scores to Investments...")
        write_scores_to_inv26(sh, results)

    if do_snapshot:
        print("\nUpdating Notion Investments Context...")
        update_notion_snapshot(sh, results)

        if do_bot:
            try:
                ws          = sh.worksheet('Investments')
                inv_rows    = find_inv_rows(ws)
                r_vadym     = ws.row_values(inv_rows['vadym_total'])
                vadym_total = parse_float(r_vadym[6]) if len(r_vadym) > 6 else 0.0
            except Exception:
                vadym_total = 0.0
            send_bot_confirmation(vadym_total)

    print("\nDone.")


if __name__ == '__main__':
    main()
