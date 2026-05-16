#!/usr/bin/env python3
"""
fix_lisa_start.py

One-off: corrects the historical backfill error where Lisa's starting
portfolio value was set to £14,000 instead of £14,044.

Updates all portfolio_snapshots rows where lisa_total = 14000.0
(these are the flat-line historical rows set by backfill_lisa_total.py).

Run once from repo root:
    python scripts/fix_lisa_start.py
"""

import os
import sys
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

OLD_VALUE = 14000.0
NEW_VALUE = 14044.0


def main():
    url = os.getenv('SUPABASE_URL', '')
    key = os.getenv('SUPABASE_SERVICE_ROLE_KEY', '')
    if not url or not key:
        print("ERROR: SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY not set.")
        sys.exit(1)

    client = create_client(url, key)

    # Find rows with the old backfilled value
    resp = (
        client.table('portfolio_snapshots')
        .select('date, lisa_total')
        .eq('lisa_total', OLD_VALUE)
        .order('date')
        .execute()
    )
    rows = resp.data or []

    if not rows:
        print(f"No rows found with lisa_total = {OLD_VALUE} — nothing to update.")
        return

    dates = [r['date'] for r in rows]
    print(f"Found {len(dates)} rows with lisa_total = £{OLD_VALUE:,.2f}:")
    print(f"  {dates[0]} → {dates[-1]}")
    print(f"\nUpdating to £{NEW_VALUE:,.2f}...")

    updates = [{'date': d, 'lisa_total': NEW_VALUE} for d in dates]
    client.table('portfolio_snapshots').upsert(updates, on_conflict='date').execute()

    print(f"Done. {len(dates)} rows updated: lisa_total £{OLD_VALUE:,.0f} → £{NEW_VALUE:,.0f}")
    print("\nThe web app baseline will now correctly show Lisa's portfolio starting at £14,044.")


if __name__ == '__main__':
    main()
