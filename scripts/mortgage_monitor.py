#!/usr/bin/env python3
"""
mortgage_monitor.py — Weekly UK mortgage market monitor.

Fetches UK mortgage rate news via Marketaux, reads the previous snapshot
for comparison, calls Claude to generate a structured report, saves it to
mortgage/market-snapshots/, and sends the report to Telegram.

Run:
  python3 scripts/mortgage_monitor.py
"""

import os
import requests
import anthropic
from datetime import datetime, timezone, timedelta
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

MARKETAUX_KEY    = os.getenv('MARKETAUX_API_KEY', '')
CLAUDE_API_KEY   = os.getenv('CLAUDE_API_KEY', '')
TELEGRAM_TOKEN   = os.getenv('TELEGRAM_BOT_TOKEN', '')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', '')

SNAPSHOTS_DIR = Path('mortgage/market-snapshots')
TODAY = datetime.now(timezone.utc).strftime('%Y-%m-%d')
REPORT_PATH = SNAPSHOTS_DIR / f'{TODAY}-report.md'

SYSTEM_PROMPT = """You are the mortgage market monitoring agent for Vadym and Lisa, a UK couple remortgaging in October 2026.

## Their Situation
- Current mortgage: Co-operative Bank, 5.26% fixed, fix ends 31 Jan 2027
- Outstanding balance: £552,371 | Property value: £660,000 | LTV: ~84%
- Combined income: ~£210,000/year | Monthly payment: £3,072
- Remortgage window: Aug 2026 – Jan 2027 (6-month window opens ~Aug 2026)
- Broker: Oliver (existing contact)
- Life plan: expecting children — single-income stress test required (~£5,700–5,833/month net)

## Report Format (follow EXACTLY)

# Mortgage Market Monitor — {DATE}

## 🏦 Rate Snapshot

| Product | Best Rate | Lender | Fee | Monthly Payment (est.) |
|---|---|---|---|---|
| 2-year fixed (85% LTV) | X.XX% | [Lender] | £X,XXX | ~£X,XXX |
| 5-year fixed (85% LTV) | X.XX% | [Lender] | £X,XXX | ~£X,XXX |

*vs. current rate: 5.26% (Co-operative Bank) → current payment £3,072/month*

## 📊 Bank of England

- **Current base rate**: X.XX%
- **Last changed**: [date or period]
- **Next MPC decision**: [date]
- **Market expectation**: [cut / hold / hike and basis]

## 📰 Key News (past 7 days)

1. [Headline] — [brief implication for Vadym & Lisa]
2. [Headline] — [brief implication]
3. [Headline] — [brief implication]

## 🔄 Change vs. Last Week

- 2-year fixed: [up/down/unchanged by X basis points vs last snapshot]
- 5-year fixed: [up/down/unchanged by X basis points vs last snapshot]
- BoE base rate: [changed / unchanged]

## ✅ Recommended Action

**[No action needed / Consider reviewing reservation / Act now]**

[2–3 sentences grounded in their specific situation: ~£556k balance, 85% LTV, October 2026 expiry.]

---

*Report generated automatically on {DATE}. Sources: [list sources used]*

## Rules
- Ground every recommendation in their actual situation — not generic advice.
- If current rates are materially better than 5.26% and improved vs last week, flag prominently.
- If a BoE MPC meeting is within 2 weeks, flag it with ⚠️ and explain the timing trade-off.
- Be factual. If specific 84% LTV rate data is unavailable from news, say so and recommend verifying via L&C Mortgages or a broker.
- Compare 2yr vs 5yr: Vadym prefers 2yr for flexibility; the rate delta between them matters.
- The 6-month switch window opens ~Aug 2026; optimal action window is Aug–Nov 2026.
"""


def fetch_mortgage_news():
    if not MARKETAUX_KEY:
        print("  No MARKETAUX_API_KEY — skipping news fetch")
        return []

    cutoff = (datetime.now(timezone.utc) - timedelta(days=8)).strftime('%Y-%m-%dT%H:%M')
    articles = []
    queries = [
        'UK mortgage rates fixed',
        'Bank of England base rate MPC',
        'UK remortgage lender rates',
    ]
    for query in queries:
        try:
            resp = requests.get(
                'https://api.marketaux.com/v1/news/all',
                params={
                    'search':           query,
                    'language':         'en',
                    'published_after':  cutoff,
                    'limit':            5,
                    'api_token':        MARKETAUX_KEY,
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
        except Exception as e:
            print(f"  Marketaux error ({query}): {e}")

    seen, unique = set(), []
    for a in articles:
        if a['title'] not in seen:
            seen.add(a['title'])
            unique.append(a)
    return unique


def read_previous_snapshot():
    if not SNAPSHOTS_DIR.exists():
        return None
    for path in sorted(SNAPSHOTS_DIR.glob('*.md'), reverse=True):
        if path.name != f'{TODAY}-report.md':
            try:
                return path.read_text()
            except Exception:
                pass
    return None


def generate_report(news_articles, previous_snapshot):
    client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)

    parts = [f"Today's date: {TODAY}\n"]

    if news_articles:
        parts.append("## News articles fetched (past 8 days)\n")
        for i, a in enumerate(news_articles, 1):
            parts.append(
                f"{i}. **{a['title']}** ({a['source']}, {a['published']})\n"
                f"   {a['description']}\n"
                f"   URL: {a['url']}\n"
            )
    else:
        parts.append(
            "No news articles fetched. Base the report on your training knowledge "
            "but clearly note that rates must be verified via L&C Mortgages or a broker.\n"
        )

    if previous_snapshot:
        parts.append(f"\n## Previous snapshot (for week-on-week comparison)\n\n{previous_snapshot}\n")
    else:
        parts.append("\nNo previous snapshot available — omit 'Change vs. Last Week'.\n")

    parts.append("\nGenerate the full weekly mortgage monitor report now.")

    message = client.messages.create(
        model='claude-sonnet-4-6',
        max_tokens=2000,
        system=SYSTEM_PROMPT,
        messages=[{'role': 'user', 'content': '\n'.join(parts)}],
    )
    return message.content[0].text


def build_telegram_summary(report):
    """Extract key data from the full report into a short plain-text summary."""
    rate_lines = []
    boe_line   = ''
    rec_text   = ''

    in_rec = False
    for line in report.splitlines():
        # Rate table rows (| 2-year fixed ... | 4.29% | Halifax | ...)
        if '| 2-year' in line or '| 5-year' in line:
            cols = [c.strip() for c in line.split('|') if c.strip()]
            if len(cols) >= 3:
                rate_lines.append(f"  {cols[0]}: {cols[1]} ({cols[2]})")

        # BoE base rate line
        if 'Current base rate' in line and not boe_line:
            boe_line = line.replace('**', '').replace('- ', '').strip()

        # Recommended action block
        if '## ✅ Recommended Action' in line:
            in_rec = True
            continue
        if in_rec:
            if line.startswith('---') or (line.startswith('## ') and 'Recommended' not in line):
                in_rec = False
                continue
            clean = line.replace('**', '').replace('*', '').strip()
            if clean and not clean.startswith('#'):
                rec_text += clean + ' '

    parts = [f'🏦 Mortgage Monitor — {TODAY}', '']
    if rate_lines:
        parts.append('Rates (85% LTV):')
        parts.extend(rate_lines[:2])
    if boe_line:
        parts.append(f'\n{boe_line}')
    if rec_text:
        parts.append(f'\n✅ {rec_text.strip()[:400]}')
    parts.append('\n(Full report saved to repo)')

    return '\n'.join(parts)


def send_telegram(text):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("  Telegram not configured — report printed above")
        return
    safe = text if len(text) <= 4096 else text[:4090] + '…'
    try:
        resp = requests.post(
            f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage',
            json={'chat_id': TELEGRAM_CHAT_ID, 'text': safe},
            timeout=10,
        )
        resp.raise_for_status()
    except Exception as e:
        print(f"  Telegram error: {e}")


def main():
    print(f"=== Mortgage Monitor — {TODAY} ===")

    print("Fetching mortgage news...")
    news = fetch_mortgage_news()
    print(f"  {len(news)} articles fetched")

    print("Reading previous snapshot...")
    prev = read_previous_snapshot()
    print(f"  Previous snapshot: {'found' if prev else 'none'}")

    print("Generating report with Claude...")
    report = generate_report(news, prev)
    print(report)

    SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(report)
    print(f"\nReport saved to {REPORT_PATH}")

    print("Sending summary to Telegram...")
    summary = build_telegram_summary(report)
    print(f"  Summary length: {len(summary)} chars")
    send_telegram(summary)
    print("Done.")


if __name__ == '__main__':
    main()
