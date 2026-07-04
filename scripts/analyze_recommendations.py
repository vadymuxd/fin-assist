#!/usr/bin/env python3
"""
analyze_recommendations.py — Work 4: were the bot's stock recommendations any good?

Event-study analysis of every ACT-level holdings_alerts row (the only alerts
that actually got sent to Telegram — WATCH-level "discoveries" never did, per
Notion Plan). For each alert, measures the ticker's forward return at ~1wk,
~2wk, ~1mo and "to date" horizons against your ACTUAL Custom Stocks portfolio
return over the same window — i.e. what your real self-managed stock
portfolio actually did, not a market index. A BUY_MORE call is judged
against "did this stock do better than your portfolio as a whole did
anyway", and a TRIM/SELL call against "did avoiding it turn out to be the
right move relative to what your portfolio actually returned".

The Custom Stocks benchmark is a Time-Weighted Return (TWR) index built the
same way the web app's Performance Comparison chart builds it — chaining
sub-period returns between portfolio_snapshots rows using self_managed +
stocks_started_value, so a deposit/BUY/consolidation contributes 0% return
and only real market movement moves the line (ported from
buildComparisonData() in web/lib/queries.ts).

Also runs a fixed-notional (£1,000 per signal) overlay: since alerts don't
carry a suggested trade size, this isolates whether the DIRECTION of the
calls added value, without guessing at real position sizing. Compares the
total hypothetical P&L of following every signal against what the same
£1,000-per-signal, same-timing flows would have earned by just staying in
the actual Custom Stocks portfolio instead — i.e. did tilting toward/away
from these specific tickers beat doing nothing.

Run:
    python3 scripts/analyze_recommendations.py
"""

import os
import sys
import bisect
from datetime import date

from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

NOTIONAL_PER_SIGNAL = 1000.0
HORIZONS = [(5, '~1wk'), (10, '~2wk'), (21, '~1mo')]

# SELL = fully exits the position (weight 1.0); TRIM = partial reduction (0.5);
# BUY_MORE adds to it (weight 1.0, opposite sign).
ACTION_WEIGHT = {'BUY_MORE': 1.0, 'TRIM': -0.5, 'SELL': -1.0}


def get_client():
    url = os.getenv('SUPABASE_URL', '')
    key = os.getenv('SUPABASE_SERVICE_ROLE_KEY', '')
    if not url or not key:
        print('Missing SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY in .env', file=sys.stderr)
        sys.exit(1)
    return create_client(url, key)


def build_series(rows, date_key, value_key):
    """rows -> (sorted_dates, sorted_values), deduped/sorted by date."""
    pairs = sorted({(r[date_key], float(r[value_key])) for r in rows if r.get(value_key) is not None})
    dates = [p[0] for p in pairs]
    values = [p[1] for p in pairs]
    return dates, values


def build_custom_stocks_twr(snapshot_rows):
    """Port of buildComparisonData()'s stocksTwr chain in web/lib/queries.ts.

    Chains sub-period returns between consecutive portfolio_snapshots rows.
    A deposit/BUY/consolidation shifts stocks_started_value by the same
    amount it shifts self_managed, so it cancels out of the sub-period base
    and contributes 0% return — only real market movement moves the index.
    Returns (sorted_dates, twr_index) with twr_index[0] = 1.0.
    """
    rows = sorted(
        ({'date': r['date'], 'self_managed': float(r['self_managed']),
          'started': float(r['stocks_started_value'])} for r in snapshot_rows
         if r.get('self_managed') is not None and r.get('stocks_started_value') is not None),
        key=lambda r: r['date'],
    )
    dates, twr = [], []
    running = 1.0
    prev = None
    for r in rows:
        if prev is not None:
            base = prev['self_managed'] + (r['started'] - prev['started'])
            if base > 0:
                running *= 1 + (r['self_managed'] - base) / base
        dates.append(r['date'])
        twr.append(running)
        prev = r
    return dates, twr


def price_at_or_after(dates, values, target):
    """First trading day on/after target (alert-day price)."""
    i = bisect.bisect_left(dates, target)
    return values[i] if i < len(values) else None


def price_n_after(dates, values, target, n):
    """Price N trading days after the first day on/after target; None if out of range."""
    i = bisect.bisect_left(dates, target)
    j = i + n
    return values[j] if 0 <= j < len(values) else None


def pct(a, b):
    return (b / a - 1) if (a is not None and b is not None) else None


def fmt_pct(x):
    return f'{x * 100:+.1f}%' if x is not None else 'n/a'


def main():
    sb = get_client()

    alerts = (
        sb.table('holdings_alerts')
        .select('ticker, run_time, alert_level, suggested_action, event, rationale')
        .eq('alert_level', 'ACT')
        .order('run_time')
        .execute()
    ).data

    if not alerts:
        print('No ACT-level alerts found.')
        return

    # Fetch per-ticker (not a single .in_() query) — a combined query across
    # several hundred-row-each tickers can silently hit Supabase's 1000-row
    # response cap and drop whole tickers (bit the spending dashboard before).
    tickers = sorted({a['ticker'] for a in alerts})
    by_ticker = {}
    for t in tickers:
        rows = sb.table('holding_price_history').select('date, price').eq('ticker', t).execute().data
        by_ticker[t] = build_series(rows, 'date', 'price')

    snapshot_rows = sb.table('portfolio_snapshots').select('date, self_managed, stocks_started_value').execute().data
    port_dates, port_twr = build_custom_stocks_twr(snapshot_rows)

    today = date.today().isoformat()

    print('=' * 100)
    print('WORK 4 — Recommendation quality analysis (ACT-level Telegram alerts only)')
    print(f'{len(alerts)} signals, {alerts[0]["run_time"][:10]} → {alerts[-1]["run_time"][:10]}. Evaluated as of {today}.')
    print('Benchmark: your actual Custom Stocks portfolio (TWR, deposit-neutral) — not a market index.')
    print('=' * 100)

    results = []
    for a in alerts:
        t = a['ticker']
        d0 = a['run_time'][:10]
        dates, values = by_ticker[t]
        p0 = price_at_or_after(dates, values, d0)
        if p0 is None:
            continue

        row = {'ticker': t, 'date': d0, 'action': a['suggested_action'],
               'event': a['event'], 'p0': p0}

        for n, label in HORIZONS:
            pN = price_n_after(dates, values, d0, n)
            row[f'ret_{label}'] = pct(p0, pN)
            b0 = price_at_or_after(port_dates, port_twr, d0)
            bN = price_n_after(port_dates, port_twr, d0, n)
            port_ret = pct(b0, bN)
            row[f'alpha_{label}'] = (row[f'ret_{label}'] - port_ret) if (row[f'ret_{label}'] is not None and port_ret is not None) else None

        # "To date": latest available price vs alert-day price.
        p_latest = values[-1]
        row['ret_todate'] = pct(p0, p_latest)
        b0 = price_at_or_after(port_dates, port_twr, d0)
        b_latest = port_twr[-1]
        port_ret_todate = pct(b0, b_latest) if b0 else None
        row['alpha_todate'] = (row['ret_todate'] - port_ret_todate) if port_ret_todate is not None else None

        results.append(row)

    # ── Per-signal table ────────────────────────────────────────────────────
    print(f"\n{'Date':<11}{'Ticker':<8}{'Action':<10}{'~1wk':<9}{'~2wk':<9}{'~1mo':<9}{'To date':<10}{'α vs portfolio'}")
    print('-' * 100)
    for r in results:
        print(f"{r['date']:<11}{r['ticker']:<8}{r['action']:<10}"
              f"{fmt_pct(r['ret_~1wk']):<9}{fmt_pct(r['ret_~2wk']):<9}{fmt_pct(r['ret_~1mo']):<9}"
              f"{fmt_pct(r['ret_todate']):<10}{fmt_pct(r['alpha_todate'])}")

    # ── Hit-rate by action type ─────────────────────────────────────────────
    print('\n' + '=' * 100)
    print('HIT RATE BY ACTION (evaluated "to date", vs your actual Custom Stocks portfolio return)')
    print('=' * 100)
    for action in ('BUY_MORE', 'TRIM', 'SELL'):
        rows = [r for r in results if r['action'] == action and r['ret_todate'] is not None]
        if not rows:
            continue
        if action == 'BUY_MORE':
            hits = [r for r in rows if r['ret_todate'] > 0 and (r['alpha_todate'] or 0) > 0]
            desc = 'gained AND beat your own portfolio'
        else:
            hits = [r for r in rows if r['ret_todate'] < 0 or (r['alpha_todate'] or 0) < 0]
            desc = 'price fell OR underperformed your portfolio (i.e. reducing/exiting was right)'
        avg_ret   = sum(r['ret_todate'] for r in rows) / len(rows)
        avg_alpha = sum(r['alpha_todate'] for r in rows if r['alpha_todate'] is not None) / len(rows)
        print(f"{action:<10} n={len(rows):<3} hit-rate={len(hits)}/{len(rows)} ({desc})"
              f"   avg return={fmt_pct(avg_ret)}   avg vs your portfolio={fmt_pct(avg_alpha)}")

    # ── Concentration check: is this broad-based, or one ticker doing the work? ─
    print('\n' + '=' * 100)
    print('BY TICKER (concentration check — is the signal broad-based or one lucky name?)')
    print('=' * 100)
    by_ticker_agg = {}
    for r in results:
        if r['ret_todate'] is None:
            continue
        by_ticker_agg.setdefault(r['ticker'], []).append(r)
    for t, rows in sorted(by_ticker_agg.items(), key=lambda kv: -len(kv[1])):
        avg_alpha = sum(r['alpha_todate'] for r in rows if r['alpha_todate'] is not None) / len(rows)
        print(f"{t:<8} n={len(rows):<3} avg return={fmt_pct(sum(r['ret_todate'] for r in rows) / len(rows)):<9} avg vs your portfolio={fmt_pct(avg_alpha)}")

    # ── Version C: fixed-notional overlay vs staying in the actual portfolio ─
    print('\n' + '=' * 100)
    print(f'VERSION C — if you had acted on EVERY signal (£{NOTIONAL_PER_SIGNAL:,.0f} notional per signal, "to date")')
    print('=' * 100)
    total_signal_pnl = 0.0
    total_asis_pnl   = 0.0
    for r in results:
        w = ACTION_WEIGHT[r['action']]
        if r['ret_todate'] is None:
            continue
        total_signal_pnl += w * NOTIONAL_PER_SIGNAL * r['ret_todate']
        if r['alpha_todate'] is not None:
            portfolio_equiv_ret = r['ret_todate'] - r['alpha_todate']
            total_asis_pnl += w * NOTIONAL_PER_SIGNAL * portfolio_equiv_ret
    print(f"Total notional deployed across {len(results)} signals: £{NOTIONAL_PER_SIGNAL * len(results):,.0f}")
    print(f"Hypothetical P&L from following every signal:            £{total_signal_pnl:+,.0f}")
    print(f"Same cash flows, same timing, left in your portfolio as-is: £{total_asis_pnl:+,.0f}")
    print(f"Net effect of following the bot vs doing nothing:         £{total_signal_pnl - total_asis_pnl:+,.0f}")

    # Sensitivity: how much of that net effect comes from the single most-
    # repeated ticker? A result that evaporates when you drop one name isn't
    # evidence the PROCESS works — it's evidence that name had a good run.
    top_ticker = max(by_ticker_agg, key=lambda t: len(by_ticker_agg[t])) if by_ticker_agg else None
    if top_ticker:
        signal_ex  = sum(ACTION_WEIGHT[r['action']] * NOTIONAL_PER_SIGNAL * r['ret_todate']
                          for r in results if r['ticker'] != top_ticker and r['ret_todate'] is not None)
        asis_ex    = sum(ACTION_WEIGHT[r['action']] * NOTIONAL_PER_SIGNAL * (r['ret_todate'] - r['alpha_todate'])
                          for r in results if r['ticker'] != top_ticker and r['ret_todate'] is not None and r['alpha_todate'] is not None)
        net_ex     = signal_ex - asis_ex
        net_full   = total_signal_pnl - total_asis_pnl
        n_ex = len(by_ticker_agg[top_ticker])
        print(f"\nExcluding {top_ticker} ({n_ex} of {len(results)} signals): net effect = £{net_ex:+,.0f}  (full sample was £{net_full:+,.0f})")
        print(f"{top_ticker} alone accounts for £{net_full - net_ex:+,.0f} of the £{net_full:+,.0f} total"
              f" — {'the sign FLIPS without it, so this result is really about ' + top_ticker + ', not the process' if (net_ex > 0) != (net_full > 0) else 'result direction holds without it too'}.")

    # ── Version B: one concrete ~1-month-ago example ───────────────────────
    print('\n' + '=' * 100)
    print('VERSION B — one concrete example, ~1 month ago')
    print('=' * 100)
    one_month_ago_candidates = [r for r in results if r['date'] <= today]
    if one_month_ago_candidates:
        from datetime import date as _date
        target = _date.fromisoformat(today)
        best = min(one_month_ago_candidates,
                   key=lambda r: abs((target - _date.fromisoformat(r['date'])).days - 30))
        print(f"{best['date']} — {best['action']} {best['ticker']} (\"{best['event']}\")")
        print(f"  Price then: £{best['p0']:.2f}")
        print(f"  Return to date: {fmt_pct(best['ret_todate'])}  |  vs your Custom Stocks portfolio: {fmt_pct(best['alpha_todate'])}")

    print()


if __name__ == '__main__':
    main()
