#!/usr/bin/env python3
"""
One-off cleanup: delete per_holding news_items where the assigned ticker
has no obvious match in the title. yfinance Ticker.news returns "related"
articles that are about adjacent companies (e.g. a Bloom Energy article
returned for NVDA because the article mentions NVIDIA chips). The new
news_fetcher.py validates ticker assignment via Claude, but historical
rows from before that fix are still polluting the news feed.

Usage:
  python3 scripts/cleanup_mistagged_news.py            # dry-run
  python3 scripts/cleanup_mistagged_news.py --apply    # actually delete
"""

import os
import sys
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()
DRY_RUN = '--apply' not in sys.argv

# Title-token whitelist per holding: at least one token must appear in the
# article title for the article to be considered correctly tagged.
TICKER_TOKENS = {
    'NVDA':   ['nvidia', 'nvda'],
    'GOOG':   ['google', 'alphabet', 'goog', 'youtube', 'waymo'],
    'RTX':    ['rtx', 'raytheon', 'pratt & whitney', 'collins aerospace', 'rocketdyne'],
    'BRK.B':  ['berkshire', 'buffett'],
    'TECK.B': ['teck'],
    'RIO':    ['rio tinto', ' rio '],
    'SGLN':   ['sgln', 'gold etf', 'physical gold'],
    'INRG':   ['inrg', 'clean energy etf'],
    'IITU':   ['iitu', 'tech etf'],
    'VGER':   ['vger', 'vanguard ftse'],
    'BA.':    ['bae systems', 'bae '],
    'VUSA':   ['vusa', 's&p 500'],
    'ISP6':   ['isp6'],
    'LGEN':   ['legal & general', 'lgen'],
    'EUE':    ['eue', 'msci europe'],
    'RHM':    ['rheinmetall', 'rhm'],
    'HO':     ['thales', 'ho.pa'],
}


def main():
    sb = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_SERVICE_ROLE_KEY'))
    print(f"Mode: {'DRY-RUN' if DRY_RUN else 'APPLY'}")

    cutoff = (datetime.now(timezone.utc) - timedelta(days=14)).isoformat()
    resp = (
        sb.table('news_items')
        .select('id, title, tickers')
        .eq('source_type', 'per_holding')
        .gte('published_at', cutoff)
        .limit(2000)
        .execute()
    )
    rows = resp.data or []
    print(f"Total per_holding rows in last 14d: {len(rows)}")

    bad_ids = []
    for r in rows:
        title = ' ' + (r.get('title') or '').lower() + ' '
        tickers = r.get('tickers') or []
        if not tickers:
            continue
        matched = False
        for t in tickers:
            tokens = TICKER_TOKENS.get(t, [t.lower()])
            for token in tokens:
                if token and token in title:
                    matched = True
                    break
            if matched:
                break
        if not matched:
            bad_ids.append(r['id'])
            print(f"  [mis-tagged] {tickers} | {(r.get('title') or '')[:90]}")

    print(f"\nMis-tagged rows to delete: {len(bad_ids)}")
    if bad_ids and not DRY_RUN:
        deleted = 0
        for i in range(0, len(bad_ids), 100):
            sb.table('news_items').delete().in_('id', bad_ids[i:i + 100]).execute()
            deleted += len(bad_ids[i:i + 100])
        print(f"Deleted {deleted} rows")
    elif bad_ids:
        print("DRY-RUN: pass --apply to actually delete")


if __name__ == '__main__':
    main()
