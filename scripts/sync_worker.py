#!/usr/bin/env python3
"""
sync_worker.py — Phase 16 orchestrator.

Reads the Notion Financial Updates DB, routes each row by (Type, Domain),
writes the appropriate Sheets cells/columns and Supabase transactions,
then marks rows synced. snapshot_worker is run separately by bot_sync.yml
after this script completes.

Pipeline per row:
  1. Fetch unsynced rows (Status=confirmed AND Sheets Written=false)
  2. Route per (Type, Domain) — handlers update Sheets directly
  3. Mark Sheets Written=true on the Notion row
  4. After all rows processed: mark Status=synced + Supabase Written=true + Synced At=today
  5. Send Telegram summary

CLI:
  --dry-run            Read Notion only, log planned actions, no writes
  --id <notion_id>     Sync one specific row by Notion page id
  (default)            Sync all rows where Status=confirmed AND Sheets Written=false
"""

import os
import sys
import tempfile
import argparse
from datetime import date
from dotenv import load_dotenv
import gspread
from google.oauth2.service_account import Credentials

from lib.sheets_layout import find_investment_rows
from lib.notion_writer import notion_headers
from lib.notion_db import (
    fetch_unsynced_financial_updates,
    extract_financial_update,
    query_database,
    update_page_properties,
    mark_row_synced,
    mark_row_failed,
    mark_sheets_written,
    prop_select,
    prop_checkbox,
    FINANCIAL_UPDATES_DB_ID,
)
from lib.supabase_sink import write_transaction, write_property_value


load_dotenv()

SHEET_ID = os.getenv('PORTFOLIO_SHEET_ID')
SA_FILE  = os.getenv('GOOGLE_APPLICATION_CREDENTIALS', 'config/service_account.json')
SCOPES   = ['https://www.googleapis.com/auth/spreadsheets']

COL_VALUE_IDX = 7  # col G (1-based) for cash/managed/lisa value cells in Investments tab

# Handoff file for the combined bot_sync Telegram message. sync_worker writes
# its Notion-queue summary here when DEFER_SYNC_TELEGRAM is set; snapshot_worker
# reads it and sends one message. Same path must be used by both scripts.
SYNC_SUMMARY_FILE = os.path.join(tempfile.gettempdir(), 'fin_assist_sync_summary.txt')


# ── Sheet utilities ──────────────────────────────────────────────────────────

def open_sheet():
    creds = Credentials.from_service_account_file(SA_FILE, scopes=SCOPES)
    return gspread.authorize(creds).open_by_key(SHEET_ID)


# Per-run cache: gspread's sh.worksheet(name) re-fetches spreadsheet metadata on
# EVERY call, and several handlers call ws.get_all_values() repeatedly for data
# that hasn't changed since the last read within this run. Both are full Sheets
# API requests, and the pipeline runs multiple scripts back-to-back against the
# same spreadsheet/user, so redundant reads burst past Google's per-minute quota.
# Fix: open each worksheet once and cache its values; only re-fetch after a
# write we made ourselves invalidates the cache.
_ws_cache = {}
_values_cache = {}


def get_worksheet(sh, title):
    """Cached sh.worksheet(title) — avoids a fresh metadata fetch on every call."""
    key = (sh.id, title)
    ws = _ws_cache.get(key)
    if ws is None:
        ws = sh.worksheet(title)
        _ws_cache[key] = ws
    return ws


def get_values(ws):
    """Cached ws.get_all_values() — fetched once, reused until invalidate_values()
    is called after a write to this worksheet."""
    cached = _values_cache.get(ws.id)
    if cached is None:
        cached = ws.get_all_values()
        _values_cache[ws.id] = cached
    return cached


def invalidate_values(ws):
    """Drop the cached values for `ws` — call after any write to it."""
    _values_cache.pop(ws.id, None)


def parse_float(val):
    if val is None or str(val).strip() == '':
        return 0.0
    try:
        return float(str(val).replace('£', '').replace(',', '').strip())
    except (ValueError, TypeError):
        return 0.0


def today_header():
    """Today as 'Mon D, YYYY' (e.g. 'May 21, 2026') — matches Savings/Pensions sheet format."""
    t = date.today()
    return t.strftime('%b ') + str(t.day) + t.strftime(', %Y')


def find_or_create_date_column(ws, header_text):
    """Return 1-based column index of the column whose header matches `header_text`.
    Creates a new column at the end if not found.

    Matches by PARSED DATE, not literal string. ws.update_cell() always sends
    valueInputOption=USER_ENTERED (gspread hardcodes this for this method) —
    Sheets silently reinterprets a date-shaped string like 'Jul 3, 2026' as an
    actual date value and renders it back per the column's number format (seen
    in practice as 'July 3, 2026'). A literal string compare then never matches
    on a second call for the same day, so each entry synced that day created
    its OWN new column instead of sharing one — 6 duplicate 'July 3, 2026'
    columns were created this way on 2026-07-03 once multiple same-day entries
    started arriving via monzo_balance_sync. _parse_date_header() already
    handles both '%b %d, %Y' and '%B %d, %Y', so comparing parsed dates is
    robust regardless of how Sheets chose to format the round-tripped value.
    """
    headers = get_values(ws)[0] if get_values(ws) else []
    target_date = _parse_date_header(header_text)
    for i, h in enumerate(headers, start=1):
        if target_date is not None and _parse_date_header(h) == target_date:
            return i, False  # found, not created
        if h.strip() == header_text.strip():
            return i, False  # non-date header fallback (exact match)
    new_col = len(headers) + 1
    if new_col > ws.col_count:
        ws.add_cols(new_col - ws.col_count)
    ws.update_cell(1, new_col, header_text)
    invalidate_values(ws)
    return new_col, True


def _is_date_header(h):
    """True if header matches the 'Mon D, YYYY' format used by Savings + Pensions tabs."""
    return bool(_re.match(r'^[A-Za-z]+ \d{1,2}, \d{4}$', (h or '').strip()))


def _parse_date_header(h):
    """Parse 'Mon D, YYYY' header to a date for chronological sorting."""
    from datetime import datetime
    for fmt in ('%b %d, %Y', '%B %d, %Y'):
        try:
            return datetime.strptime((h or '').strip(), fmt).date()
        except ValueError:
            continue
    return None


def latest_date_column(ws):
    """Return 1-based index of the chronologically latest date column on `ws`,
    or None if no date columns are present."""
    headers = get_values(ws)[0] if get_values(ws) else []
    dated = []
    for col_i, h in enumerate(headers, start=1):
        if not _is_date_header(h):
            continue
        d = _parse_date_header(h)
        if d:
            dated.append((col_i, d))
    if not dated:
        return None
    dated.sort(key=lambda x: x[1])
    return dated[-1][0]


def self_heal_sparse_columns(sh):
    """Run carry_forward_column on the latest date column of Savings Balance
    and Pensions. Idempotent — only fills empty cells — so safe to run every
    sync, even when no Notion entries were pending."""
    healed = []
    for sheet_name in ('Savings Balance', 'Pensions'):
        try:
            ws = get_worksheet(sh, sheet_name)
        except Exception as e:
            print(f"  ⚠ {sheet_name}: cannot open ({e})")
            continue
        col = latest_date_column(ws)
        if col is None:
            print(f"  {sheet_name}: no date columns — skipping")
            continue
        # Header already known from latest_date_column's cached read above —
        # no need for a separate ws.cell(1, col) API call.
        header = get_values(ws)[0][col - 1]
        cf_count = carry_forward_column(ws, col)
        if cf_count:
            print(f"  {sheet_name} · {header} (col {col}): +{cf_count} carry-fwd")
            healed.append(f"{sheet_name}:{cf_count}")
        else:
            print(f"  {sheet_name} · {header} (col {col}): already complete")
    return healed


def carry_forward_column(ws, target_col):
    """Fill empty cells in target_col with each row's most-recent prior value
    from other date columns. Idempotent — skips non-empty cells. Returns count
    of cells written.

    Used after sync_worker creates a new date column so the column reflects a
    complete household snapshot (not just the one NL-updated account), which is
    what snapshot_worker + the web app expect.
    """
    all_rows = get_values(ws)
    if not all_rows:
        return 0
    headers = all_rows[0]

    # Date columns to the left of target_col, ordered chronologically
    prior_cols = []
    for col_i, h in enumerate(headers, start=1):
        if col_i == target_col or not _is_date_header(h):
            continue
        d = _parse_date_header(h)
        if d:
            prior_cols.append((col_i, d))
    prior_cols.sort(key=lambda x: x[1])  # oldest → newest

    batch = []
    for row_idx, row in enumerate(all_rows[1:], start=2):
        # Skip if target cell already populated
        if target_col - 1 < len(row) and row[target_col - 1].strip():
            continue
        # Skip subtotal/total rows (empty bank+account)
        first_non_empty = next((c.strip() for c in row[:3] if c.strip()), '')
        if not first_non_empty or first_non_empty.lower() in ('total', 'joint total', 'subtotal'):
            continue
        # Find most-recent non-empty source cell; carry-forward zero too
        # (a £0 balance is meaningful — an empty pot, not missing data).
        for col_i, _ in reversed(prior_cols):
            if col_i - 1 < len(row) and row[col_i - 1].strip():
                val = parse_float(row[col_i - 1])
                batch.append({
                    'range': gspread.utils.rowcol_to_a1(row_idx, target_col),
                    'values': [[val]],
                })
                break

    if batch:
        ws.batch_update(batch, value_input_option='USER_ENTERED')
        invalidate_values(ws)
    return len(batch)


import re as _re


def _normalise(s):
    """Strip everything except a–z and 0–9 (lowercase). So 'Legal & General' / 'Pension Bee'
    match 'LegalGeneral' / 'PensionBee' — same account, different naming convention."""
    return _re.sub(r'[^a-z0-9]', '', (s or '').lower())


def find_savings_row(ws, account_name):
    """Match a Savings Balance row to a Notion Account string.

    Strategy:
      1. Prefer rows where target contains BOTH bank AND account name (best signal).
      2. If exactly one row matches by account name alone, accept it (handles
         users who omit the bank prefix).
      3. Otherwise return None (ambiguous — can't tell which 'Cash ISA' they mean).
    """
    rows = get_values(ws)
    target = _normalise(account_name)
    if not target:
        return None, None, None

    both_matches = []
    account_only = []

    for i, row in enumerate(rows[1:], start=2):
        if len(row) < 2:
            continue
        bank    = _normalise(row[0])
        account = _normalise(row[1])
        if not account:
            continue
        # Skip aggregate rows like 'Total' (bank='total', account='')
        if bank == 'total':
            continue
        if bank in target and account in target:
            both_matches.append((i, row[0].strip(), row[1].strip()))
        elif account in target:
            account_only.append((i, row[0].strip(), row[1].strip()))

    if len(both_matches) == 1:
        return both_matches[0]
    if len(both_matches) > 1:
        return None, None, None  # ambiguous bank-and-account match
    if len(account_only) == 1:
        return account_only[0]
    return None, None, None


def find_pensions_row(ws, account_name):
    """Match a Pensions row to a Notion Account string.

    Same lenient strategy as savings:
      1. Prefer rows where target contains BOTH provider AND employer.
      2. Fall back to unique provider-only or employer-only match.
    """
    rows = get_values(ws)
    target = _normalise(account_name)
    if not target:
        return None, None, None

    both_matches = []
    one_side    = []

    for i, row in enumerate(rows[1:], start=2):
        if len(row) < 3:
            continue
        provider = _normalise(row[1])
        employer = _normalise(row[2])
        if not provider or not employer:
            continue
        if provider in target and employer in target:
            both_matches.append((i, row[1].strip(), row[2].strip()))
        elif provider in target or employer in target:
            one_side.append((i, row[1].strip(), row[2].strip()))

    if len(both_matches) == 1:
        return both_matches[0]
    if len(both_matches) > 1:
        return None, None, None
    if len(one_side) == 1:
        return one_side[0]
    return None, None, None


def find_investments_balance_row(ws, account_name):
    """For Investments BALANCE_UPDATE, map Account text → row in Investments tab.

    Returns (row_1based, label) where label is one of cash/managed/lisa.
    """
    rows = find_investment_rows(ws)
    a = (account_name or '').lower()

    if 'lisa' in a or 'hsbc gic' in a or 'gic isa' in a:
        return rows.get('lisa_total'), 'lisa'
    if 'cash' in a or 't212 cash' in a or 'freetrade cash' in a:
        return rows.get('cash'), 'cash'
    if 'managed' in a or 'nutmeg' in a or 'jp morgan' in a or 'j.p. morgan' in a or 'alpha' in a:
        return rows.get('managed_total'), 'managed'
    return None, None


def find_managed_fund_row(ws, account_name):
    """Locate the specific managed-fund detail row (e.g. Nutmeg) by name.

    Scans the rows below the MANAGED FUNDS aggregate, matching the Notion
    Account text against each fund's Name/Platform cells. Returns
    (row_1based, fund_name) or None. Used so a DEPOSIT/WITHDRAWAL on a managed
    fund updates the fund itself rather than the brokerage cash pile.
    """
    layout = find_investment_rows(ws)
    start = layout.get('managed_total')  # aggregate row; fund detail begins next row
    if not start:
        return None
    all_rows = get_values(ws)
    a = (account_name or '').lower()
    for i in range(start + 1, len(all_rows) + 1):
        row = all_rows[i - 1] if i - 1 < len(all_rows) else []
        label = (row[0] if len(row) > 0 else '').strip()
        name  = (row[1] if len(row) > 1 else '').strip()
        plat  = (row[2] if len(row) > 2 else '').strip()
        if label and not name:  # next section header (e.g. BENCHMARKS) — stop
            break
        if not name:
            continue
        tokens = [w for w in (name + ' ' + plat).lower().replace('/', ' ').split() if len(w) > 3]
        if any(t in a for t in tokens):
            return i, name
    return None


# ── Handlers — per (Type, Domain) ────────────────────────────────────────────

def handle_balance_update(entry, sh):
    """BALANCE_UPDATE — write new balance to Sheets. No transactions write."""
    domain = entry['domain']
    new_balance = entry['new_balance']
    if new_balance is None:
        raise ValueError("BALANCE_UPDATE missing New Balance £")

    if domain == 'savings':
        ws = get_worksheet(sh, 'Savings Balance')
        row, bank, account = find_savings_row(ws, entry['account'])
        if not row:
            raise ValueError(f"Savings account not found in sheet: {entry['account']!r}")
        col, _created = find_or_create_date_column(ws, today_header())
        ws.update_cell(row, col, new_balance)
        invalidate_values(ws)
        # Always carry-forward — idempotent, only fills empty cells. Self-heals
        # sparse columns left by earlier runs (e.g. pre-fix Phase 16 syncs).
        cf_count = carry_forward_column(ws, col)
        cf_note = f' (+{cf_count} carry-fwd)' if cf_count else ''
        return f"Savings · {bank} {account} · row {row} col {col}{cf_note} = £{new_balance:,.2f}"

    if domain == 'pensions':
        ws = get_worksheet(sh, 'Pensions')
        row, provider, employer = find_pensions_row(ws, entry['account'])
        if not row:
            raise ValueError(f"Pension not found in sheet: {entry['account']!r}")
        col, _created = find_or_create_date_column(ws, today_header())
        ws.update_cell(row, col, new_balance)
        invalidate_values(ws)
        cf_count = carry_forward_column(ws, col)
        cf_note = f' (+{cf_count} carry-fwd)' if cf_count else ''
        return f"Pensions · {provider} {employer} · row {row} col {col}{cf_note} = £{new_balance:,.2f}"

    if domain == 'investments':
        ws = get_worksheet(sh, 'Investments')
        row, label = find_investments_balance_row(ws, entry['account'])
        if not row:
            raise ValueError(f"Investments balance row not found for: {entry['account']!r}")
        ws.update_cell(row, COL_VALUE_IDX, new_balance)
        invalidate_values(ws)
        return f"Investments · {label} · row {row} col G = £{new_balance:,.2f}"

    if domain == 'mortgage':
        # mortgage_snapshots isn't Sheet-backed like the other domains — write
        # straight to Supabase (see write_property_value). Recalculates
        # equity/equity_half against the current balance so Mortgage KPI and
        # Net Worth's House/House Equity chips pick up the change immediately.
        result = write_property_value(new_balance)
        if not result:
            raise ValueError("Property value update failed — check Supabase logs")
        return (f"Mortgage · Property Value · £{result['old_value']:,.0f} → "
                f"£{result['new_value']:,.0f} (equity £{result['equity']:,.0f})")

    raise ValueError(f"Unknown domain for BALANCE_UPDATE: {domain!r}")


def handle_savings_cashflow(entry, sh):
    """DEPOSIT / WITHDRAWAL / TRANSFER on savings — write new balance(s) + Supabase transactions."""
    ws = get_worksheet(sh, 'Savings Balance')
    typ = entry['type']
    amount = entry['amount']
    if amount is None:
        raise ValueError(f"{typ} missing Amount £")

    msg_parts = []
    col, _col_created = find_or_create_date_column(ws, today_header())

    def adjust(account_name, delta):
        row, bank, account = find_savings_row(ws, account_name)
        if not row:
            raise ValueError(f"Savings account not found in sheet: {account_name!r}")
        # Read latest non-empty balance from prior date columns to compute new
        # balance. Skip NULL/empty cells (no data), but accept literal £0 as a
        # real balance and stop scanning — a paid-off pot is meaningful data.
        rows = get_values(ws)
        headers = rows[0] if rows else []
        row_vals = rows[row - 1] if row - 1 < len(rows) else []
        prior = 0.0
        for i in range(len(headers) - 1, 2, -1):  # scan from latest col backward, skip Bank/Account/Type
            if i + 1 == col:
                continue  # skip today's column itself
            if i < len(row_vals):
                raw = (row_vals[i] or '').strip()
                if not raw:
                    continue  # cell is NULL/empty — keep scanning
                prior = parse_float(raw)
                break
        new_balance = prior + delta
        ws.update_cell(row, col, new_balance)
        # Invalidate immediately — TRANSFER calls adjust() twice (from + to) and
        # the second call's prior-balance scan + carry_forward_column afterwards
        # must see this write, not a stale pre-write snapshot.
        invalidate_values(ws)
        return new_balance, f"{bank} {account}"

    if typ in ('DEPOSIT', 'WITHDRAWAL'):
        delta = amount if typ == 'DEPOSIT' else -amount
        new_balance, label = adjust(entry['account'], delta)
        write_transaction({
            'date':         entry['event_date'] or date.today().isoformat(),
            'domain':       'savings',
            'account_name': entry['account'],
            'amount_gbp':   amount,
            'type':         typ.lower(),
            'notes':        entry['notes'] or entry['title'] or '',
            'source':       'nl_claude',
        })
        msg_parts.append(f"Savings · {label} {typ}: prior + £{delta:+,.2f} → £{new_balance:,.2f}")

    elif typ == 'TRANSFER':
        if not (entry['from_account'] and entry['to_account']):
            raise ValueError("TRANSFER missing From Account or To Account")
        new_from, lbl_from = adjust(entry['from_account'], -amount)
        new_to,   lbl_to   = adjust(entry['to_account'],   +amount)
        write_transaction({
            'date':         entry['event_date'] or date.today().isoformat(),
            'domain':       'savings',
            'account_name': f"{entry['from_account']} → {entry['to_account']}",
            'amount_gbp':   amount,
            'type':         'transfer',
            'notes':        entry['notes'] or entry['title'] or '',
            'source':       'nl_claude',
        })
        msg_parts.append(f"Savings TRANSFER £{amount:,.2f}: {lbl_from} → £{new_from:,.2f} · {lbl_to} → £{new_to:,.2f}")

    else:
        raise ValueError(f"Unsupported savings cashflow type: {typ!r}")

    # Always carry-forward — idempotent (only fills empty cells). Self-heals
    # sparse columns left by earlier runs (e.g. pre-fix Phase 16 syncs that
    # created the date column without carry-forward).
    cf_count = carry_forward_column(ws, col)
    if cf_count:
        msg_parts.append(f"carry-fwd: {cf_count} rows")

    return ' · '.join(msg_parts)


def handle_investments_action(entry, sh):
    """DEPOSIT / WITHDRAWAL / BUY / SELL on investments — delegate to log_trades helpers."""
    import log_trades

    ws_inv = get_worksheet(sh, 'Investments')
    ws_tx  = get_worksheet(sh, 'InvTransactions')

    trade = {
        'date':     entry['event_date'] or date.today().isoformat(),
        'ticker':   (entry['ticker'] or 'CASH').upper(),
        'name':     entry['ticker'] or 'Cash',
        'action':   entry['type'],
        'qty':      entry['qty'] or 0,
        'price':    entry['price'] or 0,
        'total':    entry['amount'] or (entry['qty'] or 0) * (entry['price'] or 0),
        'platform': entry['account'] or 'T212',
        'notes':    entry['notes'] or entry['title'] or '',
    }

    log_trades.append_to_inv_transactions(ws_tx, trade)

    if entry['type'] in ('DEPOSIT', 'WITHDRAWAL'):
        delta = trade['total'] if entry['type'] == 'DEPOSIT' else -trade['total']

        # Managed-fund contributions (e.g. Nutmeg) go straight into the fund, not
        # the brokerage cash pile. Bump the fund's Current Value (G) and Initially
        # Invested (H), and the Tracking Started Value baseline (I) on BOTH the fund
        # row and the MANAGED FUNDS aggregate (its I is hardcoded, not a SUM) by the
        # same delta — so the deposit is return-neutral (no phantom gain in the %).
        fund = find_managed_fund_row(ws_inv, entry['account'])
        if fund:
            frow, fname = fund
            layout = find_investment_rows(ws_inv)
            mt_row = layout.get('managed_total')

            def _val(row_1based, col_idx):
                cells = ws_inv.row_values(row_1based)
                return parse_float(cells[col_idx - 1]) if len(cells) >= col_idx and cells[col_idx - 1] else 0.0

            g, h, i_base = _val(frow, 7), _val(frow, 8), _val(frow, 9)
            updates = [
                {'range': gspread.utils.rowcol_to_a1(frow, 7), 'values': [[g + delta]]},
                {'range': gspread.utils.rowcol_to_a1(frow, 8), 'values': [[h + delta]]},
                {'range': gspread.utils.rowcol_to_a1(frow, 9), 'values': [[i_base + delta]]},
            ]
            if mt_row:
                mt_i = _val(mt_row, 9)
                updates.append({'range': gspread.utils.rowcol_to_a1(mt_row, 9), 'values': [[mt_i + delta]]})
            ws_inv.batch_update(updates, value_input_option='USER_ENTERED')
            invalidate_values(ws_inv)
            write_transaction({
                'date':         trade['date'],
                'domain':       'investments',
                'account_name': trade['platform'],
                'amount_gbp':   trade['total'],
                'type':         entry['type'].lower(),
                'notes':        trade['notes'],
                'source':       'nl_claude',
            })
            return (f"Investments {entry['type']} £{trade['total']:,.2f} into managed fund "
                    f"{fname} (value {g:,.2f} → {g + delta:,.2f}; invested + started-value bumped)")

        # Otherwise a brokerage cash top-up/withdrawal — update Cash row (col G).
        # (log_trades.update_cash only handles BUY/SELL.)
        layout = find_investment_rows(ws_inv)
        cash_row = layout['cash_row']
        cash_vals = ws_inv.row_values(cash_row)
        prior = parse_float(cash_vals[6]) if len(cash_vals) > 6 else 0.0
        ws_inv.update_cell(cash_row, COL_VALUE_IDX, prior + delta)
        invalidate_values(ws_inv)
        write_transaction({
            'date':         trade['date'],
            'domain':       'investments',
            'account_name': trade['platform'],
            'amount_gbp':   trade['total'],
            'type':         entry['type'].lower(),
            'notes':        trade['notes'],
            'source':       'nl_claude',
        })
        return f"Investments {entry['type']} £{trade['total']:,.2f} on {trade['platform']} (cash {prior:,.2f} → {prior + delta:,.2f})"

    if entry['type'] == 'BUY':
        layout = find_investment_rows(ws_inv)
        col_a = ws_inv.col_values(1)
        try:
            row_idx = col_a.index(trade['ticker']) + 1
            log_trades.update_existing_position(ws_inv, row_idx, trade)
        except ValueError:
            log_trades.add_new_position(ws_inv, trade, layout)
        log_trades.update_cash(ws_inv, trade, layout)
        log_trades.rewrite_aggregate_formulas(ws_inv)
        # log_trades writes directly to ws_inv (row inserts/deletes included) —
        # invalidate so a later entry's find_managed_fund_row/get_values sees it.
        invalidate_values(ws_inv)
        return f"Investments BUY {trade['qty']} {trade['ticker']} @ £{trade['price']:.4f} on {trade['platform']}"

    if entry['type'] == 'SELL':
        layout = find_investment_rows(ws_inv)
        col_a = ws_inv.col_values(1)
        try:
            row_idx = col_a.index(trade['ticker']) + 1
        except ValueError:
            raise ValueError(f"SELL of {trade['ticker']} but no holding row found")
        remaining = log_trades.update_existing_position(ws_inv, row_idx, trade)
        if remaining <= 0:
            log_trades.remove_position_row(ws_inv, trade['ticker'])
        log_trades.update_cash(ws_inv, trade, layout)
        log_trades.rewrite_aggregate_formulas(ws_inv)
        invalidate_values(ws_inv)
        return f"Investments SELL {trade['qty']} {trade['ticker']} @ £{trade['price']:.4f} on {trade['platform']}"

    raise ValueError(f"Unsupported investments action: {entry['type']!r}")


# ── Orchestrator ─────────────────────────────────────────────────────────────

def process_entry(entry, sh):
    """Route one entry to the right handler. Returns a 1-line result string on success."""
    typ    = entry['type']
    domain = entry['domain']

    if typ == 'BALANCE_UPDATE':
        return handle_balance_update(entry, sh)

    if domain == 'savings' and typ in ('DEPOSIT', 'WITHDRAWAL', 'TRANSFER'):
        return handle_savings_cashflow(entry, sh)

    if domain == 'investments' and typ in ('DEPOSIT', 'WITHDRAWAL', 'BUY', 'SELL'):
        return handle_investments_action(entry, sh)

    raise ValueError(f"Unsupported (Type, Domain) combination: ({typ}, {domain})")



def send_telegram(summary):
    token   = os.getenv('TELEGRAM_BOT_TOKEN')
    chat_id = os.getenv('TELEGRAM_CHAT_ID')
    if not token or not chat_id:
        return
    import requests
    requests.post(
        f'https://api.telegram.org/bot{token}/sendMessage',
        json={'chat_id': chat_id, 'text': summary, 'parse_mode': 'HTML'},
        timeout=10,
    )


def _entry_summary_line(entry):
    """One-line description of a synced entry for the Telegram digest."""
    typ    = entry['type']
    acct   = entry['account'] or f"{entry['from_account']} → {entry['to_account']}"
    if typ == 'BALANCE_UPDATE':
        return f"• {acct} → £{entry['new_balance']:,.0f}"
    if typ in ('DEPOSIT', 'WITHDRAWAL'):
        sign = '+' if typ == 'DEPOSIT' else '−'
        return f"• {acct} · {typ.title()} {sign}£{entry['amount']:,.0f}"
    if typ == 'TRANSFER':
        return f"• {entry['from_account']} → {entry['to_account']} · £{entry['amount']:,.0f}"
    if typ in ('BUY', 'SELL'):
        return f"• {typ} {entry['qty']} {entry['ticker']} @ £{entry['price']:.2f} on {acct}"
    return f"• {typ} · {acct}"


def build_queue_section(successes, failures):
    """The Notion-queue portion of the Telegram digest (no header), shared by the
    standalone message and the combined bot_sync message that snapshot_worker sends."""
    lines = []
    if successes:
        lines.append(f"<b>📥 Recorded ({len(successes)}):</b>")
        for entry in successes:
            lines.append(_entry_summary_line(entry))
    if failures:
        if lines:
            lines.append("")
        lines.append(f"<b>⚠️ Failed ({len(failures)}):</b>")
        for entry, err in failures:
            label = entry['account'] or entry['from_account'] or entry['type']
            lines.append(f"• {label} — {err[:100]}")
    if not successes and not failures:
        lines.append("No pending entries in Notion queue.")
    return '\n'.join(lines)


def build_telegram_summary(successes, failures):
    """Standalone sync_worker message (when not deferring to snapshot_worker)."""
    today = date.today().isoformat()
    return f"<b>✅ Sync complete</b> · {today}\n\n" + build_queue_section(successes, failures)


def emit_sync_summary(successes, failures):
    """Send the Notion-queue summary now, OR — when DEFER_SYNC_TELEGRAM is set
    (the bot_sync flow) — write just the queue section to a temp file so
    snapshot_worker can fold it into ONE combined message instead of two.

    HF-B: a silent run (no entries recorded or failed) produces NO Telegram
    message. In the bot_sync flow the only thing that changes the sheet is
    draining the Notion queue — no price refresh runs there — so "no entries
    processed" means "nothing changed". We signal that to snapshot_worker by
    NOT writing the handoff file, which suppresses the combined message too.
    """
    processed = bool(successes or failures)

    if os.getenv('DEFER_SYNC_TELEGRAM'):
        # Clear any stale handoff first so an empty run can't reuse a prior file.
        try:
            os.remove(SYNC_SUMMARY_FILE)
        except OSError:
            pass
        if not processed:
            return  # silent run — snapshot_worker skips the combined message
        try:
            with open(SYNC_SUMMARY_FILE, 'w') as f:
                f.write(build_queue_section(successes, failures))
        except OSError as e:
            print(f"  ⚠ could not write sync summary file: {e}")
        return

    if not processed:
        return  # standalone silent run — no message
    send_telegram(build_telegram_summary(successes, failures))


def main():
    parser = argparse.ArgumentParser(description='Phase 16 sync_worker — Notion Financial Updates → Sheets + Supabase')
    parser.add_argument('--dry-run', action='store_true', help='Log planned actions, no writes')
    parser.add_argument('--id', help='Sync one specific Notion page by id')
    args = parser.parse_args()

    print(f"=== sync_worker — {date.today()} ===")

    headers = notion_headers()

    if args.id:
        # Fetch one row directly
        import requests
        resp = requests.get(
            f'https://api.notion.com/v1/pages/{args.id}',
            headers=headers, timeout=30,
        )
        if resp.status_code != 200:
            print(f"  ⚠ Could not fetch page {args.id}: {resp.text[:200]}")
            sys.exit(1)
        pages = [resp.json()]
    else:
        pages = fetch_unsynced_financial_updates(headers)

    sh = open_sheet()

    if not pages:
        print("  No unsynced rows found.")
        # Still self-heal — earlier broken runs may have left the latest
        # date column sparse, and without this every Sync click would do nothing.
        print("\nSelf-healing latest date columns...")
        self_heal_sparse_columns(sh)
        emit_sync_summary([], [])
        return

    print(f"  {len(pages)} unsynced row(s) to process")

    successes  = []
    failures   = []

    for page in pages:
        entry = extract_financial_update(page)
        label = f"[{entry['type']} · {entry['domain']} · {entry['account'] or entry['from_account']}]"

        if args.dry_run:
            print(f"\n  DRY-RUN {label}: would process {entry['title']}")
            continue

        try:
            result_msg = process_entry(entry, sh)
            print(f"\n  ✓ {label} {result_msg}")
            mark_sheets_written(entry['id'], headers)
            successes.append(entry)
        except Exception as e:
            err = f"{type(e).__name__}: {e}"
            print(f"\n  ✗ {label} {err}")
            mark_row_failed(entry['id'], err, headers)
            failures.append((entry, err))

    if args.dry_run:
        print("\nDry run complete — no writes performed.")
        return

    # Mark all successful entries as fully synced
    for entry in successes:
        mark_row_synced(entry['id'], headers)

    # Self-heal latest date columns — picks up any rows that ended up sparse
    # (e.g. an account explicitly updated today via Notion, but the column
    # was created on an earlier broken run).
    print("\nSelf-healing latest date columns...")
    self_heal_sparse_columns(sh)

    # Notion-queue digest — sent now standalone, or deferred into snapshot_worker's
    # single combined bot_sync message.
    emit_sync_summary(successes, failures)

    print(f"\nDone — {len(successes)} synced, {len(failures)} failed.")


if __name__ == '__main__':
    main()
