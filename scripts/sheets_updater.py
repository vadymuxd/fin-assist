#!/usr/bin/env python3
"""
sheets_updater.py

Reads data/analysis_results.json (written by holdings_monitor.py) and:
  1. Writes Score (col K), Recommendation (col L), Last Updated (col M)
     to matching rows in Inv26 - Summary
  2. Appends a row to Analysis Log for each scored ticker

Also handles the daily Notion Portfolio Snapshot update (after 15:30 UTC run).
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
    Write Score (K), Recommendation (L), Last Updated (M) to Inv26 - Summary.
    Looks up each ticker dynamically in col A — safe if row order ever changes.
    """
    ws = sh.worksheet('Inv26 - Summary')
    col_a = ws.col_values(1)
    updated = 0

    for ticker, result in results.items():
        try:
            row = col_a.index(ticker) + 1  # 1-based
        except ValueError:
            print(f"  {ticker}: not found in Inv26 - Summary col A — skipping")
            continue

        score = result.get('score', '')
        rec   = result.get('recommendation', '')
        ts    = result.get('run_time', datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC'))

        ws.update_cell(row, 14, score)  # N: Score
        ws.update_cell(row, 15, rec)    # O: Recommendation
        ws.update_cell(row, 16, ts)     # P: Last Updated by Script

        print(f"  {ticker} row {row}: Score={score}, Rec={rec}")
        updated += 1

    print(f"  Inv26 - Summary: {updated} rows updated")
    return updated


def append_to_analysis_log(sh, results):
    """
    Append one row per ticker to Analysis Log.
    Columns: Date | Ticker | Score | Confidence | Reason
    """
    ws = sh.worksheet('Analysis Log')

    # Write header if sheet is empty
    if not ws.get_all_values():
        ws.append_row(['Date', 'Ticker', 'Score', 'Recommendation', 'Confidence', 'Reason'])

    rows = []
    for ticker, result in results.items():
        rows.append([
            result.get('run_time', ''),
            ticker,
            result.get('score', ''),
            result.get('recommendation', ''),
            result.get('confidence', ''),
            result.get('reason', ''),
        ])

    if rows:
        ws.append_rows(rows, value_input_option='USER_ENTERED')
        print(f"  Analysis Log: {len(rows)} rows appended")


# ---------------------------------------------------------------------------
# Notion portfolio snapshot (daily, after close run)
# ---------------------------------------------------------------------------

NOTION_PAGE_ID = '33f416f2-7566-81ce-b7e8-dd7b68101342'  # Portfolio Snapshot page
NOTION_VERSION = '2022-06-28'


def _notion_headers(key):
    return {
        'Authorization': f'Bearer {key}',
        'Notion-Version': NOTION_VERSION,
        'Content-Type': 'application/json',
    }


def _rt(text, bold=False):
    """Build a Notion rich_text object."""
    obj = {'type': 'text', 'text': {'content': str(text)}}
    if bold:
        obj['annotations'] = {'bold': True}
    return obj


def _paragraph(text, bold=False):
    return {'object': 'block', 'type': 'paragraph',
            'paragraph': {'rich_text': [_rt(text, bold)]}}


def _heading2(text):
    return {'object': 'block', 'type': 'heading_2',
            'heading_2': {'rich_text': [_rt(text)]}}


def _divider():
    return {'object': 'block', 'type': 'divider', 'divider': {}}


def _table(rows, has_column_header=True):
    """Build a Notion table block with rows as children.
    rows: list of lists of str — first row is the header if has_column_header=True.
    Notion API requires table_row children inside the 'table' object.
    """
    table_rows = [
        {'object': 'block', 'type': 'table_row',
         'table_row': {'cells': [[_rt(cell)] for cell in row]}}
        for row in rows
    ]
    return {
        'object': 'block',
        'type': 'table',
        'table': {
            'table_width': len(rows[0]),
            'has_column_header': has_column_header,
            'has_row_header': False,
            'children': table_rows,
        },
    }


def _archive_page_blocks(page_id, headers):
    """Delete all top-level blocks from a Notion page."""
    resp = requests.get(
        f'https://api.notion.com/v1/blocks/{page_id}/children',
        headers=headers, timeout=10,
    )
    if resp.status_code != 200:
        print(f"  Could not fetch page blocks: {resp.text[:200]}")
        return
    for block in resp.json().get('results', []):
        requests.patch(
            f'https://api.notion.com/v1/blocks/{block["id"]}',
            headers=headers,
            json={'archived': True},
            timeout=10,
        )


def update_notion_snapshot(sh, results):
    """
    Rebuild the Portfolio Snapshot Notion page with current portfolio totals
    and latest FAS scores. Runs after the 15:30 UTC (16:30 BST) close run.
    Uses the Notion REST API directly — no MCP required.
    """
    notion_key = os.getenv('NOTION_API_KEY', '')
    if not notion_key:
        print("  NOTION_API_KEY not set — skipping snapshot")
        return

    headers = _notion_headers(notion_key)
    run_time = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')

    # --- Read summary totals from Inv26 - Summary ---
    # Row 7 = Grand Total row (col G = current value total)
    # Row 9 = Cash row (col G = cash value)
    # Row 11 = Self-managed stocks totals (col G = stocks total, L = P&L £, M = P&L %)
    # Row 28 = Managed Funds totals (col G = managed total)
    # All values are 0-based index into row_values()
    try:
        ws = sh.worksheet('Inv26 - Summary')
        row7  = ws.row_values(7)
        row9  = ws.row_values(9)
        row11 = ws.row_values(11)
        row28 = ws.row_values(28)

        grand_total    = parse_float(row7[6])   if len(row7)  > 6  else 0
        cash           = parse_float(row9[6])   if len(row9)  > 6  else 0
        stocks_total   = parse_float(row11[6])  if len(row11) > 6  else 0
        stocks_pnl     = parse_float(row11[11]) if len(row11) > 11 else 0
        stocks_pnl_pct = parse_float(row11[12]) if len(row11) > 12 else 0
        managed_total  = parse_float(row28[6])  if len(row28) > 6  else 0

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
                'tracking_pnl':    parse_float(row[9])  if len(row) > 9  else 0,
                'tracking_pct':    parse_float(row[10]) if len(row) > 10 else 0,
                'total_pnl':   parse_float(row[11]) if len(row) > 11 else 0,
                'total_pnl_pct': parse_float(row[12]) if len(row) > 12 else 0,
            })
    except Exception as e:
        print(f"  Could not read summary rows: {e}")
        grand_total = cash = stocks_total = stocks_pnl = stocks_pnl_pct = managed_total = 0
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
                'last_updated':  run_time,
            }
            for p in positions
        ])
        print(f"  Supabase holdings: {len(positions)} row(s) upserted")

    pnl_sign = '+' if stocks_pnl >= 0 else ''

    # --- Build page blocks ---
    blocks = []

    # Header
    blocks.append(_paragraph(f'⚠️ Auto-updated by sheets_updater.py — {run_time}'))
    blocks.append(_paragraph('Source of truth: Google Sheet Inv26 - Summary'))
    blocks.append(_divider())

    # Summary table
    blocks.append(_heading2('Summary'))
    pnl_pct_str = f'{pnl_sign}{stocks_pnl_pct:.1f}%' if stocks_pnl_pct else 'n/a'
    blocks.append(_table([
        ['Metric', 'Value'],
        ['Self-Managed Stocks', f'£{stocks_total:,.2f}'],
        ['Managed Funds', f'£{managed_total:,.2f}'],
        ['Cash', f'£{cash:,.2f}'],
        ['Grand Total', f'£{grand_total:,.2f}'],
        ['Stocks P&L £', f'{pnl_sign}£{stocks_pnl:,.2f}'],
        ['Stocks P&L %', pnl_pct_str],
    ]))
    blocks.append(_divider())

    # Individual positions table
    if positions:
        blocks.append(_heading2('Stock Positions'))
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
        blocks.append(_table(pos_rows))
        blocks.append(_divider())

    # FAS Scores table (if results available)
    if results:
        blocks.append(_heading2('FAS Scores (latest run)'))
        score_rows = [['Ticker', 'Score', 'Rec', 'Confidence', 'Reason']]
        for ticker, r in sorted(results.items(), key=lambda x: x[1].get('score', 5), reverse=True):
            score_rows.append([
                ticker,
                str(r.get('score', '')),
                r.get('recommendation', ''),
                r.get('confidence', ''),
                (r.get('reason', '') or '')[:120],
            ])
        blocks.append(_table(score_rows))
        blocks.append(_divider())

    # Footer
    blocks.append(_paragraph('Source of truth: Google Sheet Inv26 - Summary'))

    # --- Write to Notion ---
    print(f"  Archiving existing page blocks...")
    _archive_page_blocks(NOTION_PAGE_ID, headers)

    print(f"  Writing {len(blocks)} new blocks to Portfolio Snapshot...")
    resp = requests.patch(
        f'https://api.notion.com/v1/blocks/{NOTION_PAGE_ID}/children',
        headers=headers,
        json={'children': blocks},
        timeout=15,
    )
    if resp.status_code == 200:
        print(f"  Notion snapshot updated — Grand Total £{grand_total:,.2f}")
    else:
        print(f"  Notion write failed ({resp.status_code}): {resp.text[:300]}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def send_bot_confirmation(grand_total):
    """Send a brief snapshot confirmation to Telegram when triggered via bot command."""
    token   = os.getenv('TELEGRAM_BOT_TOKEN')
    chat_id = os.getenv('TELEGRAM_CHAT_ID')
    if not token or not chat_id:
        return
    now_str = datetime.now(timezone.utc).strftime('%d %b %Y, %H:%M UTC')
    text = (
        f'✅ <b>Portfolio snapshot refreshed</b>\n'
        f'Grand Total: <b>£{grand_total:,.2f}</b>\n'
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
        if do_snapshot:
            # Bot /snapshot command: skip score writing, just update Notion + notify
            print(f"No results file at {RESULTS_PATH} — skipping score write, doing snapshot only")
            results = {}
        else:
            print(f"No results file at {RESULTS_PATH} — run holdings_monitor.py first")
            sys.exit(1)
    else:
        with open(RESULTS_PATH) as f:
            results = json.load(f)
        print(f"Loaded {len(results)} results from {RESULTS_PATH}")

        print("\nWriting scores to Inv26 - Summary...")
        write_scores_to_inv26(sh, results)

        print("\nAppending to Analysis Log...")
        append_to_analysis_log(sh, results)

    if do_snapshot:
        print("\nUpdating Notion portfolio snapshot...")
        update_notion_snapshot(sh, results)

        if do_bot:
            try:
                ws       = sh.worksheet('Inv26 - Summary')
                row7     = ws.row_values(7)
                grand_total = parse_float(row7[6]) if len(row7) > 6 else 0.0
            except Exception:
                grand_total = 0.0
            send_bot_confirmation(grand_total)

    print("\nDone.")


if __name__ == '__main__':
    main()
