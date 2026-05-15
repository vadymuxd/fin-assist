#!/usr/bin/env python3
"""
digest_worker.py — Monday 08:00 BST weekly digest.

Replaces: weekly_digest.py (which re-ran the full pipeline before sending).

Reads exclusively from Supabase — no Google Sheets, no live price API, so it
never rate-limits. Data comes from the daily_monitor.yml close runs:
  portfolio_snapshots  → total + net_deposits + benchmark index levels
  holdings             → current positions (qty, price, value)
  holdings_alerts      → actionable alerts from the past 7 days
  discoveries          → BUY prospects from the past 7 days

Portfolio and benchmark 7-day returns are computed by comparing the latest
snapshot row to the one ~7 days earlier. Only the Claude recommendation
paragraph makes a live API call.
"""

import os
import json
import requests
import anthropic
from datetime import datetime, date, timezone, timedelta
from dotenv import load_dotenv

from lib.supabase_sink import _get_client

load_dotenv()

TELEGRAM_TOKEN   = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
CLAUDE_API_KEY   = os.getenv('CLAUDE_API_KEY')

# Benchmark 7d returns come from portfolio_snapshots columns, which
# daily_portfolio_snapshot.py writes every close run. No live price API —
# the digest is now 100% Supabase-sourced and never rate-limited.
BENCHMARK_COLS = [
    ('S&P 500',    'spx'),
    ('FTSE 100',   'ftse'),
    ('NASDAQ 100', 'ndx'),
    ('MSCI World', 'msci'),
    ('Gold',       'gold'),
]

TICKER_META = {
    'NVDA':   ('NVDA',       'Tech'),
    'GOOG':   ('GOOG',       'Tech'),
    'IITU':   ('IITU.L',     'Tech'),
    'RTX':    ('RTX',        'Defence'),
    'RHM':    ('RHM.DE',     'Defence'),
    'HO':     ('HO.PA',      'Defence'),
    'BA.':    ('BA.L',       'Defence'),
    'BRK.B':  ('BRK-B',      'Financials'),
    'LGEN':   ('LGEN.L',     'Financials'),
    'RIO':    ('RIO.L',      'Materials'),
    'TECK.B': ('TECK-B.TO',  'Materials'),
    'INRG':   ('INRG.L',     'Energy'),
    'SGLN':   ('SGLN.L',     'Commodities'),
    'VGER':   ('VGER.L',     'Broad ETF'),
    'VUSA':   ('VUSA.L',     'Broad ETF'),
    'ISP6':   ('ISP6.L',     'Broad ETF'),
    'EUE':    ('EUE.L',      'Broad ETF'),
}

SECTOR_ETF = {
    'Tech':        ('XLK', '💻'),
    'Defence':     ('ITA', '🛡'),
    'Materials':   ('XLB', '⛏'),
    'Financials':  ('XLF', '🏦'),
    'Energy':      ('XLU', '⚡'),
    'Commodities': (None,  '🪙'),
    'Broad ETF':   (None,  '🌐'),
}

SECTOR_CONCENTRATION_WARN = 30
ALERT_LOOKBACK_DAYS       = 7


# ── Helpers ────────────────────────────────────────────────────────────────────

def pct_str(val, decimals=1):
    sign = '+' if val >= 0 else '−'
    return f'{sign}{abs(val):.{decimals}f}%'


def escape_html(text):
    return str(text).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def send_telegram(text):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("  Telegram credentials not set — printing instead:\n")
        print(text)
        return False
    try:
        resp = requests.post(
            f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage',
            json={'chat_id': TELEGRAM_CHAT_ID, 'text': text, 'parse_mode': 'HTML'},
            timeout=15,
        )
        resp.raise_for_status()
        return True
    except Exception as e:
        print(f"  Telegram error: {e}")
        return False


def send_telegram_chunks(message):
    if len(message) <= 4096:
        return send_telegram(message)
    parts   = message.split('\n━━━')
    chunks  = []
    current = parts[0]
    for part in parts[1:]:
        candidate = current + '\n━━━' + part
        if len(candidate) <= 4000:
            current = candidate
        else:
            chunks.append(current)
            current = '━━━' + part
    chunks.append(current)
    ok = True
    for c in chunks:
        ok = send_telegram(c) and ok
    return ok


# ── Supabase readers ───────────────────────────────────────────────────────────

def load_recent_snapshots(days=14):
    """Portfolio snapshot rows from the last `days`, oldest first.
    One row per trading day, each carrying vadym_total, net_deposits and the
    benchmark index levels (spx/ftse/ndx/msci/gold)."""
    sb = _get_client()
    if not sb:
        return []
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).date().isoformat()
    try:
        resp = (
            sb.table('portfolio_snapshots')
            .select('*')
            .gte('date', cutoff)
            .order('date')
            .execute()
        )
        return resp.data or []
    except Exception as e:
        print(f"  portfolio_snapshots read failed: {e}")
        return []


def pick_prior_snapshot(snapshots, target_days=7):
    """The snapshot row closest to `target_days` before the latest one —
    the baseline for week-over-week comparison."""
    if len(snapshots) < 2:
        return None
    latest_date  = date.fromisoformat(snapshots[-1]['date'])
    target       = latest_date - timedelta(days=target_days)
    on_or_before = [s for s in snapshots[:-1]
                    if date.fromisoformat(s['date']) <= target]
    return on_or_before[-1] if on_or_before else snapshots[0]


def compute_portfolio_7d(latest, prior):
    """Deposit-adjusted weekly return — strips new money so the figure is pure
    market performance (matching what the old yfinance weighting produced)."""
    if not latest or not prior:
        return None
    t_now  = float(latest.get('vadym_total') or 0)
    t_then = float(prior.get('vadym_total') or 0)
    if t_then <= 0:
        return None
    nd_now      = float(latest.get('net_deposits') or 0)
    nd_then     = float(prior.get('net_deposits') or 0)
    market_gain = (t_now - t_then) - (nd_now - nd_then)
    return market_gain / t_then * 100


def compute_benchmark_7d(latest, prior):
    """7-day % change for each benchmark index, straight from snapshot columns."""
    out = []
    for name, col in BENCHMARK_COLS:
        pct = None
        if latest and prior:
            try:
                now  = float(latest.get(col) or 0)
                then = float(prior.get(col) or 0)
                if then > 0 and now > 0:
                    pct = (now - then) / then * 100
            except (TypeError, ValueError):
                pct = None
        out.append((name, pct))
    return out


def load_holdings():
    """Current holdings from Supabase."""
    sb = _get_client()
    if not sb:
        return []
    try:
        resp = sb.table('holdings').select('ticker,name,qty,current_price,value_gbp').execute()
        return resp.data or []
    except Exception as e:
        print(f"  holdings read failed: {e}")
        return []


def load_recent_alerts():
    """holdings_alerts from the past 7 days — one alert per ticker (most recent)."""
    sb = _get_client()
    if not sb:
        return []
    cutoff = (datetime.now(timezone.utc) - timedelta(days=ALERT_LOOKBACK_DAYS)).isoformat()
    try:
        resp = (
            sb.table('holdings_alerts')
            .select('ticker,alert_level,score,event,rationale,suggested_action,run_time')
            .gte('run_time', cutoff)
            .order('run_time', desc=True)
            .execute()
        )
        # Deduplicate: keep only the most recent alert per ticker
        seen   = set()
        unique = []
        for row in (resp.data or []):
            if row['ticker'] not in seen:
                seen.add(row['ticker'])
                unique.append(row)
        return unique
    except Exception as e:
        print(f"  holdings_alerts read failed: {e}")
        return []


def load_recent_discoveries():
    """BUY discoveries from the past 7 days."""
    sb = _get_client()
    if not sb:
        return []
    cutoff = (datetime.now(timezone.utc) - timedelta(days=ALERT_LOOKBACK_DAYS)).isoformat()
    try:
        resp = (
            sb.table('discoveries')
            .select('ticker,score,rationale,run_time')
            .eq('recommendation', 'BUY')
            .gte('run_time', cutoff)
            .order('score', desc=True)
            .execute()
        )
        # Deduplicate by ticker
        seen   = set()
        unique = []
        for row in (resp.data or []):
            if row['ticker'] not in seen:
                seen.add(row['ticker'])
                unique.append(row)
        return unique
    except Exception as e:
        print(f"  discoveries read failed: {e}")
        return []


# ── Holdings classification ────────────────────────────────────────────────────

def classify_alert(alert):
    """Map a holdings_alerts row → (label, icon, note)."""
    action = (alert.get('suggested_action') or '').upper()
    level  = (alert.get('alert_level') or '').upper()
    event  = (alert.get('event') or '').strip()
    rat    = (alert.get('rationale') or '').strip()
    note   = event or rat[:80]

    if action == 'BUY_MORE':
        return ('BUY_MORE', '📈', note)
    if action in ('SELL', 'EXIT', 'TRIM') or (level == 'ACT' and action not in ('BUY_MORE',)):
        return ('CONSIDER_SELL', '📉', note)
    is_earnings = 'earning' in (event or '').lower()
    return ('WATCH', '📅' if is_earnings else '👀', note)


# ── Section builders ───────────────────────────────────────────────────────────

def build_portfolio_section(summary, portfolio_7d):
    total = float(summary.get('vadym_total') or 0)
    lines = ['━━━ <b>PORTFOLIO</b> ━━━']
    if portfolio_7d is not None:
        wow_gbp = total * portfolio_7d / 100
        sign    = '+' if portfolio_7d >= 0 else '−'
        lines.append(
            f'Total: <b>£{total:,.0f}</b>  ({sign}£{abs(wow_gbp):,.0f} / {pct_str(portfolio_7d)} WoW)'
        )
    else:
        lines.append(f'Total: <b>£{total:,.0f}</b>')
    return '\n'.join(lines)


def build_benchmarks_section(portfolio_7d, bench_returns):
    lines = ['━━━ <b>BENCHMARKS (7d %)</b> ━━━', '<pre>']
    if portfolio_7d is not None:
        emoji = '🟢' if portfolio_7d >= 0 else '🔴'
        lines.append(f'{emoji} You:         {pct_str(portfolio_7d)}')
    beat_count = 0
    total      = 0
    for name, pct in bench_returns:
        if pct is None:
            lines.append(f'⚪ {name:<12} n/a')
            continue
        total += 1
        emoji = '🟢' if pct >= 0 else '🔴'
        beat  = ''
        if portfolio_7d is not None and portfolio_7d > pct:
            beat = '   ← beat'
            beat_count += 1
        lines.append(f'{emoji} {f"{name}:".ljust(13)}{pct_str(pct)}{beat}')
    lines.append('</pre>')
    if portfolio_7d is not None and total > 0:
        lines.append(f'<b>Beat {beat_count} of {total} benchmarks {"✅" if beat_count >= total/2 else "⚠"}</b>')
    return '\n'.join(lines)


def build_holdings_section(alerts):
    if not alerts:
        return '━━━ <b>HOLDINGS</b> ━━━\n<i>No actionable alerts this week.</i>'

    buckets = {'BUY_MORE': [], 'CONSIDER_SELL': [], 'WATCH': []}
    for alert in alerts:
        label, icon, note = classify_alert(alert)
        score = float(alert.get('score') or 5)
        buckets[label].append((alert['ticker'], score, icon, note))

    buckets['BUY_MORE'].sort(key=lambda x: -x[1])
    buckets['CONSIDER_SELL'].sort(key=lambda x: x[1])
    buckets['WATCH'].sort(key=lambda x: -x[1])

    out = ['━━━ <b>HOLDINGS</b> ━━━']

    for title, key in [
        ('🚀 <b>BUY MORE</b>',       'BUY_MORE'),
        ('⚠️ <b>CONSIDER SELL</b>',  'CONSIDER_SELL'),
        ('👀 <b>WATCH</b>',          'WATCH'),
    ]:
        rows = buckets[key]
        if not rows:
            continue
        block = [f'\n{title}']
        for ticker, score, icon, note in rows:
            s = f'{score:.0f}' if float(score).is_integer() else f'{score:.1f}'
            block.append(f'{icon} <b>{escape_html(ticker)}</b>  {s}/10')
            if note:
                block.append(f'  <i>{escape_html(note[:100])}</i>')
        out.append('\n'.join(block))

    return '\n'.join(out)


def build_sector_section(holdings):
    sector_value = {}
    total_value  = 0.0
    for h in holdings:
        ticker = h.get('ticker')
        if ticker not in TICKER_META:
            continue
        sector = TICKER_META[ticker][1]
        if sector in ('Broad ETF', 'Commodities'):
            continue
        value = float(h.get('qty') or 0) * float(h.get('current_price') or 0)
        sector_value[sector] = sector_value.get(sector, 0) + value
        total_value += value

    if total_value == 0:
        return ''

    lines = [
        '━━━ <b>SECTOR ALLOCATION</b> ━━━',
        '<pre>',
    ]
    warn_sectors = []
    for sector, value in sorted(sector_value.items(), key=lambda x: -x[1]):
        pct_alloc = value / total_value * 100
        icon      = SECTOR_ETF.get(sector, (None, '📊'))[1]
        warn      = '⚠' if pct_alloc >= SECTOR_CONCENTRATION_WARN else ' '
        if pct_alloc >= SECTOR_CONCENTRATION_WARN:
            warn_sectors.append(sector)
        lines.append(f'{f"{icon} {sector}".ljust(15)} {pct_alloc:>4.0f}%{warn}')
    lines.append('</pre>')
    if warn_sectors:
        lines.append(f'⚠ Concentration: {", ".join(warn_sectors)} &gt; {SECTOR_CONCENTRATION_WARN}%.')
    return '\n'.join(lines)


def build_discovery_section(discoveries):
    top3 = [d for d in discoveries if float(d.get('score') or 0) >= 6][:3]
    if not top3:
        return ''
    lines = ['━━━ <b>DISCOVERY (top 3)</b> ━━━', '<pre>']
    for i, d in enumerate(top3, 1):
        score = float(d.get('score') or 0)
        note  = (d.get('rationale') or '')[:38]
        s     = f'{score:.0f}' if float(score).is_integer() else f'{score:.1f}'
        lines.append(f'{i}. {d["ticker"]:<6}{s:>3}  {note}')
    lines.append('</pre>')
    return '\n'.join(lines)


def build_recommendation(summary, portfolio_7d, bench_returns, alerts, discoveries):
    if not CLAUDE_API_KEY:
        return ''

    alert_lines = [
        f"{a['ticker']} ({classify_alert(a)[0]}): {(a.get('event') or a.get('rationale') or '')[:80]}"
        for a in alerts
    ]
    bench_lines = [f"{n}: {pct_str(p)}" for n, p in bench_returns if p is not None]
    disc_lines  = [
        f"{d['ticker']} (score {d.get('score')}): {(d.get('rationale') or '')[:60]}"
        for d in discoveries[:3]
    ]
    total = float(summary.get('vadym_total') or 0)

    prompt = f"""You are writing the closing paragraph of a weekly portfolio digest for a UK retail investor.

CONTEXT (this week):
Portfolio 7d: {pct_str(portfolio_7d) if portfolio_7d is not None else 'n/a'}
Total value: £{total:,.0f}

BENCHMARKS (7d):
{chr(10).join(bench_lines) if bench_lines else '(none)'}

HOLDINGS ALERTS (last 7 days):
{chr(10).join(alert_lines) if alert_lines else '(none — all holdings steady)'}

DISCOVERY CANDIDATES:
{chr(10).join(disc_lines) if disc_lines else '(none)'}

Write a single paragraph, 3–5 sentences, ~80 words max. Reference the most important
holdings by ticker. Be concrete (e.g. "trim NVDA 20%", "set stop-loss on BA.",
"watch RTX earnings"). If the user beat most benchmarks, say so briefly. If there
are concentration risks or earnings-heavy weeks ahead, flag them. End with one
concrete prospect suggestion if discovery is strong. Plain prose, no bullet points,
no markdown. Do NOT start with "Here's" or "This week".
"""
    try:
        msg = anthropic.Anthropic(api_key=CLAUDE_API_KEY).messages.create(
            model='claude-sonnet-4-6',
            max_tokens=300,
            messages=[{'role': 'user', 'content': prompt}],
        )
        return msg.content[0].text.strip()
    except Exception as e:
        print(f"  Claude recommendation failed: {e}")
        return ''


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    print("=== digest_worker ===")

    print("\nLoading data from Supabase...")
    snapshots   = load_recent_snapshots(14)
    summary     = snapshots[-1] if snapshots else {}
    prior       = pick_prior_snapshot(snapshots)
    holdings    = load_holdings()
    alerts      = load_recent_alerts()
    discoveries = load_recent_discoveries()

    print(f"  Snapshots loaded: {len(snapshots)}"
          f" ({snapshots[0]['date']}..{snapshots[-1]['date']})" if snapshots else "  Snapshots loaded: 0")
    print(f"  Portfolio total:  £{float(summary.get('vadym_total') or 0):,.2f}")
    print(f"  WoW baseline:     {prior['date'] if prior else 'n/a'}")
    print(f"  Holdings:         {len(holdings)} positions")
    print(f"  Alerts (7d):      {len(alerts)}")
    print(f"  Discoveries (7d): {len(discoveries)}")

    print("\nComputing WoW returns from snapshots...")
    portfolio_7d  = compute_portfolio_7d(summary, prior)
    bench_returns = compute_benchmark_7d(summary, prior)
    print(f"  Portfolio 7d: {f'{portfolio_7d:.2f}%' if portfolio_7d is not None else 'n/a'}")
    for name, pct in bench_returns:
        print(f"  {name}: {f'{pct:.2f}%' if pct is not None else 'n/a'}")

    print("\nBuilding sections...")
    header = (
        '📊 <b>WEEKLY DIGEST</b>\n'
        f'<i>{datetime.now(timezone.utc).strftime("%d %b %Y")}</i>'
    )
    sections = [
        header,
        build_portfolio_section(summary, portfolio_7d),
        build_benchmarks_section(portfolio_7d, bench_returns),
        build_holdings_section(alerts),
        build_sector_section(holdings),
        build_discovery_section(discoveries),
    ]

    print("\nGenerating LLM recommendation...")
    rec = build_recommendation(summary, portfolio_7d, bench_returns, alerts, discoveries)
    if rec:
        sections.append(f'━━━ <b>RECOMMENDATION</b> ━━━\n<i>{escape_html(rec)}</i>')

    message = '\n\n'.join(s for s in sections if s)
    print(f"\nDigest assembled ({len(message)} chars). Sending to Telegram...")
    send_telegram_chunks(message)
    print("Done.")


if __name__ == '__main__':
    main()
