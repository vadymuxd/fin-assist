#!/usr/bin/env python3
"""
One-off cleanup: delete holdings_alerts rows where suggested_action IS NULL.
These were written by the old holdings_monitor.py --bot / --auto runs before
alert_dispatcher.py took over. The new pipeline always populates suggested_action.

Usage:
  python3 scripts/cleanup_null_alerts.py            # dry-run
  python3 scripts/cleanup_null_alerts.py --apply    # actually delete
"""

import os
import sys
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()
DRY_RUN = '--apply' not in sys.argv


def main():
    sb = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_SERVICE_ROLE_KEY'))
    print(f"Mode: {'DRY-RUN' if DRY_RUN else 'APPLY'}")

    resp = (
        sb.table('holdings_alerts')
        .select('id, ticker, alert_level, run_time')
        .is_('suggested_action', 'null')
        .limit(2000)
        .execute()
    )
    rows = resp.data or []
    print(f"Rows with null suggested_action: {len(rows)}")
    for r in rows:
        print(f"  [{r['alert_level']}] {r['ticker']} @ {r['run_time']}")

    if not rows:
        print("Nothing to delete.")
        return

    if DRY_RUN:
        print("\nDRY-RUN: pass --apply to actually delete")
        return

    ids = [r['id'] for r in rows]
    deleted = 0
    for i in range(0, len(ids), 100):
        sb.table('holdings_alerts').delete().in_('id', ids[i:i + 100]).execute()
        deleted += len(ids[i:i + 100])
    print(f"Deleted {deleted} rows")


if __name__ == '__main__':
    main()
