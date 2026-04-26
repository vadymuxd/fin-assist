"""
supabase_sink.py

Shared Supabase client and writer helpers for all dual-write scripts.
Uses the service-role key for writes (bypasses RLS).
Fails open: logs errors without raising, so a Supabase outage never
breaks the Google Sheets pipeline.
"""

import os
import logging
import requests as _requests
from datetime import datetime, timedelta, timezone
from supabase import create_client, Client

logger = logging.getLogger(__name__)

_client: Client | None = None
_revalidated: bool = False


def _trigger_revalidate() -> None:
    """Ping the Next.js revalidate endpoint once per process so the frontend
    picks up fresh data on the next page load, without waiting for ISR expiry."""
    global _revalidated
    if _revalidated:
        return
    url = os.getenv('APP_REVALIDATE_URL', '')
    secret = os.getenv('APP_REVALIDATE_SECRET', '')
    if not url or not secret:
        return
    try:
        _requests.post(url, headers={'x-revalidate-secret': secret}, timeout=5)
        _revalidated = True
        logger.info('Frontend revalidated')
    except Exception as e:
        logger.debug(f'Revalidate ping failed (non-critical): {e}')


def _get_client() -> Client | None:
    global _client
    if _client is not None:
        return _client
    url = os.getenv('SUPABASE_URL', '')
    key = os.getenv('SUPABASE_SERVICE_ROLE_KEY', '')
    if not url or not key:
        logger.warning('Supabase env vars not set — skipping sink')
        return None
    try:
        _client = create_client(url, key)
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
    ok = _upsert('holdings', positions, on_conflict='ticker')
    if ok:
        _trigger_revalidate()
    return ok


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
    ok = _insert('holdings_alerts', rows)
    if ok:
        _trigger_revalidate()
    return ok


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
    ok = _insert('discoveries', rows)
    if ok:
        _trigger_revalidate()
    return ok


def write_portfolio_snapshot(date: str, totals: dict) -> bool:
    """
    Upsert one daily portfolio snapshot row.
    totals: grand_total, self_managed, managed, cash, net_deposits,
            spx, ftse, ndx, msci, gold
    """
    row = {'date': date, **totals}
    ok = _upsert('portfolio_snapshots', [row], on_conflict='date')
    if ok:
        _trigger_revalidate()
    return ok


def write_trend_snapshot(snapshot_date: str, data: dict) -> bool:
    """
    Upsert one monthly trend snapshot row.
    data: all numeric columns from Inv26 - Trend schema.
    """
    row = {'snapshot_date': snapshot_date, **data}
    return _upsert('trend_snapshots', [row], on_conflict='snapshot_date')


def write_news_items(items: list[dict]) -> bool:
    """
    Upsert news articles. Each dict must have 'id', 'url', and 'source_type'
    ('per_holding' or 'market_scan'). Defensive default of 'market_scan' is
    applied if missing — per_holding writes must opt in explicitly so they
    don't accidentally pollute the user-facing news feed.
    Silently skips duplicates via upsert on 'id'.
    """
    for item in items:
        item.setdefault('source_type', 'market_scan')
    ok = _upsert('news_items', items, on_conflict='id')
    if ok:
        _trigger_revalidate()
    return ok


def write_sectors(entries: list[dict]) -> bool:
    """Upsert ticker→sector/market lookup rows. Each dict must have 'ticker'."""
    return _upsert('sectors', entries, on_conflict='ticker')


def write_savings_accounts(rows: list[dict]) -> bool:
    """
    Upsert per-account savings balance rows.
    Each dict must have: date, bank, account_name, account_type, owner, balance_gbp.
    Unique constraint: (date, bank, account_name).
    """
    ok = _upsert(
        'savings_accounts',
        rows,
        on_conflict='date,bank,account_name',
    )
    if ok:
        _trigger_revalidate()
    return ok


def write_savings_snapshot(date: str, total: float, personal: float, joint: float) -> bool:
    """
    Upsert one daily savings aggregate row.
    date: ISO date string (YYYY-MM-DD).
    """
    row = {
        'date': date,
        'total': total,
        'personal_total': personal,
        'joint_total': joint,
    }
    ok = _upsert('savings_snapshots', [row], on_conflict='date')
    if ok:
        _trigger_revalidate()
    return ok


def purge_stale_market_scan_news(days: int = 30) -> int:
    """
    Delete market_scan news older than `days`. Per-holding news is kept
    indefinitely so users can scroll back. Market-scan articles only matter
    while they're recent enough to inform discovery scoring; stale rows just
    bloat the table and never re-surface to the user (frontend filters them).
    Returns count of rows deleted.
    """
    client = _get_client()
    if not client:
        return 0
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    try:
        resp = (
            client.table('news_items')
            .delete()
            .eq('source_type', 'market_scan')
            .lt('published_at', cutoff)
            .execute()
        )
        n = len(resp.data or [])
        if n:
            logger.info(f'Purged {n} stale market_scan news rows (older than {days}d)')
        return n
    except Exception as e:
        logger.warning(f'Stale news purge failed: {e}')
        return 0
