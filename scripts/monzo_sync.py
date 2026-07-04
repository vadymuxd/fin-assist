#!/usr/bin/env python3
"""
monzo_sync.py — Phase 18, monzo.4–7

Cursor-based reader that pulls only new Monzo rows each run, classifies each
transaction, upserts into monzo_transactions, and writes Supabase transactions
for balance-affecting events (investment deposits).

Reads both tabs:
  'Personal Account Transactions' → account_type='personal'
  'Joint Account Transactions'    → account_type='joint'

CLI:
  (default)     Pull delta only (from MAX row_index in Supabase)
  --backfill    Ignore cursor; sync from row 2 (full history)
  --dry-run     No Supabase writes; log what would happen
  --account     personal | joint | all  (default: all)
"""

import os
import sys
import argparse
import logging
import tempfile
from datetime import datetime, timezone

import requests as req
from dotenv import load_dotenv
from google.oauth2.service_account import Credentials
import google.auth.transport.requests

from lib.supabase_sink import (
    write_monzo_transactions,
    get_monzo_cursor,
    force_revalidate,
)

load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
logger = logging.getLogger(__name__)

MONZO_SHEET_ID = '1Hot1ukOadT5AClVV6lcw9jCamYFgPLH26WDCyq6qg2g'
SA_FILE = os.getenv('GOOGLE_APPLICATION_CREDENTIALS', 'config/service_account.json')
SCOPES  = ['https://www.googleapis.com/auth/spreadsheets.readonly']

TABS = {
    'personal': 'Personal Account Transactions',
    'joint':    'Joint Account Transactions',
}

# Handoff file read by snapshot_worker.py, which sends the ONE combined
# "Sync complete" Telegram message for the whole bot_sync/daily_monitor
# pipeline. Only written when there's something to report — see main().
MONZO_SYNC_SUMMARY_FILE = os.path.join(tempfile.gettempdir(), 'fin_assist_monzo_sync_summary.txt')

# Known investment platform name fragments (case-insensitive, exact-phrase only)
INVESTMENT_PLATFORMS = [
    'trading 212', 'freetrade', 'vanguard', 'hargreaves lansdown',
    'aj bell', 'nutmeg', 'moneybox',
]

# Savings-related keywords (checked in name + pot_name)
SAVINGS_KEYWORDS = [
    'savings', 'save', 'emergency', 'house fund', 'flexible fund',
    'rainy day', 'holiday', 'holiday fund', 'help to buy', 'lisa',
]


# ─── Auth ────────────────────────────────────────────────────────────────────

def _get_headers() -> dict:
    creds = Credentials.from_service_account_file(SA_FILE, scopes=SCOPES)
    creds.refresh(google.auth.transport.requests.Request())
    return {'Authorization': f'Bearer {creds.token}'}


# ─── Sheets helpers ──────────────────────────────────────────────────────────

def _get_row_count(headers: dict, tab_name: str) -> int:
    url = (
        f'https://sheets.googleapis.com/v4/spreadsheets/{MONZO_SHEET_ID}'
        '?fields=sheets.properties'
    )
    r = req.get(url, headers=headers)
    r.raise_for_status()
    for s in r.json().get('sheets', []):
        props = s.get('properties', {})
        if props.get('title') == tab_name:
            return props['gridProperties']['rowCount']
    raise ValueError(f'Tab not found in sheet: {tab_name!r}')


def _fetch_rows(headers: dict, tab_name: str, start: int, end: int) -> list:
    range_str = f"'{tab_name}'!A{start}:Q{end}"
    url = (
        f'https://sheets.googleapis.com/v4/spreadsheets/{MONZO_SHEET_ID}'
        f'/values/{req.utils.quote(range_str, safe="")}'
    )
    r = req.get(url, headers=headers)
    r.raise_for_status()
    return r.json().get('values', [])


# ─── Row parsing ─────────────────────────────────────────────────────────────

def _parse_date(s: str) -> str | None:
    for fmt in ('%d/%m/%Y', '%Y-%m-%d'):
        try:
            return datetime.strptime(s, fmt).strftime('%Y-%m-%d')
        except ValueError:
            pass
    return None


def _parse_num(s: str) -> float | None:
    try:
        return float(s.replace(',', ''))
    except (ValueError, TypeError):
        return None


def _parse_row(raw: list, row_index: int, account_type: str) -> dict | None:
    """Map a raw Sheets row to a monzo_transactions dict. Returns None for empty/header rows."""
    if not raw:
        return None
    tx_id = raw[0].strip() if raw[0] else ''
    if not tx_id or tx_id == 'Transaction ID':
        return None

    def g(i): return raw[i].strip() if i < len(raw) and raw[i] else None

    return {
        'transaction_id': tx_id,
        'account_type':   account_type,
        'row_index':      row_index,
        'date':           _parse_date(g(1) or ''),
        'time':           g(2),
        'type':           g(3),
        'name':           g(4),
        'emoji':          g(5),
        'category':       g(6),
        'amount':         _parse_num(g(7) or ''),
        'currency':       g(8),
        'local_amount':   _parse_num(g(9) or ''),
        'local_currency': g(10),
        'notes':          g(11),
        'address':        g(12),
        'receipt':        g(13),
        'description':    g(14),
        'category_split': g(15),
        'pot_name':       g(16),
        'synced_at':      datetime.now(timezone.utc).isoformat(),
    }


# ─── Classifier (monzo.6) ────────────────────────────────────────────────────

def classify(row: dict) -> str:
    tx_type  = (row.get('type')     or '').lower()
    name     = (row.get('name')     or '').lower()
    category = (row.get('category') or '').lower()
    pot_name = (row.get('pot_name') or '').lower()
    amount   = row.get('amount') or 0

    if tx_type == 'pot transfer':
        combined = f'{name} {pot_name}'
        if any(kw in combined for kw in SAVINGS_KEYWORDS) or category == 'savings':
            return 'savings_pot_transfer'
        return 'pot_transfer'

    if any(p in name for p in INVESTMENT_PLATFORMS):
        return 'investment_deposit'

    if category == 'savings' and amount < 0:
        return 'savings_deposit'

    if amount > 0:
        return 'income'

    return 'general_expense'


# ─── Per-account sync ────────────────────────────────────────────────────────
# Balance writers (monzo.7) — superseded by monzo_balance_sync.py (feature.1),
# which runs after this script in bot_sync.yml / daily_monitor.yml and routes
# recognised savings-pot transfers + investment deposits through the Notion
# Financial Updates DB → sync_worker.py pipeline instead of writing Supabase
# `transactions` directly.

def sync_account(
    headers: dict,
    account_type: str,
    tab_name: str,
    cursor: int,
    dry_run: bool,
) -> dict:
    row_count = _get_row_count(headers, tab_name)
    start_row = max(cursor + 1, 2)  # row 1 is the header
    logger.info(f'[{account_type}] rowCount={row_count} cursor={cursor} → fetching {start_row}:{row_count}')

    if start_row > row_count:
        logger.info(f'[{account_type}] Nothing new')
        return {'fetched': 0, 'upserted': 0, 'classified': {}}

    raw_rows = _fetch_rows(headers, tab_name, start_row, row_count)
    logger.info(f'[{account_type}] API returned {len(raw_rows)} rows')

    parsed = []
    for i, raw in enumerate(raw_rows):
        record = _parse_row(raw, start_row + i, account_type)
        if record:
            parsed.append(record)

    logger.info(f'[{account_type}] {len(parsed)} valid rows after filtering')

    class_counts: dict = {}
    for r in parsed:
        label = classify(r)
        class_counts[label] = class_counts.get(label, 0) + 1

    if not dry_run and parsed:
        write_monzo_transactions(parsed)

    return {'fetched': len(raw_rows), 'upserted': len(parsed), 'classified': class_counts}


# ─── Main ────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--backfill', action='store_true',
                        help='Sync all rows from row 2 (full history)')
    parser.add_argument('--dry-run',  action='store_true',
                        help='No Supabase writes')
    parser.add_argument('--account',  default='all',
                        choices=['personal', 'joint', 'all'])
    args = parser.parse_args()

    if not os.path.exists(SA_FILE):
        logger.error(f'Service account not found: {SA_FILE}')
        sys.exit(1)

    headers  = _get_headers()
    accounts = list(TABS.keys()) if args.account == 'all' else [args.account]
    all_stats: dict = {}

    for acct in accounts:
        tab    = TABS[acct]
        cursor = 0 if args.backfill else get_monzo_cursor(acct)
        stats  = sync_account(headers, acct, tab, cursor, args.dry_run)
        all_stats[acct] = stats
        logger.info(f'[{acct}] {stats}')

    if not args.dry_run:
        force_revalidate()

    lines     = []
    any_new   = False
    for acct, stats in all_stats.items():
        n = stats['upserted']
        if n == 0:
            continue
        any_new = True
        cats = ', '.join(f'{v} {k}' for k, v in stats['classified'].items())
        lines.append(f'{acct}: +{n} rows ({cats})')
    summary = '\n'.join(lines) if lines else 'No new Monzo rows.'
    logger.info(summary)

    # Hand off to snapshot_worker.py, which sends the one combined Telegram
    # message for the whole run — only when there's actually something new,
    # so a routine "nothing happened" sync doesn't add noise on its own.
    if not args.dry_run:
        try:
            os.remove(MONZO_SYNC_SUMMARY_FILE)
        except OSError:
            pass
        if any_new:
            with open(MONZO_SYNC_SUMMARY_FILE, 'w') as f:
                f.write('\n'.join(lines))


if __name__ == '__main__':
    main()
