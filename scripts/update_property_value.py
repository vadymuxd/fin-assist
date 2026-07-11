#!/usr/bin/env python3
"""
update_property_value.py — manual house valuation update.

Property Value has no live feed (no Land Registry/Zoopla integration — see
Plan house-val.2) so it's a manual entry, same idea as a savings/pension
BALANCE_UPDATE: record a new value, dated today, and every downstream figure
(Mortgage KPI equity/LTV, Net Worth House/House Equity chips) recomputes from
it because they all read the latest mortgage_snapshots row.

Upserts today's row with the new property_value (recalculating equity and
equity_half against the current balance) so mortgage_snapshot.py's next
monthly run carries the new value forward instead of resetting to the old one.

Run:
  python3 scripts/update_property_value.py 650000
"""

import os
import sys
from datetime import date, datetime, timezone
from decimal import Decimal
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: python3 scripts/update_property_value.py <new_property_value>")
        sys.exit(1)

    try:
        new_value = Decimal(sys.argv[1])
    except Exception:
        print(f"ERROR: {sys.argv[1]!r} is not a valid number.")
        sys.exit(1)

    url = os.getenv('SUPABASE_URL', '')
    key = os.getenv('SUPABASE_SERVICE_ROLE_KEY', '')
    if not url or not key:
        print("ERROR: SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY not set.")
        sys.exit(1)

    client = create_client(url, key)
    result = client.table('mortgage_snapshots') \
        .select('date, balance, property_value, monthly_payment, rate, lender, deal_expires, deal_term_years') \
        .order('date', desc=True).limit(1).execute()

    if not result.data:
        print("ERROR: no existing mortgage_snapshots rows — run mortgage_snapshot.py --seed first.")
        sys.exit(1)

    latest = result.data[0]
    balance = Decimal(str(latest['balance']))
    old_value = Decimal(str(latest['property_value']))
    equity = new_value - balance

    today = date.today().isoformat()
    row = {
        'date':            today,
        'balance':         float(balance),
        'property_value':  float(new_value),
        'equity':          float(equity),
        'equity_half':     float((equity / 2).quantize(Decimal('0.01'))),
        'monthly_payment': latest['monthly_payment'],
        'rate':            latest['rate'],
        'lender':          latest['lender'],
        'deal_expires':    latest['deal_expires'],
        'deal_term_years': latest['deal_term_years'],
        'updated_at':      datetime.now(timezone.utc).isoformat(),
    }

    client.table('mortgage_snapshots').upsert(row, on_conflict='date').execute()
    print(f"  Property Value: £{old_value:,.2f} → £{new_value:,.2f}  ({today})")
    print(f"  Equity: £{equity:,.2f}  (half: £{(equity / 2):,.2f})")


if __name__ == '__main__':
    main()
