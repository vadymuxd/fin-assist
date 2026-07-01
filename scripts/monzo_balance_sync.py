#!/usr/bin/env python3
"""
monzo_balance_sync.py — feature.1

Runs between monzo_sync.py and sync_worker.py in bot_sync.yml / daily_monitor.yml.

Scans monzo_transactions rows not yet considered for balance-recognition
(balance_processed_at IS NULL — see migration 0023), reuses monzo_sync's
classify() to recognise savings-pot transfers and investment-platform
deposits/withdrawals, resolves the pot/counterparty name to a tracked Savings
Balance sheet row using the SAME matching function sync_worker.py uses
(find_savings_row), and — for every confident match — creates a CONFIRMED
Financial Updates DB entry so sync_worker.py (which runs immediately after in
the same workflow) writes it to Sheets + Supabase + Notion exactly like a
manually-logged entry.

Investment-platform deposits/withdrawals are passed through with the raw
Monzo counterparty name — sync_worker's handle_investments_action already
routes DEPOSIT/WITHDRAWAL to the matching managed fund (find_managed_fund_row)
or, failing that, the brokerage cash row, so no pre-resolution is needed there.

Every scanned row (matched, unresolved, or irrelevant) is stamped
balance_processed_at — except rows where Notion page creation itself failed,
which are left unprocessed so the next run retries them. This is the guard
against double-counting and against re-scanning history.

CLI:
  --dry-run   Log what would be created; no Notion writes, no cursor stamp
"""

import argparse
import logging
from datetime import date as _date

from dotenv import load_dotenv

from monzo_sync import classify
from sync_worker import find_savings_row, open_sheet
from lib.notion_db import create_financial_update, notion_headers
from lib.supabase_sink import get_unprocessed_monzo_transactions, mark_monzo_transactions_processed

load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
logger = logging.getLogger(__name__)

SAVINGS_CATEGORIES = {'savings_pot_transfer', 'pot_transfer'}


def resolve_savings_account(row: dict, ws_savings) -> str | None:
    """Resolve a Monzo pot transfer to a 'Bank Account' label matching a
    Savings Balance sheet row, or None if it doesn't map to a tracked pot."""
    search = f"{row.get('name') or ''} {row.get('pot_name') or ''}".strip()
    r, bank, account = find_savings_row(ws_savings, search)
    if not r:
        return None
    return f'{bank} {account}'.strip()


def build_entry(row: dict, category: str, account_label: str, domain: str) -> dict:
    amount = float(row.get('amount') or 0)
    typ = 'DEPOSIT' if amount < 0 else 'WITHDRAWAL'
    abs_amount = abs(amount)
    sign = '+' if typ == 'DEPOSIT' else '-'
    return {
        'title':      f'{account_label} · {sign}£{abs_amount:,.2f} (Monzo auto)',
        'type':       typ,
        'domain':     domain,
        'account':    account_label,
        'amount':     abs_amount,
        'event_date': row.get('date'),
        'notes': (
            f"Monzo auto-sync: {row.get('name') or ''} {row.get('pot_name') or ''} "
            f"(tx {row.get('transaction_id')}, {category})"
        ).strip(),
        'source': 'monzo_auto',
    }


def main() -> None:
    parser = argparse.ArgumentParser(description='feature.1 — Monzo auto balance recognition')
    parser.add_argument('--dry-run', action='store_true', help='No Notion writes, no cursor stamp')
    args = parser.parse_args()

    print(f"=== monzo_balance_sync — {_date.today()} ===")

    rows = get_unprocessed_monzo_transactions()
    if not rows:
        print("  No unprocessed Monzo transactions.")
        return

    print(f"  {len(rows)} unprocessed row(s) to scan")

    sh = open_sheet()
    ws_savings = sh.worksheet('Savings Balance')
    headers = notion_headers()

    created = []
    processed_ids = []

    for row in rows:
        amount = float(row.get('amount') or 0)
        label_prefix = f"[{row['account_type']} row {row['row_index']}]"

        if not amount:
            processed_ids.append(row['id'])
            continue

        category = classify(row)
        entry = None

        if category in SAVINGS_CATEGORIES:
            account_label = resolve_savings_account(row, ws_savings)
            if account_label:
                entry = build_entry(row, category, account_label, 'savings')

        elif category == 'investment_deposit':
            account_label = (row.get('name') or 'Investments').strip()
            entry = build_entry(row, category, account_label, 'investments')

        if not entry:
            processed_ids.append(row['id'])
            continue

        summary = f"{label_prefix} {entry['type']} {entry['domain']} · {entry['account']} · £{entry['amount']:,.2f}"

        if args.dry_run:
            print(f"  DRY-RUN would create: {summary}")
            continue

        page_id = create_financial_update(entry, headers=headers)
        if page_id:
            print(f"  ✓ created {summary}")
            created.append(entry)
            processed_ids.append(row['id'])
        else:
            print(f"  ✗ Notion create failed — will retry next run: {summary}")

    if not args.dry_run and processed_ids:
        mark_monzo_transactions_processed(processed_ids)

    print(f"\nDone — {len(created)} Financial Updates entries created, {len(rows)} row(s) scanned.")
    if args.dry_run:
        print("(dry-run — no Notion writes, no cursor stamp — rows remain unprocessed)")


if __name__ == '__main__':
    main()
