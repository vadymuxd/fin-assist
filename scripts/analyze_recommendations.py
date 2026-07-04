#!/usr/bin/env python3
"""
analyze_recommendations.py — Work 4: were the bot's stock recommendations any good?

Event-study analysis of every ACT-level holdings_alerts row (the only alerts
that actually got sent to Telegram — WATCH-level "discoveries" never did, per
Notion Plan). For each alert, measures the ticker's forward return at ~1wk,
~2wk, ~1mo and "to date" horizons against the S&P 500 (portfolio_snapshots.spx)
over the same window, so a BUY_MORE call is judged against "did it make money
AND beat the market", and a TRIM/SELL call is judged against "did avoiding it
turn out to be the right move".

Also runs a fixed-notional (£1,000 per signal) overlay: since alerts don't
carry a suggested trade size, this isolates whether the DIRECTION of the
calls added value, without guessing at real position sizing. Compares the
total hypothetical P&L of following every signal against what the same
£1,000-per-signal, same-timing flows would have earned in the S&P 500 instead
— i.e. did the bot's stock-specific picks beat just index-timing the same
cash moves.

Run:
    python3 scripts/analyze_recommendations.py
"""

import os
import sys
import bisect
from datetime import date, datetime

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

    spx_rows = sb.table('portfolio_snapshots').select('date, spx').execute().data
    spx_dates, spx_values = build_series(spx_rows, 'date', 'spx')

    today = date.today().isoformat()

    print('=' * 100)
    print('WORK 4 — Recommendation quality analysis (ACT-level Telegram alerts only)')
    print(f'{len(alerts)} signals, {alerts[0]["run_time"][:10]} → {alerts[-1]["run_time"][:10]}. Evaluated as of {today}.')
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
            s0 = price_at_or_after(spx_dates, spx_values, d0)
            sN = price_n_after(spx_dates, spx_values, d0, n)
            spx_ret = pct(s0, sN) if s0 and sN else None
            row[f'alpha_{label}'] = (row[f'ret_{label}'] - spx_ret) if (row[f'ret_{label}'] is not None and spx_ret is not None) else None

        # "To date": latest available price vs alert-day price.
        p_latest = values[-1]
        row['ret_todate'] = pct(p0, p_latest)
        s0 = price_at_or_after(spx_dates, spx_values, d0)
        s_latest = spx_values[-1]
        spx_ret_todate = pct(s0, s_latest) if s0 else None
        row['alpha_todate'] = (row['ret_todate'] - spx_ret_todate) if spx_ret_todate is not None else None

        results.append(row)

    # ── Per-signal table ────────────────────────────────────────────────────
    print(f"\n{'Date':<11}{'Ticker':<8}{'Action':<10}{'~1wk':<9}{'~2wk':<9}{'~1mo':<9}{'To date':<10}{'α to date'}")
    print('-' * 100)
    for r in results:
        print(f"{r['date']:<11}{r['ticker']:<8}{r['action']:<10}"
              f"{fmt_pct(r['ret_~1wk']):<9}{fmt_pct(r['ret_~2wk']):<9}{fmt_pct(r['ret_~1mo']):<9}"
              f"{fmt_pct(r['ret_todate']):<10}{fmt_pct(r['alpha_todate'])}")

    # ── Hit-rate by action type ─────────────────────────────────────────────
    print('\n' + '=' * 100)
    print('HIT RATE BY ACTION (evaluated "to date")')
    print('=' * 100)
    for action in ('BUY_MORE', 'TRIM', 'SELL'):
        rows = [r for r in results if r['action'] == action and r['ret_todate'] is not None]
        if not rows:
            continue
        if action == 'BUY_MORE':
            hits = [r for r in rows if r['ret_todate'] > 0 and (r['alpha_todate'] or 0) > 0]
            desc = 'gained AND beat S&P 500'
        else:
            hits = [r for r in rows if r['ret_todate'] < 0 or (r['alpha_todate'] or 0) < 0]
            desc = 'price fell OR underperformed S&P 500 (i.e. reducing/exiting was right)'
        avg_ret   = sum(r['ret_todate'] for r in rows) / len(rows)
        avg_alpha = sum(r['alpha_todate'] for r in rows if r['alpha_todate'] is not None) / len(rows)
        print(f"{action:<10} n={len(rows):<3} hit-rate={len(hits)}/{len(rows)} ({desc})"
              f"   avg return={fmt_pct(avg_ret)}   avg alpha vs S&P500={fmt_pct(avg_alpha)}")

    # ── Version C: fixed-notional overlay vs same cash flows in S&P 500 ────
    print('\n' + '=' * 100)
    print(f'VERSION C — if you had acted on EVERY signal (£{NOTIONAL_PER_SIGNAL:,.0f} notional per signal, "to date")')
    print('=' * 100)
    total_signal_pnl = 0.0
    total_bench_pnl  = 0.0
    for r in results:
        w = ACTION_WEIGHT[r['action']]
        if r['ret_todate'] is None:
            continue
        total_signal_pnl += w * NOTIONAL_PER_SIGNAL * r['ret_todate']
        if r['alpha_todate'] is not None:
            spx_equiv_ret = r['ret_todate'] - r['alpha_todate']
            total_bench_pnl += w * NOTIONAL_PER_SIGNAL * spx_equiv_ret
    print(f"Total notional deployed across {len(results)} signals: £{NOTIONAL_PER_SIGNAL * len(results):,.0f}")
    print(f"Hypothetical P&L from following every signal:      £{total_signal_pnl:+,.0f}")
    print(f"Same cash flows, same timing, into S&P 500 instead: £{total_bench_pnl:+,.0f}")
    print(f"Bot's stock-picking edge over just index-timing:    £{total_signal_pnl - total_bench_pnl:+,.0f}")

    # ── Version B: one concrete ~1-month-ago example ───────────────────────
    print('\n' + '=' * 100)
    print('VERSION B — one concrete example, ~1 month ago')
    print('=' * 100)
    one_month_ago_candidates = [r for r in results if r['date'] <= today]
    if one_month_ago_candidates:
        # closest alert to 30 days before today
        from datetime import date as _date
        target = _date.fromisoformat(today)
        best = min(one_month_ago_candidates,
                   key=lambda r: abs((target - _date.fromisoformat(r['date'])).days - 30))
        print(f"{best['date']} — {best['action']} {best['ticker']} (\"{best['event']}\")")
        print(f"  Price then: £{best['p0']:.2f}")
        print(f"  Return to date: {fmt_pct(best['ret_todate'])}  |  vs S&P 500: {fmt_pct(best['alpha_todate'])}")

    print()


if __name__ == '__main__':
    main()
