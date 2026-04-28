#!/usr/bin/env python3
"""
news_fetcher.py  —  Script A of the daily 3-step pipeline.

Fetches per-holding news (Finnhub + yfinance) and market scan news
(Alpha Vantage + Marketaux). Writes all per_holding articles to Supabase.
Asks Claude to curate the 3-5 most relevant articles for the news feed.

Outputs:
  data/news_pool.json  —  full context for stock_assessor.py (Script B)

Run:
  python3 scripts/news_fetcher.py
"""

import os
import json
import hashlib
import anthropic
from datetime import datetime, timezone
from dotenv import load_dotenv
import gspread
from google.oauth2.service_account import Credentials

from lib.market_sources import (
    fetch_ticker_context,
    fetch_yfinance_context,
    fetch_av_market_sentiment,
    fetch_marketaux_news,
    fetch_yahoo_trending,
    load_filters,
)
from lib.supabase_sink import write_news_items

load_dotenv()

SHEET_ID = os.getenv('PORTFOLIO_SHEET_ID')
SA_FILE  = os.getenv('GOOGLE_APPLICATION_CREDENTIALS', 'config/service_account.json')
SCOPES   = ['https://www.googleapis.com/auth/spreadsheets']
POOL_PATH = 'data/news_pool.json'

TICKER_CONFIG = {
    'NVDA':   ('NVDA',    'NVDA',       'US'),
    'RTX':    ('RTX',     'RTX',        'US'),
    'GOOG':   ('GOOG',    'GOOG',       'US'),
    'BRK.B':  ('BRK.B',  'BRK-B',      'US'),
    'TECK.B': ('TECK.B',  'TECK-B.TO',  'CA'),
    'RIO':    ('RIO.L',   'RIO.L',      'LSE'),
    'SGLN':   ('SGLN.L',  'SGLN.L',     'LSE'),
    'INRG':   ('INRG.L',  'INRG.L',     'LSE'),
    'IITU':   ('IITU.L',  'IITU.L',     'LSE'),
    'VGER':   ('VGER.L',  'VGER.L',     'LSE'),
    'BA.':    ('BA.L',    'BA.L',       'LSE'),
    'VUSA':   ('VUSA.L',  'VUSA.L',     'LSE'),
    'ISP6':   ('ISP6.L',  'ISP6.L',     'LSE'),
    'LGEN':   ('LGEN.L',  'LGEN.L',     'LSE'),
    'EUE':    ('EUE.L',   'EUE.L',      'LSE'),
    'RHM':    ('RHM.DE',  'RHM.DE',     'EU'),
    'HO':     ('HO.PA',   'HO.PA',      'EU'),
}


def parse_float(val):
    if val is None or val == '':
        return 0.0
    try:
        return float(str(val).replace('£', '').replace(',', '').replace('%', '').strip())
    except (ValueError, TypeError):
        return 0.0


def read_positions(sh):
    ws = sh.worksheet('Inv26 - Summary')
    positions = []
    for row in ws.get_all_values():
        if len(row) < 6:
            continue
        ticker = row[0].strip()
        if ticker not in TICKER_CONFIG:
            continue
        qty = parse_float(row[3])
        if qty <= 0:
            continue
        positions.append({
            'ticker':        ticker,
            'name':          row[1].strip(),
            'qty':           qty,
            'avg_buy':       parse_float(row[4]),
            'current_price': parse_float(row[5]),
        })
    return positions


def curate_articles(client, candidates, holding_tickers):
    """
    Ask Claude to pick 3-5 most relevant articles from the candidate pool.
    Returns list of selected candidates (not just indices).
    """
    if not candidates:
        return []

    lines = [
        "You are reviewing financial news for a UK retail investor.",
        f"Their current holdings: {', '.join(holding_tickers)}",
        "",
        "From the articles below, select 3-5 MOST relevant and interesting:",
        "- Concrete events for current holdings (earnings, guidance change, M&A, regulatory action, major contract)",
        "- Compelling NEW prospects with a real investment thesis — not just social buzz",
        "Skip: general market commentary, daily price moves, generic macro, repeated coverage of the same story.",
        "",
        "Return ONLY a JSON array of 0-based article indices, max 5 items. Example: [0, 3, 7]",
        "",
        "Articles:",
    ]
    for i, a in enumerate(candidates):
        title   = (a.get('title') or '').strip()[:120]
        tickers = ', '.join(a.get('tickers') or [])
        lines.append(f"{i}. [{tickers}] {title}")

    try:
        msg = client.messages.create(
            model='claude-haiku-4-5-20251001',
            max_tokens=100,
            messages=[{'role': 'user', 'content': '\n'.join(lines)}],
        )
        raw = msg.content[0].text.strip()
        if raw.startswith('```'):
            parts = raw.split('```')
            raw = parts[1].strip()
            if raw.startswith('json'):
                raw = raw[4:].strip()
        indices = json.loads(raw)
        valid = [i for i in indices if isinstance(i, int) and 0 <= i < len(candidates)][:5]
        return [candidates[i] for i in valid]
    except Exception as e:
        print(f"  Claude curation error: {e} — using first 5 by default")
        return candidates[:5]


def main():
    print("=== Script A: News Fetcher ===")
    now_iso = datetime.now(timezone.utc).isoformat()

    print("\nConnecting to Google Sheets...")
    creds = Credentials.from_service_account_file(SA_FILE, scopes=SCOPES)
    gc    = gspread.authorize(creds)
    sh    = gc.open_by_key(SHEET_ID)
    positions      = read_positions(sh)
    holding_tickers = [p['ticker'] for p in positions]
    print(f"  {len(positions)} holdings: {', '.join(holding_tickers)}")

    client = anthropic.Anthropic(api_key=os.getenv('CLAUDE_API_KEY'))

    # ── Per-holding news ──────────────────────────────────────────────────────
    print("\nFetching per-holding news...")
    holding_context = {}
    article_pool    = []

    for pos in positions:
        ticker       = pos['ticker']
        finnhub_sym, yf_sym, exchange = TICKER_CONFIG[ticker]
        print(f"  {ticker} [{exchange}]")

        if exchange in ('US', 'CA'):
            data = fetch_ticker_context(finnhub_sym, hours=24, holding_ticker=ticker)
            if not data.get('headlines'):
                yf_data = fetch_yfinance_context(yf_sym, holding_ticker=ticker)
                data['headlines']    = yf_data.get('headlines', [])
                data['analyst_info'] = yf_data.get('analyst_info', {})
        else:
            yf_data = fetch_yfinance_context(yf_sym, holding_ticker=ticker)
            data = {
                'headlines':    yf_data.get('headlines', []),
                'sentiment':    {},
                'analyst':      {},
                'analyst_info': yf_data.get('analyst_info', {}),
            }

        holding_context[ticker] = {**data, 'position': pos}

        for h in data.get('headlines', [])[:5]:
            title = h.get('headline') if isinstance(h, dict) else str(h)
            if title and title.strip():
                article_pool.append({
                    'title':       title.strip(),
                    'tickers':     [ticker],
                    'source':      exchange.lower(),
                    'source_type': 'per_holding',
                })

    print(f"  {len(article_pool)} holding articles collected")

    # ── Market scan (writes market_scan news to DB automatically) ─────────────
    print("\nFetching market scan news...")
    filters            = load_filters()
    stopwords          = set(filters.get('ticker_stopwords', []))
    av_mentions        = fetch_av_market_sentiment(stopwords, limit=50)
    marketaux_mentions = fetch_marketaux_news(stopwords, limit=50)
    yahoo_trending     = fetch_yahoo_trending('US')

    # Add top AV prospect headlines to pool for curation
    for ticker, items in list(av_mentions.items())[:15]:
        for _, snippet in items[:1]:
            article_pool.append({
                'title':       snippet[:120],
                'tickers':     [ticker],
                'source':      'alphavantage',
                'source_type': 'market_scan',
            })

    print(f"  Total article pool: {len(article_pool)}")

    # ── Claude curation ───────────────────────────────────────────────────────
    print("\nCurating top articles with Claude...")
    selected = curate_articles(client, article_pool, holding_tickers)
    print(f"  Selected {len(selected)} articles for news feed")

    # Write curated per_holding articles to news_items with fresh timestamp
    # so they appear within the 14-day frontend filter regardless of source date
    curated_rows = []
    for a in selected:
        if a.get('source_type') != 'per_holding':
            continue
        title = a.get('title', '')
        key   = hashlib.sha1(f"curated:{title}:{now_iso[:13]}".encode()).hexdigest()[:16]
        curated_rows.append({
            'id':           f'c_{key}',
            'published_at': now_iso,
            'tickers':      a.get('tickers', []),
            'source':       a.get('source', 'unknown'),
            'source_type':  'per_holding',
            'title':        title,
            'url':          None,
            'image_url':    None,
            'snippet':      '',
            'sentiment':    'neutral',
        })

    if curated_rows:
        write_news_items(curated_rows)
        print(f"  Wrote {len(curated_rows)} curated news items to Supabase")

    # ── Save pool for stock_assessor.py ──────────────────────────────────────
    os.makedirs('data', exist_ok=True)
    pool = {
        'run_time':            now_iso,
        'holdings':            holding_context,
        'av_mentions':         {t: items for t, items in av_mentions.items()},
        'marketaux_mentions':  {t: items for t, items in marketaux_mentions.items()},
        'yahoo_trending':      yahoo_trending,
        'selected_news':       selected,
    }
    with open(POOL_PATH, 'w') as f:
        json.dump(pool, f, indent=2, default=str)
    print(f"\nNews pool saved → {POOL_PATH}")


if __name__ == '__main__':
    main()
