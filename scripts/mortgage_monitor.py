#!/usr/bin/env python3
"""
mortgage_monitor.py — weekly UK mortgage market monitor (real data only).

Pulls live data from real sources, computes every payment figure
deterministically in Python, and asks Claude only to interpret the news and
recommend an action — Claude is never allowed to supply a rate. Saves a
markdown report plus a JSON sidecar to mortgage/market-snapshots/ and sends a
real-data summary to Telegram.

Data sources (see scripts/lib/mortgage_rates.py):
  • Bank of England database — base rate + quoted lender rates
  • Bank of England MPC schedule
  • Marketaux — market news

Note: best-buy scraping (Moneyfacts) was removed in the 2026-06 hotfix — the
scrape was unreliable for best-buy picks and produced misleading figures. The
report now shows BoE market-average 2yr/5yr fixed rates only, with a
week-over-week comparison.

Run:
  python3 scripts/mortgage_monitor.py
  python3 scripts/mortgage_monitor.py --dry-run   # print only, no send/write
"""

import os
import sys
import json
import requests
import anthropic
from datetime import datetime, timezone, timedelta
from pathlib import Path
from dotenv import load_dotenv

from lib.mortgage_rates import (
    fetch_boe_base_rate,
    fetch_boe_quoted_rates,
    fetch_mpc_dates,
    monthly_payment,
    remaining_term_months,
)

load_dotenv()

MARKETAUX_KEY    = os.getenv('MARKETAUX_API_KEY', '')
CLAUDE_API_KEY   = os.getenv('CLAUDE_API_KEY', '')
TELEGRAM_TOKEN   = os.getenv('TELEGRAM_BOT_TOKEN', '')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', '')

SNAPSHOTS_DIR = Path('mortgage/market-snapshots')
TODAY         = datetime.now(timezone.utc).strftime('%Y-%m-%d')
REPORT_PATH   = SNAPSHOTS_DIR / f'{TODAY}-report.md'
DATA_PATH     = SNAPSHOTS_DIR / f'{TODAY}-data.json'

# ── Vadym & Lisa's current mortgage ───────────────────────────────────────────
CURRENT_RATE     = 0.0526          # 5.26% fixed
CURRENT_PAYMENT  = 3072.00         # £/month
CURRENT_LENDER   = 'Co-operative Bank'
PROPERTY_VALUE   = 650000.00       # revalued down from £660k, 2026-07-11
FALLBACK_BALANCE = 552371.48       # confirmed by bank statement, 1 Apr 2026
FIX_ENDS         = '31 January 2027'


SYSTEM_PROMPT = """You are the mortgage-market monitoring agent for Vadym and Lisa, a UK couple \
remortgaging when their current fix ends 31 January 2027 (their 6-month early-switch window has \
been open since April 2026; their broker is Oliver).

CRITICAL RULE: every market figure you need is given to you below as VERIFIED real data — the \
market-average 2yr/5yr fixed rates and their week-over-week change, the payments, the Bank of \
England base rate, quoted-rate trend, and MPC dates. Use those exact figures. Never invent, \
re-estimate, round differently, or override any rate, payment, or date. Do not quote any "best-buy" \
or named-lender headline deal — those are no longer tracked here; if you want one, tell them to ask \
Oliver. If a figure is marked unavailable, say so plainly and tell them to confirm with Oliver — do \
not fill the gap with a guess.

YOUR JOB: return Markdown containing EXACTLY these two sections and nothing else (no preamble, no \
title, no closing line):

## 📰 Key News (past 7 days)

One to three bullets. Each: the headline, then ' — ' and a one-line implication for Vadym & Lisa. \
If no genuinely relevant UK mortgage news was supplied, write a single line saying so.

## ✅ Recommended Action

Open with a bold verdict on its own line — one of: **No action needed**, **Start preparing**, or \
**Act now**. Then 2–4 sentences grounded in their actual numbers: compare the market-average rates \
against their current 5.26% and the resulting £/month difference; note the week-over-week move in \
those averages (rising or falling, and by how many bps); weigh the 2-year vs 5-year trade-off \
(Vadym prefers the 2-year for flexibility — name the rate gap between them; the two fixed terms are \
exactly 2 years and 5 years, never describe them as any other length); factor the Bank of England \
trajectory and the next MPC date; and remember they are planning children, so a single-income \
period must remain affordable. Be honest about uncertainty — do not predict rate moves with false \
confidence.

Context for your judgement: the rates shown are Bank of England market-wide quoted averages at \
~85% LTV — they sit above the sharpest broker deals, so treat them as a direction-of-travel \
indicator, not a quote. True eligibility and total cost still need Oliver.
"""


# ── helpers ───────────────────────────────────────────────────────────────────

def fmt_date(iso: str) -> str:
    try:
        return datetime.strptime(iso, '%Y-%m-%d').strftime('%-d %b %Y')
    except (ValueError, TypeError):
        return iso or '—'


def month_label(iso: str) -> str:
    try:
        return datetime.strptime(iso, '%Y-%m-%d').strftime('%b %Y')
    except (ValueError, TypeError):
        return iso or '—'


def days_until(iso: str):
    try:
        target = datetime.strptime(iso, '%Y-%m-%d').date()
        return (target - datetime.now(timezone.utc).date()).days
    except (ValueError, TypeError):
        return None


# ── data gathering ────────────────────────────────────────────────────────────

def current_balance() -> float:
    """Latest mortgage balance from Supabase; falls back to the confirmed figure."""
    url = os.getenv('SUPABASE_URL', '')
    key = os.getenv('SUPABASE_SERVICE_ROLE_KEY', '')
    if url and key:
        try:
            from supabase import create_client
            client = create_client(url, key)
            res = (client.table('mortgage_snapshots').select('balance, date')
                   .order('date', desc=True).limit(1).execute())
            if res.data:
                return float(res.data[0]['balance'])
        except Exception as exc:
            print(f"  Supabase balance lookup failed ({exc}) — using fallback")
    return FALLBACK_BALANCE


def save_insight(data: dict, report_md: str, telegram_text: str) -> None:
    """Persist this run's report to Supabase so the Insights web page can show it."""
    url = os.getenv('SUPABASE_URL', '')
    key = os.getenv('SUPABASE_SERVICE_ROLE_KEY', '')
    if not (url and key):
        print("  Supabase not configured — insight not saved")
        return
    try:
        from supabase import create_client
        client = create_client(url, key)
        triggered = 'manual' if os.getenv('TRIGGER_SOURCE') == 'workflow_dispatch' else 'schedule'
        client.table('mortgage_insights').insert({
            'report_date':      data['date'],
            'report_md':        report_md,
            'telegram_text':    telegram_text,
            'base_rate':        data.get('base_rate', {}).get('rate'),
            'avg_2yr_rate':     data.get('avg_2yr_rate'),
            'avg_5yr_rate':     data.get('avg_5yr_rate'),
            'avg_2yr_wow_bps':  data.get('avg_2yr_wow_bps'),
            'avg_5yr_wow_bps':  data.get('avg_5yr_wow_bps'),
            'next_mpc':         (data.get('mpc_dates') or [None])[0],
            'triggered_by':     triggered,
            'data':             json.loads(json.dumps(data, default=str)),
        }).execute()
        print(f"  Insight saved to Supabase ({triggered})")
    except Exception as exc:
        print(f"  Supabase insight save failed: {exc}")


def fetch_mortgage_news() -> list:
    if not MARKETAUX_KEY:
        print("  No MARKETAUX_API_KEY — skipping news fetch")
        return []

    cutoff = (datetime.now(timezone.utc) - timedelta(days=8)).strftime('%Y-%m-%dT%H:%M')
    articles, queries = [], [
        'UK mortgage rates fixed',
        'Bank of England base rate MPC',
        'UK remortgage lender rates',
    ]
    for query in queries:
        try:
            resp = requests.get(
                'https://api.marketaux.com/v1/news/all',
                params={
                    'search': query, 'language': 'en',
                    'published_after': cutoff, 'limit': 5,
                    'api_token': MARKETAUX_KEY,
                },
                timeout=15,
            )
            resp.raise_for_status()
            for item in resp.json().get('data', []):
                articles.append({
                    'title':       item.get('title', ''),
                    'description': item.get('description', ''),
                    'source':      item.get('source', ''),
                    'published':   item.get('published_at', '')[:10],
                    'url':         item.get('url', ''),
                })
        except Exception as exc:
            print(f"  Marketaux error ({query}): {exc}")

    seen, unique = set(), []
    for a in articles:
        if a['title'] and a['title'] not in seen:
            seen.add(a['title'])
            unique.append(a)
    return unique


def _boe_avg_rates(quoted: dict) -> tuple[float | None, float | None]:
    """
    Market-average 2yr and 5yr fixed rates at ~85% LTV, derived from BoE quoted
    series.  We interpolate the midpoint of the 75% and 90% LTV bands, which
    bracket the ~85% LTV at which Vadym & Lisa sit.  BoE data lags ~1–2 months
    behind live best-buy deals but is the most authoritative market-wide average.
    Returns (avg_2yr, avg_5yr) with None where data is missing.
    """
    if 'error' in quoted:
        return None, None
    by_label_ltv: dict[tuple, float] = {}
    for s in quoted.get('series', []):
        if s.get('rate') is not None:
            by_label_ltv[(s['label'], s['ltv'])] = s['rate']
    r2_75 = by_label_ltv.get(('2-year fixed', 75))
    r2_90 = by_label_ltv.get(('2-year fixed', 90))
    r5_75 = by_label_ltv.get(('5-year fixed', 75))
    r5_90 = by_label_ltv.get(('5-year fixed', 90))
    avg_2yr = round((r2_75 + r2_90) / 2, 2) if r2_75 and r2_90 else None
    avg_5yr = round((r5_75 + r5_90) / 2, 2) if r5_75 and r5_90 else None
    return avg_2yr, avg_5yr


def gather_data() -> dict:
    """Collect every real figure the report needs into one dict."""
    balance = current_balance()
    term = remaining_term_months(balance, CURRENT_RATE, CURRENT_PAYMENT)

    base_rate   = fetch_boe_base_rate()
    quoted      = fetch_boe_quoted_rates()
    mpc_dates   = fetch_mpc_dates()
    news        = fetch_mortgage_news()

    avg_2yr, avg_5yr = _boe_avg_rates(quoted)
    # Estimated monthly payments at average rates (same term, same balance).
    avg_2yr_payment = round(monthly_payment(balance, avg_2yr / 100, term)) if avg_2yr and term else None
    avg_5yr_payment = round(monthly_payment(balance, avg_5yr / 100, term)) if avg_5yr and term else None

    return {
        'date':            TODAY,
        'balance':         round(balance, 2),
        'ltv':             round(balance / PROPERTY_VALUE * 100, 1),
        'remaining_term':  term,
        'base_rate':       base_rate,
        'quoted':          quoted,
        'mpc_dates':       mpc_dates,
        'avg_2yr_rate':    avg_2yr,
        'avg_5yr_rate':    avg_5yr,
        'avg_2yr_payment': avg_2yr_payment,
        'avg_5yr_payment': avg_5yr_payment,
        # Week-over-week fields are filled in by add_wow_deltas() once the prior
        # snapshot has been loaded.
        'prev_avg_2yr_rate': None,
        'prev_avg_5yr_rate': None,
        'avg_2yr_wow_bps':   None,
        'avg_5yr_wow_bps':   None,
        'news':            news,
    }


def add_wow_deltas(data: dict, prev: dict | None) -> None:
    """Fill week-over-week average-rate deltas from the previous snapshot, in place.

    bps delta is rounded to the nearest basis point; positive = rates rose since
    last week, negative = fell. Left as None when either side is missing."""
    for term in ('2yr', '5yr'):
        now = data.get(f'avg_{term}_rate')
        was = (prev or {}).get(f'avg_{term}_rate')
        data[f'prev_avg_{term}_rate'] = was
        if now is not None and was is not None:
            data[f'avg_{term}_wow_bps'] = round((now - was) * 100)


def fmt_wow(bps) -> str:
    """Human label for a week-over-week bps move, e.g. '↑ +5bps', '↓ -5bps', '→ flat'."""
    if bps is None:
        return ''
    if bps == 0:
        return '→ flat vs last week'
    arrow = '↑' if bps > 0 else '↓'
    return f"{arrow} {'+' if bps > 0 else ''}{bps}bps vs last week"


# ── deterministic report sections ─────────────────────────────────────────────

def render_snapshot(data: dict) -> str:
    lines = ['## 🏦 Market-Average Rate Snapshot (~85% LTV)', '']

    avg_2yr = data.get('avg_2yr_rate')
    avg_5yr = data.get('avg_5yr_rate')
    if not (avg_2yr or avg_5yr):
        lines += [
            "> ⚠️ Market-average rates could not be derived this run "
            "(BoE quoted-rate series unavailable). Ask Oliver for a live rate table.", '']
        return '\n'.join(lines)

    lines += [
        f"*Bank of England market-average quoted fixed rates at ~85% LTV "
        f"(midpoint of the 75% and 90% bands), as of {fmt_date(TODAY)}. "
        "BoE data lags live broker deals by ~1–2 months and runs above the sharpest "
        "deals — treat as direction of travel, not a quote.*", '',
        '| Product | Rate | WoW change | Est. Monthly Payment\\* |',
        '|---|---|---|---|',
    ]
    avg_2yr_pay = data.get('avg_2yr_payment')
    avg_5yr_pay = data.get('avg_5yr_payment')
    for label, rate, pay, bps in (
        ('2-year fixed', avg_2yr, avg_2yr_pay, data.get('avg_2yr_wow_bps')),
        ('5-year fixed', avg_5yr, avg_5yr_pay, data.get('avg_5yr_wow_bps')),
    ):
        rate_str = f"{rate:.2f}%" if rate else '—'
        pay_str  = f"~£{pay:,}" if pay else '—'
        wow_str  = fmt_wow(bps) or '—'
        lines.append(f"| {label} | {rate_str} | {wow_str} | {pay_str} |")

    term = data['remaining_term']
    lines += [
        '',
        f"\\*Estimated on the current balance of £{data['balance']:,.0f} over "
        f"{term} months remaining — like-for-like with the current £{CURRENT_PAYMENT:,.0f}/month.",
        '',
        f"*Current deal: {CURRENT_RATE * 100:.2f}% fixed ({CURRENT_LENDER}) → "
        f"£{CURRENT_PAYMENT:,.0f}/month. Fix ends {FIX_ENDS}. "
        f"Balance £{data['balance']:,.0f}, property £{PROPERTY_VALUE:,.0f}, LTV ~{data['ltv']}%.*",
        '',
    ]
    for label, rate, pay in (('2-year', avg_2yr, avg_2yr_pay), ('5-year', avg_5yr, avg_5yr_pay)):
        if rate and pay:
            diff = round(CURRENT_PAYMENT - pay)
            verb = 'saves' if diff >= 0 else 'costs an extra'
            lines.append(
                f"- At the average {label} fixed rate, remortgaging {verb} "
                f"~£{abs(diff):,}/month vs. the current payment.")
    lines.append('')
    return '\n'.join(lines)


def render_boe(data: dict) -> str:
    br = data['base_rate']
    lines = ['## 📊 Bank of England', '']

    if 'error' in br:
        lines.append(f"> ⚠️ Base rate could not be retrieved this run ({br['error']}).")
    else:
        lines.append(f"- **Base rate:** {br['rate']:.2f}% — official, as of {fmt_date(br['as_of'])}")
        if br.get('previous_rate') is not None:
            move = 'cut' if br['rate'] < br['previous_rate'] else 'rise'
            lines.append(
                f"- **Last changed:** {fmt_date(br['last_change'])} "
                f"({br['previous_rate']:.2f}% → {br['rate']:.2f}%, a {move})")
        else:
            lines.append(f"- **Last changed:** {fmt_date(br['last_change'])}")

    mpc = data['mpc_dates']
    if mpc:
        nxt = mpc[0]
        d = days_until(nxt)
        flag = ' ⚠️' if d is not None and d <= 14 else ''
        when = f" ({d} days away)" if d is not None else ''
        lines.append(f"- **Next MPC decision:** {fmt_date(nxt)}{when}{flag}")
        if len(mpc) > 1:
            lines.append(f"- **Following meeting:** {fmt_date(mpc[1])}")
    lines.append('')
    return '\n'.join(lines)


def render_quoted_trend(data: dict) -> str:
    q = data['quoted']
    lines = ['## 📈 BoE Quoted-Rate Trend', '']
    if 'error' in q:
        lines += [f"> ⚠️ Quoted-rate data could not be retrieved this run ({q['error']}).", '']
        return '\n'.join(lines)

    lines += [
        f"*Average rate quoted across UK lenders — Bank of England, "
        f"{month_label(q['prev_as_of'])} → {month_label(q['as_of'])}. These run above the sharpest "
        "broker deals; shown to indicate market direction.*", '',
        '| Term / LTV band | ' + month_label(q['prev_as_of']) +
        ' | ' + month_label(q['as_of']) + ' | Change |',
        '|---|---|---|---|',
    ]
    for s in q['series']:
        cur = f"{s['rate']:.2f}%" if s['rate'] is not None else '—'
        prev = f"{s['prev_rate']:.2f}%" if s['prev_rate'] is not None else '—'
        if s['rate'] is not None and s['prev_rate'] is not None:
            bp = round((s['rate'] - s['prev_rate']) * 100)
            chg = f"{'+' if bp >= 0 else ''}{bp} bp"
        else:
            chg = '—'
        lines.append(f"| {s['label']}, {s['ltv']}% LTV | {prev} | {cur} | {chg} |")

    lines += ['',
              f"*Vadym & Lisa's ~{data['ltv']}% LTV sits between the 75% and 90% bands — "
              "closer to the 90% figure.*",
              '']
    return '\n'.join(lines)


def render_change(data: dict, prev: dict) -> str:
    lines = ['## 🔄 Change vs. Last Snapshot', '']
    if not prev:
        lines += ['First snapshot with the real-data monitor — no prior run to compare against.', '']
        return '\n'.join(lines)

    lines[0] = f"## 🔄 Change vs. Last Snapshot ({fmt_date(prev.get('date'))})"

    for label, key in (('2-year fixed avg', 'avg_2yr_rate'),
                        ('5-year fixed avg', 'avg_5yr_rate')):
        now, was = data.get(key), prev.get(key)
        if now is not None and was is not None:
            bp = round((now - was) * 100)
            if bp == 0:
                lines.append(f"- {label}: unchanged at {now:.2f}%")
            else:
                lines.append(
                    f"- {label}: {now:.2f}% (was {was:.2f}%) — "
                    f"**{'up' if bp > 0 else 'down'} {abs(bp)} bp**")
        elif now is not None:
            lines.append(f"- {label}: {now:.2f}% (no comparable figure last run)")

    now_br = data.get('base_rate', {}).get('rate')
    was_br = prev.get('base_rate', {}).get('rate')
    if now_br is not None and was_br is not None:
        if now_br == was_br:
            lines.append(f"- BoE base rate: unchanged at {now_br:.2f}%")
        else:
            lines.append(
                f"- BoE base rate: {now_br:.2f}% (was {was_br:.2f}%) — "
                f"**{'cut' if now_br < was_br else 'raised'}**")
    lines.append('')
    return '\n'.join(lines)


def render_footer() -> str:
    return (
        '---\n\n'
        f"*Generated automatically on {fmt_date(TODAY)}. Sources: Bank of England "
        "database (base rate IUDBEDR and quoted-rate series); Bank of England MPC "
        "schedule; Marketaux (news). Rates shown are BoE market-wide quoted averages "
        "at ~85% LTV — confirm live deals, eligibility and total cost with broker "
        "Oliver before acting.*"
    )


# ── Claude: news interpretation + recommendation ──────────────────────────────

def generate_interpretation(report_so_far: str, news: list) -> str:
    if not CLAUDE_API_KEY:
        return ("## 📰 Key News (past 7 days)\n\n*Claude API key not configured — "
                "news interpretation skipped.*\n\n## ✅ Recommended Action\n\n"
                "**Start preparing** — review the verified figures above with Oliver.")

    client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
    parts = [
        "Here is the verified market data for this week's report. Every number below is real.\n",
        report_so_far,
        "\n\n## News articles fetched (past 8 days)\n",
    ]
    if news:
        for i, a in enumerate(news, 1):
            parts.append(
                f"{i}. **{a['title']}** ({a['source']}, {a['published']})\n"
                f"   {a['description']}\n")
    else:
        parts.append("No news articles were returned by the news feed this week.\n")
    parts.append("\nNow write the two sections exactly as instructed.")

    message = client.messages.create(
        model='claude-sonnet-4-6',
        max_tokens=1500,
        system=SYSTEM_PROMPT,
        messages=[{'role': 'user', 'content': '\n'.join(parts)}],
    )
    return message.content[0].text.strip()


# ── Telegram ──────────────────────────────────────────────────────────────────

def extract_recommendation(interpretation: str) -> str:
    marker = '## ✅ Recommended Action'
    if marker in interpretation:
        body = interpretation.split(marker, 1)[1]
        clean = body.replace('**', '').replace('*', '').strip()
        return clean
    return ''


def build_telegram_summary(data: dict, interpretation: str) -> str:
    lines = [f'🏦 Mortgage Monitor — {fmt_date(TODAY)}', '']

    avg_2yr = data.get('avg_2yr_rate')
    avg_5yr = data.get('avg_5yr_rate')
    avg_2yr_pay = data.get('avg_2yr_payment')
    avg_5yr_pay = data.get('avg_5yr_payment')
    if avg_2yr or avg_5yr:
        lines.append('Market avg (BoE quoted, ~85% LTV):')
        if avg_2yr:
            pay = f" → ~£{avg_2yr_pay:,}/mo" if avg_2yr_pay else ''
            wow = fmt_wow(data.get('avg_2yr_wow_bps'))
            wow = f"  {wow}" if wow else ''
            lines.append(f"  2yr fixed: {avg_2yr:.2f}%{pay}{wow}")
        if avg_5yr:
            pay = f" → ~£{avg_5yr_pay:,}/mo" if avg_5yr_pay else ''
            wow = fmt_wow(data.get('avg_5yr_wow_bps'))
            wow = f"  {wow}" if wow else ''
            lines.append(f"  5yr fixed: {avg_5yr:.2f}%{pay}{wow}")
        lines.append(f"  vs current: {CURRENT_RATE * 100:.2f}%, £{CURRENT_PAYMENT:,.0f}/mo")
    else:
        lines.append('Market-average rates: unavailable this run — check with Oliver.')

    br = data['base_rate']
    if 'error' not in br:
        lines.append(f"\nBoE base rate: {br['rate']:.2f}% "
                     f"(since {fmt_date(br['last_change'])})")
    if data['mpc_dates']:
        d = days_until(data['mpc_dates'][0])
        when = f" — {d} days" if d is not None else ''
        lines.append(f"Next MPC: {fmt_date(data['mpc_dates'][0])}{when}")

    rec = extract_recommendation(interpretation)
    if rec:
        lines.append(f"\n✅ {rec[:500]}")

    lines.append('\nFull report saved to repo.')
    return '\n'.join(lines)


def send_telegram(text: str) -> None:
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("  Telegram not configured — summary printed above")
        return
    safe = text if len(text) <= 4096 else text[:4090] + '…'
    try:
        resp = requests.post(
            f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage',
            json={'chat_id': TELEGRAM_CHAT_ID, 'text': safe},
            timeout=10,
        )
        resp.raise_for_status()
    except Exception as exc:
        print(f"  Telegram error: {exc}")


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    dry_run = '--dry-run' in sys.argv
    print(f"=== Mortgage Monitor — {TODAY}{' (dry run)' if dry_run else ''} ===")

    print("Gathering real market data...")
    data = gather_data()
    br = data['base_rate']
    print(f"  Base rate: {'OK' if 'error' not in br else br['error']}")
    print(f"  Quoted:    {'OK' if 'error' not in data['quoted'] else data['quoted']['error']}")
    avg_ok = 'OK' if (data['avg_2yr_rate'] or data['avg_5yr_rate']) else 'unavailable'
    print(f"  Avg rates: {avg_ok} (2yr {data['avg_2yr_rate']}, 5yr {data['avg_5yr_rate']})")
    print(f"  News:      {len(data['news'])} articles")

    prev = None
    for path in sorted(SNAPSHOTS_DIR.glob('*-data.json'), reverse=True):
        if path.name != DATA_PATH.name:
            try:
                prev = json.loads(path.read_text())
                break
            except Exception:
                pass

    add_wow_deltas(data, prev)
    print(f"  WoW:       2yr {fmt_wow(data['avg_2yr_wow_bps']) or 'n/a'}, "
          f"5yr {fmt_wow(data['avg_5yr_wow_bps']) or 'n/a'}")

    deterministic = '\n'.join([
        f'# Mortgage Market Monitor — {fmt_date(TODAY)}',
        '',
        render_snapshot(data),
        render_boe(data),
        render_quoted_trend(data),
        render_change(data, prev),
    ])

    print("Asking Claude to interpret news and recommend an action...")
    try:
        interpretation = generate_interpretation(deterministic, data['news'])
    except Exception as exc:
        print(f"  Claude error: {exc}")
        interpretation = ("## 📰 Key News (past 7 days)\n\n*Interpretation unavailable "
                           f"this run ({exc}).*\n\n## ✅ Recommended Action\n\n"
                           "**Start preparing** — review the verified figures above with Oliver.")

    report = f"{deterministic}\n{interpretation}\n\n{render_footer()}\n"
    print('\n' + report)

    if dry_run:
        print("Dry run — not writing files or sending Telegram.")
        return

    SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(report)
    DATA_PATH.write_text(json.dumps(data, indent=2, default=str))
    print(f"Report saved to {REPORT_PATH}")
    print(f"Data saved to   {DATA_PATH}")

    summary = build_telegram_summary(data, interpretation)

    print("Saving insight to Supabase...")
    save_insight(data, report, summary)

    print("Sending summary to Telegram...")
    print(f"  Summary length: {len(summary)} chars")
    send_telegram(summary)
    print("Done.")


if __name__ == '__main__':
    main()
