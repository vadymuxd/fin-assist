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


def force_revalidate() -> None:
    """Reset the once-per-process guard and ping the revalidate endpoint again.

    _trigger_revalidate fires on the FIRST Supabase write of a process. In a
    multi-domain run (snapshot_worker --domain all) that first write is the
    portfolio snapshot, which lands BEFORE savings/pension data is written — so
    a page request in that gap re-caches stale values for the ISR window. Call
    this AFTER all writes complete to purge the frontend cache once everything
    is in Supabase."""
    global _revalidated
    _revalidated = False
    _trigger_revalidate()


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


def delete_holding(ticker: str) -> bool:
    """Remove a ticker from the holdings table (called when a position is fully sold)."""
    client = _get_client()
    if not client:
        return False
    try:
        client.table('holdings').delete().eq('ticker', ticker).execute()
        _trigger_revalidate()
        return True
    except Exception as e:
        logger.warning(f'Supabase delete from holdings failed for {ticker}: {e}')
        return False


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
    totals: vadym_total, lisa_total, joint_total, self_managed, managed, cash,
            net_deposits, spx, ftse, ndx, msci, gold
    """
    row = {'date': date, **totals}
    ok = _upsert('portfolio_snapshots', [row], on_conflict='date')
    if ok:
        _trigger_revalidate()
    return ok


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


def write_holding_trade(trade: dict) -> bool:
    """
    Insert one BUY/SELL row into holding_trades.
    trade keys: date, ticker, action, qty, price_gbp, total_gbp, platform, notes
    """
    row = {
        'date':       trade['date'],
        'ticker':     trade['ticker'],
        'action':     trade['action'].upper(),
        'qty':        trade['qty'],
        'price_gbp':  trade['price_gbp'],
        'total_gbp':  trade['total_gbp'],
        'platform':   trade.get('platform') or None,
        'notes':      trade.get('notes') or None,
    }
    return _insert('holding_trades', [row])


def write_sectors(entries: list[dict]) -> bool:
    """Upsert ticker→sector/market lookup rows. Each dict must have 'ticker'."""
    return _upsert('sectors', entries, on_conflict='ticker')


def write_savings_accounts(rows: list[dict]) -> bool:
    """
    Upsert per-account savings balance rows.
    Each dict must have: date, bank, account_name, account_type, owner, balance_gbp.
    Unique constraint: (date, bank, account_name).
    """
    now = datetime.now(timezone.utc).isoformat()
    for row in rows:
        row['updated_at'] = now
    ok = _upsert(
        'savings_accounts',
        rows,
        on_conflict='date,bank,account_name',
    )
    if ok:
        _trigger_revalidate()
    return ok


def write_savings_snapshot(date: str, total: float, vadym: float, lisa: float, joint: float) -> bool:
    """
    Upsert one daily savings aggregate row.
    date: ISO date string (YYYY-MM-DD).
    """
    row = {
        'date': date,
        'total': total,
        'vadym_total': vadym,
        'lisa_total': lisa,
        'joint_total': joint,
        'updated_at': datetime.now(timezone.utc).isoformat(),
    }
    ok = _upsert('savings_snapshots', [row], on_conflict='date')
    if ok:
        _trigger_revalidate()
    return ok


def write_pension_accounts(rows: list[dict]) -> bool:
    """
    Upsert per-provider pension balance rows.
    Each dict must have: date, provider, account_name, owner, balance_gbp.
    Unique constraint: (date, provider, account_name).
    """
    now = datetime.now(timezone.utc).isoformat()
    for row in rows:
        row['updated_at'] = now
    ok = _upsert(
        'pension_accounts',
        rows,
        on_conflict='date,provider,account_name',
    )
    if ok:
        _trigger_revalidate()
    return ok


def write_pension_snapshot(date: str, total: float, vadym: float = 0.0, lisa: float = 0.0) -> bool:
    """
    Upsert one monthly pension aggregate row.
    date: ISO date string (YYYY-MM-DD).
    """
    row = {
        'date':        date,
        'total':       total,
        'vadym_total': vadym,
        'lisa_total':  lisa,
        'updated_at':  datetime.now(timezone.utc).isoformat(),
    }
    ok = _upsert('pension_snapshots', [row], on_conflict='date')
    if ok:
        _trigger_revalidate()
    return ok


def get_recently_alerted_tickers(hours: int = 48) -> set:
    """
    Return the set of tickers that had any alert or discovery logged in the
    last `hours`.  Used by alert_dispatcher.py for ticker-level dedup.
    Fails open: returns empty set on any error so the pipeline never blocks.
    """
    client = _get_client()
    if not client:
        return set()
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    tickers: set = set()
    try:
        for table in ('holdings_alerts', 'discoveries'):
            resp = client.table(table).select('ticker').gte('run_time', cutoff).execute()
            for row in (resp.data or []):
                tickers.add(row['ticker'])
    except Exception as e:
        logger.warning(f'Dedup check failed: {e}')
    return tickers


def get_recommendation_mechanism_summary() -> dict:
    """Current mechanism_version (whichever produced the most recent ACT
    alert) + how many signals exist under it + the date of the earliest one.
    Used to render a live 'Recommendation Quality' section on Investments
    Context (sheets_updater.py) that survives the page's daily full rebuild,
    instead of a hand-written note that would get archived on the next run.
    Returns {} on any error or if no alerts exist.
    """
    client = _get_client()
    if not client:
        return {}
    try:
        latest = (
            client.table('holdings_alerts')
            .select('mechanism_version, run_time')
            .eq('alert_level', 'ACT')
            .order('run_time', desc=True)
            .limit(1)
            .execute()
        )
        if not latest.data:
            return {}
        version = latest.data[0].get('mechanism_version') or 'untagged'
        same_version = (
            client.table('holdings_alerts')
            .select('run_time')
            .eq('alert_level', 'ACT')
            .eq('mechanism_version', version)
            .order('run_time')
            .execute()
        )
        rows = same_version.data or []
        return {
            'version': version,
            'count':   len(rows),
            'since':   rows[0]['run_time'][:10] if rows else None,
        }
    except Exception as e:
        logger.warning(f'Recommendation mechanism summary failed: {e}')
        return {}


def get_recent_alert_events(ticker: str = None, days: int = 10) -> dict:
    """
    Return {ticker: [event, ...]} for holdings_alerts logged in the last
    `days`. Used for catalyst-level dedup (same underlying story re-surfacing
    a few days later isn't a new signal) — a longer, event-text-aware
    complement to get_recently_alerted_tickers()'s 48h ticker-level dedup.
    Fails open: returns {} on any error.
    """
    client = _get_client()
    if not client:
        return {}
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    events: dict = {}
    try:
        q = client.table('holdings_alerts').select('ticker,event').gte('run_time', cutoff)
        if ticker:
            q = q.eq('ticker', ticker)
        for row in (q.execute().data or []):
            if row.get('event'):
                events.setdefault(row['ticker'], []).append(row['event'])
    except Exception as e:
        logger.warning(f'Catalyst dedup check failed: {e}')
    return events


def write_holding_alert(run_id: str, run_time: str, assessment: dict) -> bool:
    """
    Insert a single actionable holding alert from alert_dispatcher.py.
    assessment must have: ticker, action, score, event, rationale.
    mechanism_version (optional) tags which recommendation mechanism
    produced this row, so future backtests can filter cleanly.
    """
    row = {
        'run_id':            run_id,
        'run_time':          run_time,
        'ticker':            assessment['ticker'],
        'alert_level':       'ACT',
        'score':             assessment.get('score'),
        'event':             assessment.get('event', ''),
        'rationale':         assessment.get('rationale', ''),
        'suggested_action':  assessment.get('action', 'HOLD'),
        'mechanism_version': assessment.get('mechanism_version'),
    }
    ok = _insert('holdings_alerts', [row])
    if ok:
        _trigger_revalidate()
    return ok


def write_prospect_alert(run_id: str, run_time: str, assessment: dict) -> bool:
    """
    Insert a single BUY prospect discovery from alert_dispatcher.py.
    assessment must have: ticker, name, score, rationale.
    """
    row = {
        'run_id':               run_id,
        'run_time':             run_time,
        'ticker':               assessment['ticker'],
        'score':                assessment.get('score'),
        'recommendation':       'BUY',
        'sources':              ['market_scan'],
        'rationale':            assessment.get('rationale', ''),
        'filtered_reason':      None,
        'surfaced_to_telegram': True,
    }
    ok = _insert('discoveries', [row])
    if ok:
        _trigger_revalidate()
    return ok


def write_transaction(trade: dict) -> bool:
    """
    Insert one row into the transactions table.
    Only for DEPOSIT/WITHDRAWAL — BUY/SELL have no matching type in the constraint.
    trade keys: date, domain, account_name, amount_gbp, type, notes, source
    """
    row = {
        'date':             trade['date'],
        'domain':           trade.get('domain', 'investments'),
        'account_name':     trade.get('account_name', ''),
        'amount_gbp':       trade['amount_gbp'],
        'type':             trade['type'],
        'notes':            trade.get('notes', ''),
        'source':           trade.get('source', 'nl_claude'),
        'synced_to_notion': True,
    }
    ok = _insert('transactions', [row])
    if ok:
        _trigger_revalidate()
    return ok


def write_holding_prices(date: str, prices: dict) -> bool:
    """
    Upsert per-ticker closing prices for one date into holding_price_history.
    prices: {ticker: price}. Re-running the same day overwrites the row.
    Fails open — if the table is missing the trailing-stop signal just stays
    quiet, stop-loss and concentration signals are unaffected.
    """
    rows = [
        {'ticker': t, 'date': date, 'price': p}
        for t, p in prices.items()
        if p and p > 0
    ]
    return _upsert('holding_price_history', rows, on_conflict='ticker,date')


def get_holding_price_history(days: int = 30) -> dict:
    """
    Return {ticker: [price, ...]} for the last `days`, oldest first.
    Used to compute a rolling high for the trailing-stop sell signal.
    Fails open: returns {} on any error (e.g. table not yet migrated).
    """
    client = _get_client()
    if not client:
        return {}
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).date().isoformat()
    history: dict = {}
    try:
        resp = (
            client.table('holding_price_history')
            .select('ticker,date,price')
            .gte('date', cutoff)
            .order('date')
            .execute()
        )
        for row in (resp.data or []):
            try:
                price = float(row['price'])
            except (ValueError, TypeError, KeyError):
                continue
            history.setdefault(row['ticker'], []).append(price)
    except Exception as e:
        logger.warning(f'holding_price_history read failed: {e}')
        return {}
    return history


def get_monzo_cursor(account_type: str) -> int:
    """Return MAX row_index for account_type, or 0 if no rows yet."""
    client = _get_client()
    if not client:
        return 0
    try:
        resp = (
            client.table('monzo_transactions')
            .select('row_index')
            .eq('account_type', account_type)
            .order('row_index', desc=True)
            .limit(1)
            .execute()
        )
        rows = resp.data or []
        return rows[0]['row_index'] if rows else 0
    except Exception as e:
        logger.warning(f'get_monzo_cursor failed for {account_type}: {e}')
        return 0


def write_monzo_transactions(rows: list[dict]) -> bool:
    """Upsert monzo_transactions rows. Unique on (transaction_id, account_type)."""
    ok = _upsert('monzo_transactions', rows, on_conflict='transaction_id,account_type')
    if ok:
        _trigger_revalidate()
    return ok


def get_unprocessed_monzo_transactions() -> list[dict]:
    """Return monzo_transactions rows not yet considered by monzo_balance_sync.py
    (feature.1) — i.e. balance_processed_at IS NULL. Fails open: returns []
    on any error so a Supabase hiccup never blocks bot_sync.yml."""
    client = _get_client()
    if not client:
        return []
    try:
        resp = (
            client.table('monzo_transactions')
            .select('id,transaction_id,account_type,row_index,date,type,name,category,amount,pot_name,notes')
            .is_('balance_processed_at', 'null')
            .order('row_index')
            .execute()
        )
        return resp.data or []
    except Exception as e:
        logger.warning(f'get_unprocessed_monzo_transactions failed: {e}')
        return []


def mark_monzo_transactions_processed(ids: list[int]) -> bool:
    """Stamp balance_processed_at=now() on monzo_transactions rows by primary
    key id. Called for every row monzo_balance_sync.py scans (matched,
    unresolved, or irrelevant) so history is never re-scanned and a
    transaction is never considered twice."""
    client = _get_client()
    if not client or not ids:
        return False
    now = datetime.now(timezone.utc).isoformat()
    try:
        client.table('monzo_transactions').update({'balance_processed_at': now}).in_('id', ids).execute()
        return True
    except Exception as e:
        logger.warning(f'mark_monzo_transactions_processed failed: {e}')
        return False


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
