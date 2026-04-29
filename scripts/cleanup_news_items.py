#!/usr/bin/env python3
"""
One-off cleanup: delete per_holding news_items that are duplicates by
normalized title (keeping the oldest entry per title) and delete recent
per_holding rows that were bulk-inserted by the previous version of
news_fetcher.py / holdings_monitor.py.

Run once after deploying the news_fetcher.py rewrite.

Usage:
  python3 scripts/cleanup_news_items.py            # dry-run (default)
  python3 scripts/cleanup_news_items.py --apply    # actually delete
"""

import os
import sys
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

DRY_RUN = '--apply' not in sys.argv


def normalize_title(title):
    if not title:
        return ''
    t = title.lower().strip()
    for ch in '"\'’“”():.,!?-—–|':
        t = t.replace(ch, ' ')
    return ' '.join(t.split())


def main():
    url = os.getenv('SUPABASE_URL', '')
    key = os.getenv('SUPABASE_SERVICE_ROLE_KEY', '')
    if not url or not key:
        print('SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY not set')
        sys.exit(1)

    sb = create_client(url, key)
    print(f"Connected. Mode: {'DRY-RUN' if DRY_RUN else 'APPLY'}")

    # Fetch all per_holding items from the last 30 days
    cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    resp = (
        sb.table('news_items')
        .select('id, title, published_at, tickers, source')
        .eq('source_type', 'per_holding')
        .gte('published_at', cutoff)
        .order('published_at', desc=False)
        .limit(5000)
        .execute()
    )
    rows = resp.data or []
    print(f"Fetched {len(rows)} per_holding rows from last 30d")

    # Group by normalized title — keep the FIRST (oldest) per title, mark rest for delete
    seen = {}
    to_delete = []
    for r in rows:
        norm = normalize_title(r.get('title', ''))
        if not norm:
            continue
        if norm in seen:
            to_delete.append(r['id'])
        else:
            seen[norm] = r['id']

    print(f"Unique titles: {len(seen)}")
    print(f"Duplicate rows to delete: {len(to_delete)}")

    if to_delete:
        sample = to_delete[:5]
        print(f"  Sample IDs: {sample}")
        if not DRY_RUN:
            # Delete in batches of 100 to avoid URL length issues
            deleted = 0
            for i in range(0, len(to_delete), 100):
                batch = to_delete[i:i + 100]
                sb.table('news_items').delete().in_('id', batch).execute()
                deleted += len(batch)
                print(f"  Deleted {deleted}/{len(to_delete)}")
            print(f"Done — deleted {deleted} duplicate rows")
        else:
            print("DRY-RUN: pass --apply to actually delete")
    else:
        print("No duplicates found — nothing to do")


if __name__ == '__main__':
    main()
