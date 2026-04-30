#!/usr/bin/env python3
"""
mortgage_snapshot.py — Monthly mortgage balance snapshot.

Calculates the mortgage balance for the current month using amortisation
and upserts to Supabase mortgage_snapshots. Run with --seed to backfill
the full history from October 2024 using the confirmed April 2026 balance
as the anchor point.

Run:
  python3 scripts/mortgage_snapshot.py           # add this month's row
  python3 scripts/mortgage_snapshot.py --seed    # seed full history
"""

import os
import sys
import requests
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

SUPABASE_URL    = os.getenv('SUPABASE_URL', '')
SUPABASE_KEY    = os.getenv('SUPABASE_SERVICE_ROLE_KEY', '')
REVALIDATE_URL  = os.getenv('APP_REVALIDATE_URL', '')
REVALIDATE_SEC  = os.getenv('APP_REVALIDATE_SECRET', '')

# ── Mortgage constants ────────────────────────────────────────────────────────
ANNUAL_RATE      = Decimal('0.0526')
MONTHLY_RATE     = ANNUAL_RATE / 12
MONTHLY_PAYMENT  = Decimal('3072.00')
PROPERTY_VALUE   = Decimal('660000.00')
LENDER           = 'Co-operative Bank'
START_DATE       = date(2024, 10, 1)   # mortgage start; no payment on this date

# Confirmed by bank statement as of 1 Apr 2026 (after April payment)
CONFIRMED_DATE    = date(2026, 4, 1)
CONFIRMED_BALANCE = Decimal('552371.48')


def next_month(d: date) -> date:
    if d.month == 12:
        return date(d.year + 1, 1, 1)
    return date(d.year, d.month + 1, 1)


def prev_month(d: date) -> date:
    if d.month == 1:
        return date(d.year - 1, 12, 1)
    return date(d.year, d.month - 1, 1)


def calc_next_balance(balance: Decimal) -> Decimal:
    """Balance after one monthly payment."""
    interest  = (balance * MONTHLY_RATE).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    principal = MONTHLY_PAYMENT - interest
    return (balance - principal).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def calc_prev_balance(balance: Decimal) -> Decimal:
    """Reverse one month: what was the balance before this payment?"""
    # B_prev * (1+r) - M = B_current  =>  B_prev = (B_current + M) / (1+r)
    return ((balance + MONTHLY_PAYMENT) / (1 + MONTHLY_RATE)).quantize(
        Decimal('0.01'), rounding=ROUND_HALF_UP
    )


def make_row(d: date, balance: Decimal) -> dict:
    equity = PROPERTY_VALUE - balance
    return {
        'date':            d.isoformat(),
        'balance':         float(balance),
        'property_value':  float(PROPERTY_VALUE),
        'equity':          float(equity),
        'equity_half':     float((equity / 2).quantize(Decimal('0.01'))),
        'monthly_payment': float(MONTHLY_PAYMENT),
        'rate':            float(ANNUAL_RATE),
        'lender':          LENDER,
    }


def build_history() -> list[dict]:
    """Generate all monthly rows: backwards from CONFIRMED_DATE to START_DATE,
    then forwards from CONFIRMED_DATE to the current month."""
    today = date.today()
    rows: dict[str, dict] = {}

    # ── Backwards from confirmed date to start ────────────────────────────────
    balance = CONFIRMED_BALANCE
    d = CONFIRMED_DATE
    while d >= START_DATE:
        rows[d.isoformat()] = make_row(d, balance)
        if d == START_DATE:
            break
        balance = calc_prev_balance(balance)
        d = prev_month(d)

    # ── Forwards from confirmed date to today ─────────────────────────────────
    balance = CONFIRMED_BALANCE
    d = next_month(CONFIRMED_DATE)
    this_month = date(today.year, today.month, 1)
    while d <= this_month:
        balance = calc_next_balance(balance)
        rows[d.isoformat()] = make_row(d, balance)
        d = next_month(d)

    return sorted(rows.values(), key=lambda r: r['date'])


def upsert(client, rows: list[dict]) -> None:
    client.table('mortgage_snapshots').upsert(rows, on_conflict='date').execute()


def trigger_revalidate() -> None:
    if not REVALIDATE_URL or not REVALIDATE_SEC:
        return
    try:
        requests.post(REVALIDATE_URL, json={'secret': REVALIDATE_SEC}, timeout=10)
    except Exception as e:
        print(f"  Revalidate error: {e}")


def main() -> None:
    seed = '--seed' in sys.argv
    client = create_client(SUPABASE_URL, SUPABASE_KEY)

    if seed:
        print('=== Mortgage Snapshot — SEED ===')
        rows = build_history()
        print(f'  Inserting {len(rows)} rows ({rows[0]["date"]} → {rows[-1]["date"]})')
        upsert(client, rows)
        for r in rows:
            print(f'  ✓ {r["date"]}  balance=£{r["balance"]:,.2f}  equity=£{r["equity"]:,.2f}')
        trigger_revalidate()
        print('Done.')
        return

    # ── Normal monthly run ────────────────────────────────────────────────────
    today = date.today()
    target = date(today.year, today.month, 1)
    print(f'=== Mortgage Snapshot — {target} ===')

    result = client.table('mortgage_snapshots').select('date, balance') \
        .order('date', desc=True).limit(1).execute()

    if not result.data:
        print('  No existing data — run with --seed first.')
        sys.exit(1)

    latest_date = date.fromisoformat(result.data[0]['date'])
    if latest_date >= target:
        print(f'  Already have snapshot for {target} — nothing to do.')
        return

    # Step forward month by month from latest to target
    balance = Decimal(str(result.data[0]['balance']))
    d = next_month(latest_date)
    new_rows = []
    while d <= target:
        balance = calc_next_balance(balance)
        new_rows.append(make_row(d, balance))
        d = next_month(d)

    upsert(client, new_rows)
    for r in new_rows:
        print(f'  ✓ {r["date"]}  balance=£{r["balance"]:,.2f}  equity=£{r["equity"]:,.2f}')

    trigger_revalidate()
    print('Done.')


if __name__ == '__main__':
    main()
