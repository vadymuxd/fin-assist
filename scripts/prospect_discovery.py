#!/usr/bin/env python3
"""
prospect_discovery.py

Dynamic discovery of buy candidates from sources traders actually follow.

Sources:
  - Reddit r/wallstreetbets, r/stocks, r/investing, r/ValueInvesting
  - Finnhub general market news (tickers via `related` field)
  - Yahoo Finance trending (most-watched today)

Pipeline:
  1. Aggregate ticker mentions across sources; rank by mention count
  2. Filter: exclude existing holdings, exclude_tickers, exclude_keywords
     matched in evidence, exclude Chinese/HK-domiciled via country code,
     drop anything below min_source_mentions / min_market_cap_usd
  3. For each surviving candidate: fetch company news + sentiment + analyst
  4. Ask Claude for an exploratory thesis — alert-worthy at score ≥6 with a real case
  5. Append/update rows in the Watchlist tab (journal of every discovery)
  6. Modes:
       --auto  (cron)    silent unless a new BUY emerges
       --bot   (Telegram) always replies with top discoveries + rationale

Run:
  python3 scripts/prospect_discovery.py --auto
  python3 scripts/prospect_discovery.py --bot
"""

import os
import sys
import json
import requests
import anthropic
from datetime import datetime, timezone
from dotenv import load_dotenv
import gspread
from google.oauth2.service_account import Credentials

from lib.market_sources import (
    load_filters,
    fetch_ticker_universe,
    fetch_av_market_sentiment,
    fetch_marketaux_news,
    fetch_yahoo_trending,
    aggregate_candidates,
    fetch_ticker_context,
    fetch_yfinance_context,
    infer_yf_symbol,
    infer_exchange_tag,
)

load_dotenv()

SHEET_ID = os.getenv('PORTFOLIO_SHEET_ID')
SA_FILE  = os.getenv('GOOGLE_APPLICATION_CREDENTIALS', 'config/service_account.json')
SCOPES   = ['https://www.googleapis.com/auth/spreadsheets']
RESULTS_PATH = 'data/prospect_discoveries.json'

TELEGRAM_TOKEN   = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

BUY_THRESHOLD = 6   # exploratory: alert at 6+ with real thesis

WATCHLIST_TAB = 'Watchlist'
WATCHLIST_HEADERS = [
    'Date Added', 'Ticker', 'Name', 'Exchange', 'Source(s)',
    'First Score', 'Latest Score', 'Recommendation', 'Rationale', 'Status',
]


# ---------------------------------------------------------------------------
# Sheet access
# ---------------------------------------------------------------------------

def open_sheet():
    creds = Credentials.from_service_account_file(SA_FILE, scopes=SCOPES)
    gc = gspread.authorize(creds)
    return gc.open_by_key(SHEET_ID)


def get_or_create_watchlist(sh):
    """Ensure the Watchlist tab exists with the correct header row."""
    try:
        ws = sh.worksheet(WATCHLIST_TAB)
    except gspread.exceptions.WorksheetNotFound:
        ws = sh.add_worksheet(title=WATCHLIST_TAB, rows=500, cols=len(WATCHLIST_HEADERS))
        ws.update(values=[WATCHLIST_HEADERS], range_name='A1')
        return ws

    first_row = ws.row_values(1)
    if first_row[:len(WATCHLIST_HEADERS)] != WATCHLIST_HEADERS:
        # Header mismatch — wipe and rewrite to match new schema
        ws.clear()
        ws.update(values=[WATCHLIST_HEADERS], range_name='A1')
    return ws


def read_holdings(sh):
    """Return set of held tickers (qty > 0) — exclude from discovery."""
    try:
        ws = sh.worksheet('Inv26 - Summary')
    except gspread.exceptions.WorksheetNotFound:
        return set()
    held = set()
    for row in ws.get_all_values():
        if len(row) < 4:
            continue
        ticker = row[0].strip().upper()
        qty_str = row[3].replace(',', '').strip() if len(row) > 3 else ''
        try:
            qty = float(qty_str)
        except ValueError:
            qty = 0
        if ticker and qty > 0:
            held.add(ticker)
    return held


def read_watchlist_rows(ws):
    """Return {ticker: {row_index, first_score, status, date_added}}."""
    rows = ws.get_all_values()
    existing = {}
    for i, row in enumerate(rows[1:], start=2):  # row 2 = first data row
        if not row or not row[1].strip():
            continue
        ticker = row[1].strip().upper()
        existing[ticker] = {
            'row':         i,
            'first_score': row[5] if len(row) > 5 else '',
            'status':      row[9] if len(row) > 9 else '',
            'date_added':  row[0] if row else '',
        }
    return existing


# ---------------------------------------------------------------------------
# Claude evaluation
# ---------------------------------------------------------------------------

def build_prompt(candidate, context, price_info):
    price    = price_info.get('price')
    currency = price_info.get('currency', 'USD')

    lines = [
        f"Evaluate {candidate['ticker']} as a potential BUY for a UK retail investor.",
        f"Tone: exploratory — surface interesting setups even if the case isn't ironclad, but be honest about risk.",
        "",
    ]
    if price:
        lines.append(f"Current price: {currency} {price:.2f}")
        lines.append("")

    lines.append(f"Discovery sources: {', '.join(candidate['sources'])}")
    if candidate.get('evidence'):
        lines.append("Evidence:")
        for e in candidate['evidence']:
            lines.append(f"  - {e}")
    lines.append("")

    headlines = context.get('headlines') or []
    if headlines:
        lines.append("Company news (last 7 days):")
        for i, h in enumerate(headlines[:8], 1):
            title = h.get('headline') if isinstance(h, dict) else h
            lines.append(f"  {i}. {title}")
        lines.append("")

    s_block = context.get('sentiment', {})
    if s_block and s_block.get('sentiment'):
        s = s_block['sentiment']
        lines.append(
            f"Sentiment: {s.get('bullishPercent', 0)*100:.0f}% bullish / "
            f"{s.get('bearishPercent', 0)*100:.0f}% bearish"
        )

    a = context.get('analyst') or {}
    if a and any(a.get(k, 0) for k in ('strongBuy', 'buy', 'hold', 'sell', 'strongSell')):
        lines.append(
            f"Analysts: StrongBuy {a.get('strongBuy',0)} Buy {a.get('buy',0)} "
            f"Hold {a.get('hold',0)} Sell {a.get('sell',0)} StrongSell {a.get('strongSell',0)}"
        )

    pt = context.get('price_target', {})
    if pt and pt.get('targetMean') and price:
        upside = (pt['targetMean'] - price) / price * 100
        lines.append(f"Price target mean: {pt['targetMean']:.2f} ({upside:+.1f}% upside)")

    ai = context.get('analyst_info') or {}
    if ai.get('recommendationKey'):
        lines.append(f"yfinance recommendation: {ai['recommendationKey']} ({ai.get('numberOfAnalystOpinions', 0)} analysts)")
    if ai.get('marketCap'):
        lines.append(f"Market cap: {ai['marketCap']:,}")

    lines += [
        "",
        "Return ONLY a JSON object (no markdown, no prose):",
        '{',
        '  "score": <integer 1-10>,',
        '  "recommendation": "<BUY|WATCH|PASS>",',
        '  "confidence": "<HIGH|MEDIUM|LOW>",',
        '  "thesis": "<2-3 sentences: why this is interesting right now, key catalyst, main risk>",',
        '  "name": "<best-guess company name or empty string>"',
        '}',
        "",
        "Score: 8-10=strong buy case, 6-7=worth watching with real thesis, 5=neutral, 3-4=weak, 1-2=avoid.",
        "Be exploratory but grounded: the thesis must cite a concrete reason (news event, valuation shift, ",
        "catalyst, sector tailwind). If the evidence is just hype with no substance, score ≤5.",
    ]
    return '\n'.join(lines)


def call_claude(client, prompt, ticker):
    try:
        msg = client.messages.create(
            model='claude-haiku-4-5-20251001',
            max_tokens=500,
            messages=[{'role': 'user', 'content': prompt}],
        )
        raw = msg.content[0].text.strip()
        if raw.startswith('```'):
            parts = raw.split('```')
            raw = parts[1] if len(parts) > 1 else raw
            if raw.startswith('json'):
                raw = raw[4:].strip()
        return json.loads(raw)
    except json.JSONDecodeError:
        return {'score': 5, 'recommendation': 'WATCH', 'confidence': 'LOW', 'thesis': 'Parse error', 'name': ''}
    except Exception as e:
        print(f"    Claude API error for {ticker}: {e}")
        return {'score': 5, 'recommendation': 'WATCH', 'confidence': 'LOW', 'thesis': f'API error: {e}', 'name': ''}


# ---------------------------------------------------------------------------
# Keyword exclusion check
# ---------------------------------------------------------------------------

def evidence_has_excluded_keyword(candidate, keywords):
    blob = ' '.join(candidate.get('evidence', [])).lower()
    return any(kw.lower() in blob for kw in keywords)


# ---------------------------------------------------------------------------
# Watchlist writer
# ---------------------------------------------------------------------------

def upsert_watchlist(ws, evaluated):
    """
    For each evaluated candidate:
      - If ticker already exists: update Latest Score + Recommendation + Rationale
        (keep First Score, Date Added, Status)
      - Else: append a new row with Status=Active
    """
    existing = read_watchlist_rows(ws)
    today    = datetime.now(timezone.utc).strftime('%Y-%m-%d')

    updates  = []  # list of (range_a1, [[values]]) for batch_update
    appends  = []  # list of new rows

    for r in evaluated:
        ticker = r['ticker']
        if ticker in existing:
            row_idx = existing[ticker]['row']
            updates.append((f'G{row_idx}:I{row_idx}', [[r['score'], r['recommendation'], r['thesis']]]))
        else:
            appends.append([
                today, ticker, r.get('name', ''), r.get('exchange_tag', ''),
                ', '.join(r.get('sources', [])),
                r['score'], r['score'], r['recommendation'], r['thesis'], 'Active',
            ])

    if updates:
        ws.batch_update([{'range': rng, 'values': vals} for rng, vals in updates])
        print(f"  Updated {len(updates)} existing Watchlist row(s)")
    if appends:
        ws.append_rows(appends, value_input_option='USER_ENTERED')
        print(f"  Appended {len(appends)} new Watchlist row(s)")


# ---------------------------------------------------------------------------
# Telegram
# ---------------------------------------------------------------------------

def escape_html(text):
    return str(text).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def send_telegram(text):
    """Send message, splitting into chunks if it exceeds Telegram's 4096-char limit."""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("  Telegram credentials not set — printing instead:")
        print(text)
        return False
    chunks = [text[i:i+4000] for i in range(0, len(text), 4000)]
    ok = True
    for chunk in chunks:
        try:
            resp = requests.post(
                f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage',
                json={'chat_id': TELEGRAM_CHAT_ID, 'text': chunk, 'parse_mode': 'HTML'},
                timeout=10,
            )
            resp.raise_for_status()
        except Exception as e:
            print(f"  Telegram error: {e}")
            ok = False
    return ok


def format_auto_alert(buys):
    """Auto-mode: only BUY-level finds. Keep it short and actionable."""
    now_str = datetime.now(timezone.utc).strftime('%d %b %Y, %H:%M UTC')
    lines = [f'🔭 <b>NEW PROSPECT</b> — {now_str}', '']
    for r in buys:
        lines.append(f'🟢 <b>{escape_html(r["ticker"])}</b> {escape_html(r.get("name",""))} | {r["score"]}/10 {escape_html(r["recommendation"])} ({escape_html(r["confidence"])})')
        lines.append(f'   Sources: {escape_html(", ".join(r.get("sources", [])))}')
        lines.append(f'   {escape_html(r["thesis"])}')
        lines.append('')
    lines.append('Added to Watchlist tab.')
    return '\n'.join(lines).strip()


def format_bot_reply(evaluated):
    """
    Bot-mode: show top 5 candidates scored ≥6, ranked by score.
    All evaluated candidates are still written to the Watchlist regardless.
    """
    now_str = datetime.now(timezone.utc).strftime('%d %b %Y, %H:%M UTC')
    lines = [f'🔍 <b>DISCOVERY SCAN</b> — {now_str}', '']

    if not evaluated:
        lines.append('No tickers surfaced from any source right now.')
        lines.append('Try again later — sources refresh continuously.')
        return '\n'.join(lines)

    # Rank by score, take top 5 with score ≥ 6
    ranked = sorted(evaluated, key=lambda r: -r.get('score', 0))
    shortlisted = [r for r in ranked if r.get('score', 0) >= 6][:5]
    total = len(evaluated)

    if not shortlisted:
        lines.append(f'Scanned {total} candidates — none scored 6+ today.')
        lines.append('All added to Watchlist. Try again tomorrow.')
        return '\n'.join(lines)

    lines.append(f'Top picks from {total} candidates scanned:\n')
    for r in shortlisted:
        score = r['score']
        emoji = '🟢' if score >= 8 else '🟡'
        lines.append(f'{emoji} <b>{escape_html(r["ticker"])}</b> {escape_html(r.get("name",""))} | {score}/10 {escape_html(r["recommendation"])} ({escape_html(r["confidence"])})')
        lines.append(f'   Sources: {escape_html(", ".join(r.get("sources", [])))}')
        lines.append(f'   {escape_html(r["thesis"])}')
        lines.append('')

    lines.append(f'Full list ({total} tickers) saved to Watchlist tab.')
    return '\n'.join(lines).strip()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(mode):
    is_bot = (mode == 'bot')
    filters = load_filters()

    # Manual /discover should always surface something — relax the mention
    # threshold so single-source candidates still reach Claude scoring.
    if is_bot:
        filters = dict(filters)
        filters['min_source_mentions'] = 1

    print("Loading ticker universe (Finnhub)...")
    universe = fetch_ticker_universe()
    print(f"  Universe size: {len(universe)} symbols")

    print("\nOpening sheet + reading holdings...")
    sh = open_sheet()
    holdings = read_holdings(sh)
    print(f"  {len(holdings)} held tickers")

    ws = get_or_create_watchlist(sh)

    stopwords       = set(filters.get('ticker_stopwords', []))
    excluded_tickers = set(filters.get('exclude_tickers', []))
    excluded = holdings | excluded_tickers

    print("\nFetching Alpha Vantage market news sentiment...")
    av_mentions = fetch_av_market_sentiment(stopwords, limit=50)

    print("\nFetching Marketaux news sentiment...")
    marketaux_mentions = fetch_marketaux_news(stopwords, limit=3)

    print("\nFetching Yahoo Finance trending...")
    yahoo = fetch_yahoo_trending('US')
    print(f"  {len(yahoo)} trending tickers")

    candidates = aggregate_candidates(av_mentions, marketaux_mentions, yahoo, filters, excluded)
    print(f"\n{len(candidates)} candidate(s) after filters + thresholds")

    # Drop candidates whose evidence contains excluded keywords (e.g. "crypto")
    kw_excludes = filters.get('exclude_keywords', [])
    candidates = [c for c in candidates if not evidence_has_excluded_keyword(c, kw_excludes)]
    print(f"  {len(candidates)} candidate(s) after keyword filter")

    if not candidates:
        print("\nNothing to score.")
        if is_bot:
            send_telegram(format_bot_reply([]))
        return

    client = anthropic.Anthropic(api_key=os.getenv('CLAUDE_API_KEY'))
    min_mcap = filters.get('min_market_cap_usd', 0)
    evaluated = []

    for c in candidates:
        ticker = c['ticker']
        uni    = universe.get(ticker)
        yf_sym = infer_yf_symbol(ticker, uni)
        ex_tag = infer_exchange_tag(uni)
        print(f"\n  {ticker} [{ex_tag}] score={c['score']} sources={c['sources']}")

        if ex_tag in ('US', 'CA'):
            finnhub_sym = ticker
            if uni and uni.get('exchange') == 'L':
                finnhub_sym = f'{ticker}.L'
            context = fetch_ticker_context(finnhub_sym, hours=168)
        else:
            context = {'headlines': [], 'sentiment': {}, 'analyst': {}, 'price_target': {}}

        yf_data = fetch_yfinance_context(yf_sym)
        if not context.get('headlines'):
            context['headlines'] = yf_data.get('headlines', [])
        context['analyst_info'] = yf_data.get('analyst_info', {})

        # Market cap filter
        mcap = yf_data.get('analyst_info', {}).get('marketCap') or 0
        if min_mcap and mcap and mcap < min_mcap:
            print(f"    Skip — market cap {mcap:,} < min {min_mcap:,}")
            continue

        price_info = {
            'price':    yf_data.get('price'),
            'currency': yf_data.get('currency', 'USD'),
        }

        prompt = build_prompt(c, context, price_info)
        print(f"    Claude ({len(context.get('headlines', []))} headlines)...")
        scored = call_claude(client, prompt, ticker)

        name = scored.get('name') or (uni.get('name') if uni else '') or ''
        evaluated.append({
            'ticker':         ticker,
            'name':           name,
            'exchange_tag':   ex_tag,
            'sources':        c['sources'],
            'evidence':       c['evidence'],
            'score':          scored.get('score', 5),
            'recommendation': scored.get('recommendation', 'WATCH'),
            'confidence':     scored.get('confidence', 'LOW'),
            'thesis':         scored.get('thesis', ''),
            'run_time':       datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC'),
        })
        print(f"    → {scored.get('score')}/10 {scored.get('recommendation')} ({scored.get('confidence')})")

    os.makedirs('data', exist_ok=True)
    with open(RESULTS_PATH, 'w') as f:
        json.dump(evaluated, f, indent=2)
    print(f"\nResults saved → {RESULTS_PATH}")

    # Journal everything to Watchlist
    if evaluated:
        upsert_watchlist(ws, evaluated)

    # Figure out what's NEW (score ≥ threshold AND not already on Watchlist before this run)
    # We need the pre-run watchlist snapshot — read again post-write would be wrong.
    # Use the fact that newly-appended rows have today's date + existing didn't.
    # Simpler: a "new BUY" is recommendation==BUY AND score ≥ BUY_THRESHOLD AND was not
    # previously in the Watchlist with a BUY recommendation.
    pre_existing = read_watchlist_rows(ws)  # after upsert, but existing rows kept original date
    today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    new_buys = []
    for r in evaluated:
        if r['score'] < BUY_THRESHOLD:
            continue
        if r['recommendation'] != 'BUY':
            continue
        meta = pre_existing.get(r['ticker'], {})
        # "new" = date_added is today (just appended this run)
        if meta.get('date_added') == today:
            new_buys.append(r)

    if is_bot:
        send_telegram(format_bot_reply(evaluated))
        print(f"\n[bot] Full scan sent. {len(new_buys)} new BUY(s).")
    else:
        if new_buys:
            send_telegram(format_auto_alert(new_buys))
            print(f"\n[auto] {len(new_buys)} new BUY alert(s) sent.")
        else:
            print("\n[auto] No new BUYs — staying silent.")


if __name__ == '__main__':
    mode = 'auto'
    if '--bot' in sys.argv:
        mode = 'bot'
    elif '--auto' in sys.argv:
        mode = 'auto'
    main(mode)
