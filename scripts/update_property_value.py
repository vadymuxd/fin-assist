#!/usr/bin/env python3
"""
update_property_value.py — manual house valuation update (CLI wrapper).

Property Value has no live feed (no Land Registry/Zoopla integration — see
Plan house-val.2), so it's a manual entry — the same idea as a savings/
pension BALANCE_UPDATE. Every downstream figure (Mortgage KPI equity/LTV,
Net Worth House/House Equity chips) recomputes automatically because they
all read the latest mortgage_snapshots row.

This is also reachable via the normal Notion Financial Updates flow — see
sync_worker.py's handle_balance_update, domain='mortgage'. Use this script
for a one-off manual run outside that pipeline.

Run:
  python3 scripts/update_property_value.py 650000
"""

import sys
from dotenv import load_dotenv
from lib.supabase_sink import write_property_value

load_dotenv()


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: python3 scripts/update_property_value.py <new_property_value>")
        sys.exit(1)

    try:
        new_value = float(sys.argv[1])
    except ValueError:
        print(f"ERROR: {sys.argv[1]!r} is not a valid number.")
        sys.exit(1)

    result = write_property_value(new_value)
    if not result:
        print("ERROR: update failed — check SUPABASE_URL/SUPABASE_SERVICE_ROLE_KEY and logs.")
        sys.exit(1)

    print(f"  Property Value: £{result['old_value']:,.2f} → £{result['new_value']:,.2f}")
    print(f"  Equity: £{result['equity']:,.2f}  (half: £{(result['equity'] / 2):,.2f})")


if __name__ == '__main__':
    main()
