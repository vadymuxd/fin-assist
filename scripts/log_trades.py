#!/usr/bin/env python3
"""
log_trades.py — Log investment trades to all stores.

Writes to:
  1. InvTransactions tab (Google Sheets) — appends one row per trade
  2. Investments tab (Google Sheets)     — adds/updates/removes stock rows,
                                           adjusts cash and the col I tracking
                                           baseline, rewrites aggregate formulas
  3. Supabase holding_trades             — one row per BUY/SELL (drives the
                                           dotted trade markers on the ticker page)
  4. Supabase sectors                    — sector/market for a newly bought ticker
  5. Supabase holdings                   — deletes the row on a full exit
  6. Supabase transactions table         — inserts DEPOSIT/WITHDRAWAL cash events

sync_worker calls process_trade() for BUY/SELL rows coming off the Notion queue,
so both entry routes write the same stores. Add new writes there, not in callers.

After running this script, call:
  python3 scripts/snapshot_worker.py --domain portfolio
  python3 scripts/sheets_updater.py --snapshot

Trade JSON schema (per item):
  {
    "date": "YYYY-MM-DD",
    "ticker": "SWMR",
    "name": "Swarmer, Inc",
    "action": "BUY" | "SELL" | "DEPOSIT" | "WITHDRAWAL" | "TRANSFER_IN" | "TRANSFER_OUT",
    "qty": 8.14461219,
    "price": 24.56,            // GBP per share
    "total": 200.00,           // GBP total
    "platform": "T212",        // T212 | Freetrade | Nutmeg | ...
    "notes": "optional",
    "price_formula": "=GOOGLEFINANCE(\"SWMR\")/GOOGLEFINANCE(\"CURRENCY:GBPUSD\")",  // optional
    "sector": "Industrials",   // BUY of a new ticker only — upserted into Supabase sectors table
    "market": "US"             // BUY of a new ticker only — e.g. US | LSE | EU | CA
  }

SELL behavior: if qty after sell == 0, the row is deleted automatically.
Aggregate formulas (Self-Managed Stocks total, Total T212, Total Freetrade)
are rewritten after every batch so they always reflect the current rows.
"""

import os
import re
import sys
import json
import argparse
from dotenv import load_dotenv
import gspread
from google.oauth2.service_account import Credentials

from lib.supabase_sink import write_transaction, write_holding_trade, delete_holding, write_sectors
from lib.sheets_layout import find_investment_rows

load_dotenv()

SHEET_ID = os.getenv('PORTFOLIO_SHEET_ID')
SA_FILE  = os.getenv('GOOGLE_APPLICATION_CREDENTIALS', 'config/service_account.json')
SCOPES   = ['https://www.googleapis.com/auth/spreadsheets']

CASH_ACTIONS = {'DEPOSIT', 'WITHDRAWAL'}


def parse_float(val):
    if val is None or val == '':
        return 0.0
    try:
        return float(str(val).replace('£', '').replace(',', '').strip())
    except (ValueError, TypeError):
        return 0.0


def connect_sheets():
    creds = Credentials.from_service_account_file(SA_FILE, scopes=SCOPES)
    gc = gspread.authorize(creds)
    return gc.open_by_key(SHEET_ID)


# ── Investments tab layout — uses shared lib.sheets_layout.find_investment_rows
# Re-exported as find_layout for backwards compatibility with this file's callers.
find_layout = find_investment_rows


def last_stock_row(ws, layout):
    """Last row with a ticker in col A, within the stocks section."""
    col_a = ws.col_values(1)
    last = layout['first_stock_row'] - 1
    # Stocks end just above the BENCHMARKS header. Fall back to the legacy
    # platform-subtotal / managed-fund boundary rows for older sheet layouts.
    end_excl = layout.get('stocks_end_row')
    if end_excl is None:
        end_excl = min(
            layout.get('t212_total_row', 10**9),
            layout.get('freetrade_total_row', 10**9),
            layout.get('managed_funds_row', 10**9),
        )
    for i in range(layout['first_stock_row'] - 1, end_excl - 1):
        if i < len(col_a) and col_a[i].strip():
            last = i + 1
    return last


# ── InvTransactions ───────────────────────────────────────────────────────────

def append_to_inv_transactions(ws, trade):
    action = trade['action'].upper()
    is_cash = action in CASH_ACTIONS
    row = [
        trade['date'],
        trade['ticker'],
        trade['name'],
        action,
        0 if is_cash else trade['qty'],
        0 if is_cash else trade['price'],
        trade['total'],
        trade.get('platform', ''),
        trade.get('notes', ''),
    ]
    ws.append_row(row, value_input_option='USER_ENTERED')
    if is_cash:
        print(f"  ✓ InvTransactions: {action} {trade['ticker']} £{trade['total']:,.2f}")
    else:
        print(f"  ✓ InvTransactions: {action} {trade['ticker']} {trade['qty']} @ £{trade['price']:.4f} = £{trade['total']:,.2f}")


# ── Investments tab: add / update / remove ────────────────────────────────────

def _copy_row_formulas(ws, source_row, target_row, skip_cols=()):
    """Copy formulas from cols F–M of source_row into target_row, adjusting row refs."""
    try:
        data = ws.get(f'F{source_row}:M{source_row}', value_render_option='FORMULA')
        if not data or not data[0]:
            return
        updates = []
        for j, formula in enumerate(data[0]):
            col_idx = j + 6  # F=6 (1-based)
            if col_idx in skip_cols:
                continue
            if not formula or not str(formula).startswith('='):
                continue
            adjusted = re.sub(
                rf'([A-Za-z]+){source_row}(?!\d)',
                lambda m, t=target_row: f'{m.group(1)}{t}',
                str(formula)
            )
            updates.append({
                'range': gspread.utils.rowcol_to_a1(target_row, col_idx),
                'values': [[adjusted]],
            })
        if updates:
            ws.batch_update(updates, value_input_option='USER_ENTERED')
    except Exception as e:
        print(f"  ⚠ Formula copy partial ({e})")


def add_new_position(ws, trade, layout):
    """Insert a new stock row just after the last stock."""
    insert_at = last_stock_row(ws, layout) + 1
    source_row = insert_at - 1  # the row above is the template

    ws.insert_rows([[]], row=insert_at, inherit_from_before=True)

    ws.update_cell(insert_at, 1, trade['ticker'])
    ws.update_cell(insert_at, 2, trade['name'])
    ws.update_cell(insert_at, 3, trade.get('platform', 'T212'))
    ws.update_cell(insert_at, 4, round(trade['qty'], 8))      # D: Qty
    ws.update_cell(insert_at, 5, round(trade['price'], 6))    # E: Avg Buy

    # F: price source — use provided formula or fall back to static current price
    price_formula = trade.get('price_formula')
    if price_formula:
        ws.update_cell(insert_at, 6, price_formula)
    else:
        ws.update_cell(insert_at, 6, round(trade['price'], 6))
        print(f"  ⚠ No price_formula provided — wrote static £{trade['price']:.4f} to col F. Update with GOOGLEFINANCE later.")

    # I: Tracking Started Value — new position has no Apr-13 history, use initial buy total
    ws.update_cell(insert_at, 9, round(trade['total'], 2))

    # Copy formulas for G, H, J, K, L, M from the row above (F and I are set above)
    _copy_row_formulas(ws, source_row, insert_at, skip_cols={6, 9})

    print(f"  ✓ Investments row {insert_at}: new position {trade['ticker']} ({trade['name']}) added")
    return insert_at


def remove_position_row(ws, ticker):
    """Delete the Investments row for a fully-exited ticker, and sync to Supabase holdings."""
    col_a = ws.col_values(1)
    try:
        row_idx = col_a.index(ticker) + 1
    except ValueError:
        print(f"  ⚠ {ticker} not found in Investments — cannot remove")
        return False
    ws.delete_rows(row_idx)
    print(f"  ✓ Investments: row {row_idx} ({ticker}) removed — position fully exited")
    if delete_holding(ticker):
        print(f"  ✓ Supabase holdings: {ticker} removed")
    else:
        print(f"  ⚠ Supabase holdings delete failed for {ticker} — remove manually")
    return True


def update_existing_position(ws, row_idx, trade):
    """Update Qty + Avg Buy for an existing position. Returns new_qty.

    Also moves col I (Tracking Started Value) by the cash that crosses the
    stocks boundary: +total on a BUY, -total on a SELL. Col I is the baseline
    the app subtracts to isolate organic (market) movement — I11 feeds
    portfolio_snapshots.stocks_started_value, and the dashboard's delta() is
    (Δ self_managed - Δ stocks_started_value). Leaving I alone on a BUY books
    the whole purchase as market gain: a £2,000 cash→stock move showed up as
    +£2,000 in WoW/MoM (IITU, 2026-08-05).

    This applies to EVERY position. The old rule only bumped I when I ≈ H
    (within 1%), i.e. positions the script itself had created, and skipped the
    ones carrying an Apr-13 tracking baseline (I ≠ H) — precisely the ones the
    phantom-gain bug hits.
    """
    action = trade['action'].upper()
    row_vals = ws.row_values(row_idx)
    old_qty = parse_float(row_vals[3]) if len(row_vals) > 3 else 0.0
    old_avg = parse_float(row_vals[4]) if len(row_vals) > 4 else 0.0
    old_i   = parse_float(row_vals[8]) if len(row_vals) > 8 else 0.0  # col I

    if action == 'BUY':
        new_qty = old_qty + trade['qty']
        new_avg = (
            (old_qty * old_avg + trade['qty'] * trade['price']) / new_qty
            if new_qty > 0 else trade['price']
        )
    else:  # SELL — avg cost basis unchanged
        new_qty = max(0.0, old_qty - trade['qty'])
        new_avg = old_avg

    if new_qty > 0:
        ws.update_cell(row_idx, 4, round(new_qty, 8))
        ws.update_cell(row_idx, 5, round(new_avg, 6))
        print(f"  ✓ Investments row {row_idx} ({trade['ticker']}): Qty {old_qty}→{new_qty}, Avg Buy £{old_avg:.4f}→£{new_avg:.4f}")

        # Move the baseline by the cash crossing the boundary, so the trade is
        # return-neutral: value and baseline both move by `total`, they cancel
        # in delta(), and only market movement survives.
        delta_i = trade['total'] if action == 'BUY' else -trade['total']
        new_i = max(0.0, old_i + delta_i)
        ws.update_cell(row_idx, 9, round(new_i, 2))
        print(f"  ✓ Tracking Started Value (col I): £{old_i:,.2f} → £{new_i:,.2f} "
              f"({'+' if delta_i >= 0 else '−'}£{abs(delta_i):,.2f}, keeps the trade return-neutral)")
    # NOTE full exit (new_qty == 0): the caller deletes the row, so I11 loses
    # the whole baseline while G11 loses the market value — the position's
    # realised gain drops out of the tracking series. Pre-existing; needs a
    # realised-adjustments row in the stocks range to hold the residual.
    return new_qty


def update_cash(ws, trade, layout):
    """Adjust uninvested cash by the trade total (BUY -, SELL +)."""
    action = trade['action'].upper()
    if action not in ('BUY', 'SELL'):
        return
    cash_row = layout['cash_row']
    cash_vals = ws.row_values(cash_row)
    old_cash = parse_float(cash_vals[6]) if len(cash_vals) > 6 else 0.0
    new_cash = old_cash - trade['total'] if action == 'BUY' else old_cash + trade['total']
    ws.update_cell(cash_row, 7, round(new_cash, 2))
    sign = '-' if action == 'BUY' else '+'
    print(f"  ✓ Cash: £{old_cash:,.2f} {sign}£{trade['total']:,.2f} → £{new_cash:,.2f}")


# ── Aggregate formula maintenance ─────────────────────────────────────────────

def rewrite_aggregate_formulas(ws):
    """
    Rewrite all stock-section aggregate formulas to reflect current row positions.
    Called once at the end of a batch.

      - Stocks total row (G,H,J,L): =SUM over current first..last stock range
      - Total T212:      =SUMIF(C..,"T212",G..) + cash
      - Total Freetrade: =SUMIF(C..,"Freetrade",G..)
    """
    layout = find_layout(ws)
    first  = layout['first_stock_row']
    last   = last_stock_row(ws, layout)
    cash   = layout['cash_row']
    stocks = layout['stocks_total_row']

    updates = [
        {'range': f'G{stocks}', 'values': [[f'=SUM(G{first}:G{last})']]},
        {'range': f'H{stocks}', 'values': [[f'=SUM(H{first}:H{last})']]},
        # Col I (Tracking Started Value) drives the app's stocks-only performance %.
        # Must be rewritten when rows are added/removed so I11 always sums the
        # whole stocks range — otherwise the app under/overstates organic growth.
        {'range': f'I{stocks}', 'values': [[f'=SUM(I{first}:I{last})']]},
        {'range': f'J{stocks}', 'values': [[f'=SUM(J{first}:J{last})']]},
        {'range': f'L{stocks}', 'values': [[f'=SUM(L{first}:L{last})']]},
    ]

    if 't212_total_row' in layout:
        updates.append({
            'range':  f'G{layout["t212_total_row"]}',
            'values': [[f'=SUMIF(C{first}:C{last},"T212",G{first}:G{last})+G{cash}']],
        })
    if 'freetrade_total_row' in layout:
        updates.append({
            'range':  f'G{layout["freetrade_total_row"]}',
            'values': [[f'=SUMIF(C{first}:C{last},"Freetrade",G{first}:G{last})']],
        })

    ws.batch_update(updates, value_input_option='USER_ENTERED')
    print(f"  ✓ Aggregate formulas rewritten over stock range rows {first}–{last}")


# ── Supabase ──────────────────────────────────────────────────────────────────

def write_ticker_sector(trade):
    """Upsert sector/market for a newly added ticker into the Supabase sectors table.
    Skipped silently if either field is missing — the lookup falls back to NULL,
    which the web app handles gracefully. Warns so it doesn't go unnoticed."""
    ticker = trade['ticker']
    sector = trade.get('sector')
    market = trade.get('market')
    if not sector or not market:
        print(f"  ⚠ {ticker}: no sector/market provided — Allocation chart will miss this ticker until the sectors table is updated")
        return
    ok = write_sectors([{'ticker': ticker, 'sector': sector, 'market': market}])
    if ok:
        print(f"  ✓ Supabase sectors: {ticker} → sector={sector}, market={market}")
    else:
        print(f"  ⚠ Supabase sectors upsert failed for {ticker}")


def log_to_supabase(trade):
    action = trade['action'].upper()
    if action not in CASH_ACTIONS:
        return
    ok = write_transaction({
        'date':         trade['date'],
        'domain':       'investments',
        'account_name': trade.get('platform', ''),
        'amount_gbp':   trade['total'],
        'type':         action.lower(),
        'notes':        trade.get('notes', '') or trade.get('name', ''),
        'source':       'nl_claude',
    })
    if ok:
        print(f"  ✓ Supabase transactions: {action} £{trade['total']:,.2f}")
    else:
        print(f"  ⚠ Supabase insert failed for {action} {trade['ticker']}")


# ── Per-trade dispatcher ──────────────────────────────────────────────────────

def process_trade(ws_inv, ws_inv_tx, trade):
    """Process one trade end-to-end. Layout/rows may shift between trades, so
    we always look up fresh state."""
    action = trade['action'].upper()
    append_to_inv_transactions(ws_inv_tx, trade)

    if action in CASH_ACTIONS:
        log_to_supabase(trade)
        return

    if action not in ('BUY', 'SELL'):
        print(f"  ⚠ Unsupported action: {action} — only InvTransactions row appended")
        return

    # Write to holding_trades for the web app chart
    ok = write_holding_trade({
        'date':      trade['date'],
        'ticker':    trade['ticker'],
        'action':    action,
        'qty':       trade['qty'],
        'price_gbp': trade['price'],
        'total_gbp': trade['total'],
        'platform':  trade.get('platform'),
        'notes':     trade.get('notes'),
    })
    if ok:
        print(f"  ✓ Supabase holding_trades: {action} {trade['ticker']} {trade['qty']} @ £{trade['price']:.4f}")
    else:
        print(f"  ⚠ Supabase holding_trades insert failed for {action} {trade['ticker']}")

    layout = find_layout(ws_inv)
    col_a  = ws_inv.col_values(1)
    ticker = trade['ticker']
    try:
        row_idx = col_a.index(ticker) + 1
    except ValueError:
        row_idx = None

    if row_idx is None:
        if action == 'BUY':
            add_new_position(ws_inv, trade, layout)
            update_cash(ws_inv, trade, layout)
            write_ticker_sector(trade)
        else:
            print(f"  ⚠ {ticker} not found — cannot SELL unknown position")
        return

    new_qty = update_existing_position(ws_inv, row_idx, trade)
    update_cash(ws_inv, trade, layout)

    if action == 'SELL' and new_qty == 0:
        remove_position_row(ws_inv, ticker)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='Log investment trades to all stores.')
    parser.add_argument('--json', help='JSON array of trade objects')
    parser.add_argument('--remove', metavar='TICKER', help='Manually remove a row by ticker (rare; SELL→0 auto-removes)')
    args = parser.parse_args()

    if not args.json and not args.remove:
        parser.error('Provide --json or --remove')

    print('\nConnecting to Google Sheets...')
    sh        = connect_sheets()
    ws_inv    = sh.worksheet('Investments')
    ws_inv_tx = sh.worksheet('InvTransactions')
    print(f'  Opened: {sh.title}\n')

    if args.remove:
        remove_position_row(ws_inv, args.remove.upper())
        rewrite_aggregate_formulas(ws_inv)
        print('\n✅ Row removed and aggregates refreshed.')
        return

    try:
        trades = json.loads(args.json)
    except json.JSONDecodeError as e:
        print(f'Invalid JSON: {e}', file=sys.stderr)
        sys.exit(1)
    if isinstance(trades, dict):
        trades = [trades]

    layout = find_layout(ws_inv)
    print(f"Layout: cash={layout.get('cash_row')} stocks_total={layout.get('stocks_total_row')} "
          f"first_stock={layout.get('first_stock_row')} t212_total={layout.get('t212_total_row')} "
          f"freetrade_total={layout.get('freetrade_total_row')} managed_funds={layout.get('managed_funds_row')}\n")

    print(f'Processing {len(trades)} trade(s)...')
    for trade in trades:
        process_trade(ws_inv, ws_inv_tx, trade)

    print('\nRewriting aggregate formulas...')
    rewrite_aggregate_formulas(ws_inv)

    print(f'\n✅ {len(trades)} trade(s) logged.')
    print('\nRun next to refresh snapshots:')
    print('  python3 scripts/snapshot_worker.py --domain portfolio')
    print('  python3 scripts/sheets_updater.py --snapshot')


if __name__ == '__main__':
    main()
