"""
supabase_sink.py

Shared Supabase client and writer helpers for all dual-write scripts.
Uses the service-role key for writes (bypasses RLS).
Fails open: logs errors without raising, so a Supabase outage never
breaks the Google Sheets pipeline.
"""

import os
import logging
from datetime import datetime, timezone
from supabase import create_client, Client

logger = logging.getLogger(__name__)

SUPABASE_URL = os.getenv('SUPABASE_URL', '')
SUPABASE_SERVICE_ROLE_KEY = os.getenv('SUPABASE_SERVICE_ROLE_KEY', '')

_client: Client | None = None


def _get_client() -> Client | None:
    global _client
    if _client is not None:
        return _client
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        logger.warning('Supabase env vars not set — skipping sink')
        return None
    try:
        _client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
        return _client
    except Exception as e:
        logger.warning(f'Supabase client init failed: {e}')
        return None


def _upsert(table: str, rows: list[dict], on_conflict: str | None = None) -> bool:
    client = _get_client()
    if not client or not rows:
        return False
    try:
        q = client.table(table).upsert(rows)
        if on_conflict:
            q = client.table(table).upsert(rows, on_conflict=on_conflict)
        q.execute()
        return True
    except Exception as e:
        logger.warning(f'Supabase upsert to {table} failed: {e}')
        return False


def _insert(table: str, rows: list[dict]) -> bool:
    client = _get_client()
    if not client or not rows:
        return False
    try:
        client.table(table).insert(rows).execute()
        return True
    except Exception as e:
        logger.warning(f'Supabase insert to {table} failed: {e}')
        return False


# ─── Writers ─────────────────────────────────────────────────────────────────

def write_holdings(positions: list[dict]) -> bool:
    """Upsert current portfolio positions. Each dict must have 'ticker' key."""
    return _upsert('holdings', positions, on_conflict='ticker')


def write_holdings_alerts(run_id: str, run_time: datetime, alerts: list[dict]) -> bool:
    """
    Insert one row per ticker from a holdings_monitor run.
    alerts: list of dicts with keys: ticker, alert_level, score, event, rationale
    """
    rows = [
        {
            'run_id': run_id,
            'run_time': run_time.isoformat(),
            'ticker': a['ticker'],
            'alert_level': a.get('alert_level', 'NONE'),
            'score': a.get('score'),
            'event': a.get('event'),
            'rationale': a.get('rationale'),
        }
        for a in alerts
    ]
    return _insert('holdings_alerts', rows)


def write_discoveries(run_id: str, run_time: datetime, candidates: list[dict]) -> bool:
    """
    Insert one row per candidate from a prospect_discovery run.
    candidates: list of dicts with keys: ticker, score, recommendation,
                sources, rationale, filtered_reason, surfaced_to_telegram
    """
    rows = [
        {
            'run_id': run_id,
            'run_time': run_time.isoformat(),
            'ticker': c['ticker'],
            'score': c.get('score'),
            'recommendation': c.get('recommendation'),
            'sources': c.get('sources', []),
            'rationale': c.get('rationale'),
            'filtered_reason': c.get('filtered_reason'),
            'surfaced_to_telegram': c.get('surfaced_to_telegram', False),
        }
        for c in candidates
    ]
    return _insert('discoveries', rows)


def write_portfolio_snapshot(date: str, totals: dict) -> bool:
    """
    Upsert one daily portfolio snapshot row.
    totals: grand_total, self_managed, managed, cash, net_deposits,
            spx, ftse, ndx, msci, gold
    """
    row = {'date': date, **totals}
    return _upsert('portfolio_snapshots', [row], on_conflict='date')


def write_trend_snapshot(snapshot_date: str, data: dict) -> bool:
    """
    Upsert one monthly trend snapshot row.
    data: all numeric columns from Inv26 - Trend schema.
    """
    row = {'snapshot_date': snapshot_date, **data}
    return _upsert('trend_snapshots', [row], on_conflict='snapshot_date')


def write_news_items(items: list[dict]) -> bool:
    """
    Upsert news articles. Each dict must have 'id' and 'url'.
    Silently skips duplicates via upsert on 'id'.
    """
    return _upsert('news_items', items, on_conflict='id')


def write_sectors(entries: list[dict]) -> bool:
    """Upsert ticker→sector/market lookup rows. Each dict must have 'ticker'."""
    return _upsert('sectors', entries, on_conflict='ticker')
