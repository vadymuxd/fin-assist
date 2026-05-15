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
  • Moneyfacts — live best-buy deals at the 85% LTV tier
  • Marketaux — market news

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
    fetch_best_buy_rates,
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
PROPERTY_VALUE   = 660000.00
FALLBACK_BALANCE = 552371.48       # confirmed by bank statement, 1 Apr 2026
FIX_ENDS         = '31 January 2027'


SYSTEM_PROMPT = """You are the mortgage-market monitoring agent for Vadym and Lisa, a UK couple \
remortgaging when their current fix ends 31 January 2027 (their 6-month early-switch window has \
been open since April 2026; their broker is Oliver).

CRITICAL RULE: every market figure you need is given to you below as VERIFIED real data — best-buy \
rates, payments, the Bank of England base rate, quoted-rate trend, and MPC dates. Use those exact \
figures. Never invent, re-estimate, round differently, or override any rate, payment, or date. If a \
figure is marked unavailable, say so plainly and tell them to confirm with Oliver — do not fill the \
gap with a guess.

YOUR JOB: return Markdown containing EXACTLY these two sections and nothing else (no preamble, no \
title, no closing line):

## 📰 Key News (past 7 days)

One to three bullets. Each: the headline, then ' — ' and a one-line implication for Vadym & Lisa. \
If no genuinely relevant UK mortgage news was supplied, write a single line saying so.

## ✅ Recommended Action

Open with a bold verdict on its own line — one of: **No action needed**, **Start preparing**, or \
**Act now**. Then 2–4 sentences grounded in their actual numbers: compare the best-buy rates against \
their current 5.26% and the resulting £/month difference; weigh the 2-year vs 5-year trade-off \
(Vadym prefers the 2-year for flexibility — name the rate gap between them; the two fixed terms are \
exactly 2 years and 5 years, never describe them as any other length); factor the Bank of England \
trajectory and the next MPC date; and remember they are planning children, so a single-income \
period must remain affordable. Be honest about uncertainty — do not predict rate moves with false \
confidence.

Context for your judgement: best-buy rates are headline deals at the 85% LTV tier — true eligibility \
and total cost still need Oliver. BoE quoted rates are market-wide averages that sit above best-buy; \
they are shown only to indicate direction.
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
        bb = data.get('best_buy', {})
        d2 = bb.get('fixed_2yr') or {}
        d5 = bb.get('fixed_5yr') or {}
        triggered = 'manual' if os.getenv('TRIGGER_SOURCE') == 'workflow_dispatch' else 'schedule'
        client.table('mortgage_insights').insert({
            'report_date':      data['date'],
            'report_md':        report_md,
            'telegram_text':    telegram_text,
            'base_rate':        data.get('base_rate', {}).get('rate'),
            'fixed_2yr_rate':   d2.get('rate'),
            'fixed_2yr_lender': d2.get('lender'),
            'fixed_5yr_rate':   d5.get('rate'),
            'fixed_5yr_lender': d5.get('lender'),
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


def gather_data() -> dict:
    """Collect every real figure the report needs into one dict."""
    balance = current_balance()
    term = remaining_term_months(balance, CURRENT_RATE, CURRENT_PAYMENT)

    base_rate   = fetch_boe_base_rate()
    quoted      = fetch_boe_quoted_rates()
    mpc_dates   = fetch_mpc_dates()
    best_buy    = fetch_best_buy_rates()
    news        = fetch_mortgage_news()

    # Deterministic payment estimates on the actual balance & remaining term.
    if 'error' not in best_buy and term:
        for key in ('fixed_2yr', 'fixed_5yr'):
            deal = best_buy.get(key)
            if deal:
                est = monthly_payment(balance, deal['rate'] / 100, term)
                deal['est_payment']    = round(est)
                deal['monthly_saving'] = round(CURRENT_PAYMENT - est)

    return {
        'date':           TODAY,
        'balance':        round(balance, 2),
        'ltv':            round(balance / PROPERTY_VALUE * 100, 1),
        'remaining_term': term,
        'base_rate':      base_rate,
        'quoted':         quoted,
        'mpc_dates':      mpc_dates,
        'best_buy':       best_buy,
        'news':           news,
    }


# ── deterministic report sections ─────────────────────────────────────────────

def render_snapshot(data: dict) -> str:
    bb = data['best_buy']
    lines = ['## 🏦 Best-Buy Rate Snapshot (85% LTV tier)', '']

    if 'error' in bb:
        lines += [
            f"> ⚠️ Best-buy data could not be retrieved this run ({bb['error']}). "
            "Ask Oliver for a live best-buy table.", '']
        return '\n'.join(lines)

    lines += [
        f"*Live best-buy deals — {bb['source']}, fetched {fmt_date(TODAY)}.*", '',
        '| Product | Best Rate | Lender | Product Fee | Est. Monthly Payment\\* |',
        '|---|---|---|---|---|',
    ]
    for label, key in (('2-year fixed', 'fixed_2yr'), ('5-year fixed', 'fixed_5yr')):
        deal = bb.get(key)
        if deal:
            pay = f"~£{deal['est_payment']:,}" if 'est_payment' in deal else '—'
            lines.append(
                f"| {label} | {deal['rate']:.2f}% | {deal['lender']} | "
                f"{deal['fee_text'] or 'None'} | {pay} |")
        else:
            lines.append(f"| {label} | *none in this run's best-buy table* | — | — | — |")

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
    for label, key in (('2-year', 'fixed_2yr'), ('5-year', 'fixed_5yr')):
        deal = bb.get(key)
        if deal and 'monthly_saving' in deal:
            saving = deal['monthly_saving']
            verb = 'saves' if saving >= 0 else 'costs an extra'
            lines.append(
                f"- Switching to the best {label} fixed {verb} "
                f"~£{abs(saving):,}/month vs. the current payment.")
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
        f"{month_label(q['prev_as_of'])} → {month_label(q['as_of'])}. These run above best-buy "
        "deals; shown to indicate market direction.*", '',
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
              "*Vadym & Lisa's ~84% LTV sits between the 75% and 90% bands — closer to the 90% figure.*",
              '']
    return '\n'.join(lines)


def render_change(data: dict, prev: dict) -> str:
    lines = ['## 🔄 Change vs. Last Snapshot', '']
    if not prev:
        lines += ['First snapshot with the real-data monitor — no prior run to compare against.', '']
        return '\n'.join(lines)

    lines[0] = f"## 🔄 Change vs. Last Snapshot ({fmt_date(prev.get('date'))})"

    def deal_rate(d, key):
        bb = d.get('best_buy', {})
        if isinstance(bb, dict) and isinstance(bb.get(key), dict):
            return bb[key].get('rate')
        return None

    for label, key in (('2-year fixed best-buy', 'fixed_2yr'),
                        ('5-year fixed best-buy', 'fixed_5yr')):
        now, was = deal_rate(data, key), deal_rate(prev, key)
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
        f"*Generated automatically on {fmt_date(TODAY)}. Sources: Moneyfacts "
        "(live best-buy deals, 85% LTV tier); Bank of England database (base rate "
        "IUDBEDR and quoted-rate series); Bank of England MPC schedule; Marketaux "
        "(news). Best-buy rates are headline deals — confirm eligibility and total "
        "cost with broker Oliver before acting.*"
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

    bb = data['best_buy']
    if 'error' not in bb:
        lines.append('Best-buy, 85% LTV tier (Moneyfacts):')
        for label, key in (('2yr fixed', 'fixed_2yr'), ('5yr fixed', 'fixed_5yr')):
            deal = bb.get(key)
            if deal:
                pay = f" → ~£{deal['est_payment']:,}/mo" if 'est_payment' in deal else ''
                lines.append(
                    f"  {label}: {deal['rate']:.2f}% — {deal['lender']} "
                    f"({deal['fee_text'] or 'no fee'}){pay}")
        lines.append(f"  vs current: {CURRENT_RATE * 100:.2f}%, £{CURRENT_PAYMENT:,.0f}/mo")
    else:
        lines.append('Best-buy rates: unavailable this run — check with Oliver.')

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
    bb, br = data['best_buy'], data['base_rate']
    print(f"  Best-buy:  {'OK' if 'error' not in bb else bb['error']}")
    print(f"  Base rate: {'OK' if 'error' not in br else br['error']}")
    print(f"  Quoted:    {'OK' if 'error' not in data['quoted'] else data['quoted']['error']}")
    print(f"  News:      {len(data['news'])} articles")

    prev = None
    for path in sorted(SNAPSHOTS_DIR.glob('*-data.json'), reverse=True):
        if path.name != DATA_PATH.name:
            try:
                prev = json.loads(path.read_text())
                break
            except Exception:
                pass

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
