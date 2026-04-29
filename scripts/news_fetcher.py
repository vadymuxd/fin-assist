#!/usr/bin/env python3
"""
news_fetcher.py  —  Script A of the daily 3-step pipeline.

Builds a deduplicated raw article pool from Finnhub + yfinance per holding,
plus market scan from AV + Marketaux. Asks Claude to pick the 3-5 most
relevant articles AND validate which holding ticker each is actually about.
Only the curated, validated articles are written to Supabase news_items —
nothing else. The news feed in the app is therefore exactly what Claude
selected, no per-ticker bulk dumps.

Outputs:
  data/news_pool.json  —  full context for stock_assessor.py (Script B)

Run:
  python3 scripts/news_fetcher.py
"""

import os
import json
import hashlib
import time
import requests
import yfinance as yf
import anthropic
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
import gspread
from google.oauth2.service_account import Credentials

from lib.market_sources import (
    fetch_av_market_sentiment,
    fetch_marketaux_news,
    fetch_yahoo_trending,
    fetch_alpha_vantage_sentiment,
    finnhub_get,
    load_filters,
)
from lib.supabase_sink import write_news_items

load_dotenv()

SHEET_ID  = os.getenv('PORTFOLIO_SHEET_ID')
SA_FILE   = os.getenv('GOOGLE_APPLICATION_CREDENTIALS', 'config/service_account.json')
SCOPES    = ['https://www.googleapis.com/auth/spreadsheets']
POOL_PATH = 'data/news_pool.json'
USER_AGENT = 'fin-assist/1.0 (+https://github.com/vadymuxd/fin-assist)'

FINNHUB_KEY  = os.getenv('FINNHUB_API_KEY', '')
FINNHUB_BASE = 'https://finnhub.io/api/v1'

MAX_PER_TICKER = 4   # cap raw articles fetched per holding before dedup
MAX_CURATED    = 5   # max articles Claude can select for the news feed

TICKER_CONFIG = {
    'NVDA':   ('NVDA',    'NVDA',       'US'),
    'RTX':    ('RTX',     'RTX',        'US'),
    'GOOG':   ('GOOG',    'GOOG',       'US'),
    'BRK.B':  ('BRK.B',   'BRK-B',      'US'),
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


# ── Helpers ──────────────────────────────────────────────────────────────────

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


def normalize_title(title):
    """Lower, strip punctuation/whitespace — used for dedup across sources."""
    if not title:
        return ''
    t = title.lower().strip()
    for ch in '"\'’“”():.,!?-—–|':
        t = t.replace(ch, ' ')
    return ' '.join(t.split())


# ── Inline news fetchers (NO Supabase writes) ─────────────────────────────────

def fetch_finnhub_news(symbol, hours=24):
    """Return raw Finnhub company-news with full metadata. Does NOT write to DB."""
    if not FINNHUB_KEY:
        return []
    now = datetime.now(timezone.utc)
    date_to = now.strftime('%Y-%m-%d')
    date_from = (now - timedelta(hours=hours)).strftime('%Y-%m-%d')
    try:
        resp = requests.get(
            f'{FINNHUB_BASE}/company-news',
            params={'symbol': symbol, 'from': date_from, 'to': date_to, 'token': FINNHUB_KEY},
            timeout=10,
        )
        resp.raise_for_status()
        items = resp.json() or []
    except Exception as e:
        print(f"    Finnhub news error ({symbol}): {e}")
        return []

    out = []
    for i in items[:MAX_PER_TICKER * 2]:  # over-fetch; dedup will trim
        title = i.get('headline', '').strip()
        url   = i.get('url', '')
        if not title or not url:
            continue
        ts = i.get('datetime', 0)
        published_iso = (
            datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
            if ts else datetime.now(timezone.utc).isoformat()
        )
        out.append({
            'title':        title,
            'url':          url,
            'image_url':    i.get('image') or None,
            'snippet':      (i.get('summary') or '')[:500],
            'published_at': published_iso,
            'source':       i.get('source', 'finnhub'),
        })
    return out


def fetch_yfinance_news(symbol):
    """Return raw yfinance Ticker.news with full metadata. Does NOT write to DB."""
    try:
        t   = yf.Ticker(symbol)
        raw = t.news or []
    except Exception as e:
        print(f"    yfinance news error ({symbol}): {e}")
        return []

    out = []
    now_iso = datetime.now(timezone.utc).isoformat()
    for item in raw[:MAX_PER_TICKER * 2]:
        content = item.get('content', {}) or {}
        title   = content.get('title') or item.get('title') or ''
        url     = ((content.get('canonicalUrl') or {}).get('url', '')
                   or item.get('link', ''))
        if not title or not url:
            continue

        published_at = None
        pub_iso = content.get('pubDate') or content.get('displayTime')
        if pub_iso:
            try:
                published_at = datetime.fromisoformat(
                    str(pub_iso).replace('Z', '+00:00')
                ).isoformat()
            except (ValueError, TypeError):
                published_at = None
        if not published_at:
            pub_ts = item.get('providerPublishTime')
            if pub_ts:
                published_at = datetime.fromtimestamp(pub_ts, tz=timezone.utc).isoformat()
        if not published_at:
            published_at = now_iso

        publisher = (
            (content.get('provider') or {}).get('displayName')
            or item.get('publisher')
            or 'yfinance'
        )
        thumb     = content.get('thumbnail') or item.get('thumbnail') or {}
        image_url = None
        resolutions = thumb.get('resolutions', []) or []
        if resolutions:
            image_url = resolutions[-1].get('url')
        elif thumb.get('originalUrl'):
            image_url = thumb['originalUrl']

        snippet = (content.get('summary') or content.get('description') or '')[:500]

        out.append({
            'title':        title.strip(),
            'url':          url,
            'image_url':    image_url,
            'snippet':      snippet,
            'published_at': published_at,
            'source':       publisher,
        })
    return out


def fetch_holding_sentiment(symbol, exchange):
    """Fetch sentiment + analyst data for holding (no news)."""
    sentiment    = {}
    analyst      = {}
    price_target = {}
    if exchange in ('US', 'CA'):
        sentiment    = finnhub_get('news-sentiment', {'symbol': symbol}) or {}
        if not sentiment:
            sentiment = fetch_alpha_vantage_sentiment(symbol)
        rec_raw      = finnhub_get('stock/recommendation', {'symbol': symbol}) or []
        analyst      = rec_raw[0] if rec_raw else {}
        price_target = finnhub_get('stock/price-target', {'symbol': symbol}) or {}
    return {'sentiment': sentiment, 'analyst': analyst, 'price_target': price_target}


# ── Curation ─────────────────────────────────────────────────────────────────

def curate_with_validation(client, articles, holding_tickers):
    """
    Ask Claude to pick max 3-5 articles AND validate which holding ticker each
    is *primarily* about. Articles primarily about a non-held company are
    rejected, even if a holding is mentioned tangentially.

    Returns list of articles (subset of input) with 'validated_ticker' set.
    """
    if not articles:
        return []

    holding_set = set(holding_tickers)
    lines = [
        "You are reviewing financial news for a UK retail investor.",
        f"Holdings (the only valid ticker tags): {', '.join(holding_tickers)}",
        "",
        "Pick at most 3-5 articles that are MOST relevant. For each pick, identify",
        "which holding ticker the article is PRIMARILY about. The article must be",
        "fundamentally about that company — not just mention it in passing.",
        "",
        "Reject articles that are primarily about a different company even if a",
        "holding is mentioned (e.g. an article about Bloom Energy that mentions",
        "NVIDIA chips is NOT an NVDA article — skip it).",
        "",
        "Selection criteria:",
        "- Concrete events for current holdings (earnings, guidance, M&A, regulatory, contracts)",
        "- News that materially affects the holder's position",
        "Skip: generic market commentary, daily price moves, articles about other companies.",
        "",
        "Return ONLY a JSON array of objects (max 5):",
        '[{"index": <0-based index>, "ticker": "<one of: ' + ', '.join(holding_tickers) + '>"}]',
        "If nothing in the list qualifies, return [].",
        "",
        "Articles (each labelled with the ticker it was fetched alongside):",
    ]
    for i, a in enumerate(articles):
        title = (a.get('title') or '').strip()[:160]
        hint  = a.get('ticker_hint', '')
        lines.append(f"{i}. [hint:{hint}] {title}")

    try:
        msg = client.messages.create(
            model='claude-haiku-4-5-20251001',
            max_tokens=400,
            messages=[{'role': 'user', 'content': '\n'.join(lines)}],
        )
        raw = msg.content[0].text.strip()
        if raw.startswith('```'):
            parts = raw.split('```')
            raw = parts[1].strip()
            if raw.startswith('json'):
                raw = raw[4:].strip()
        result = json.loads(raw)
    except Exception as e:
        print(f"  Claude curation error: {e}")
        return []

    out = []
    seen_idx = set()
    for r in (result or [])[:MAX_CURATED]:
        if not isinstance(r, dict):
            continue
        idx    = r.get('index')
        ticker = (r.get('ticker') or '').upper()
        if not isinstance(idx, int) or idx < 0 or idx >= len(articles):
            continue
        if ticker not in holding_set:
            print(f"    [reject] index {idx} validated as {ticker!r} which is not a holding")
            continue
        if idx in seen_idx:
            continue
        seen_idx.add(idx)
        out.append({**articles[idx], 'validated_ticker': ticker})
    return out


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("=== Script A: News Fetcher ===")
    now_iso = datetime.now(timezone.utc).isoformat()

    print("\nConnecting to Google Sheets...")
    creds = Credentials.from_service_account_file(SA_FILE, scopes=SCOPES)
    gc    = gspread.authorize(creds)
    sh    = gc.open_by_key(SHEET_ID)
    positions       = read_positions(sh)
    holding_tickers = [p['ticker'] for p in positions]
    print(f"  {len(positions)} holdings: {', '.join(holding_tickers)}")

    client = anthropic.Anthropic(api_key=os.getenv('CLAUDE_API_KEY'))

    # ── Build raw article pool ────────────────────────────────────────────────
    print("\nFetching per-holding news (no DB writes)...")
    article_pool    = []
    holding_context = {}

    for pos in positions:
        ticker = pos['ticker']
        finnhub_sym, yf_sym, exchange = TICKER_CONFIG[ticker]

        articles = []
        if exchange in ('US', 'CA'):
            articles = fetch_finnhub_news(finnhub_sym, hours=24)
            if not articles:
                articles = fetch_yfinance_news(yf_sym)
        else:
            articles = fetch_yfinance_news(yf_sym)

        # Cap per ticker to MAX_PER_TICKER for the pool
        for a in articles[:MAX_PER_TICKER]:
            article_pool.append({**a, 'ticker_hint': ticker})

        # Sentiment + analyst for Script B (separate from news)
        sentiment_data = fetch_holding_sentiment(finnhub_sym, exchange)
        # Headlines for Script B come from raw articles (title only is fine for assessment)
        headlines = [
            {'headline': a['title'], 'source': a['source'], 'datetime': 0}
            for a in articles
        ]
        holding_context[ticker] = {
            'headlines':    headlines,
            'sentiment':    sentiment_data['sentiment'],
            'analyst':      sentiment_data['analyst'],
            'price_target': sentiment_data['price_target'],
            'analyst_info': {},
            'position':     pos,
        }
        print(f"  {ticker} [{exchange}] → {len(articles)} raw articles")

    print(f"\nRaw pool size: {len(article_pool)}")

    # ── Dedup by normalized title ─────────────────────────────────────────────
    seen_norms = set()
    deduped = []
    for a in article_pool:
        norm = normalize_title(a.get('title', ''))
        if not norm or norm in seen_norms:
            continue
        seen_norms.add(norm)
        deduped.append(a)
    print(f"  After title dedup: {len(deduped)}")

    # ── Market scan (still writes market_scan articles for prospect_discovery) ─
    print("\nFetching market scan news...")
    filters            = load_filters()
    stopwords          = set(filters.get('ticker_stopwords', []))
    av_mentions        = fetch_av_market_sentiment(stopwords, limit=50)
    marketaux_mentions = fetch_marketaux_news(stopwords, limit=50)
    yahoo_trending     = fetch_yahoo_trending('US')

    # ── Claude curation + ticker validation ───────────────────────────────────
    print("\nCurating with Claude (validates ticker assignment)...")
    curated = curate_with_validation(client, deduped, holding_tickers)
    print(f"  Curated: {len(curated)} article(s)")
    for a in curated:
        print(f"    - [{a['validated_ticker']}] {a['title'][:80]}")

    # ── Write ONLY the curated articles to news_items ────────────────────────
    # Skip URLs that already exist (the table has a UNIQUE constraint on url).
    # Without this filter we hit unique-violation errors when the same URL
    # was already written by an earlier run with a different id (e.g. Finnhub's
    # numeric id vs sha1-of-url).
    if curated:
        urls_to_check = [a.get('url') for a in curated if a.get('url')]
        existing_urls = set()
        if urls_to_check:
            try:
                from lib.supabase_sink import _get_client
                sb = _get_client()
                if sb:
                    resp = sb.table('news_items').select('url').in_('url', urls_to_check).execute()
                    existing_urls = {r['url'] for r in (resp.data or []) if r.get('url')}
            except Exception as e:
                print(f"  URL existence check failed (non-critical): {e}")

        rows = []
        for a in curated:
            url = a.get('url') or ''
            if url and url in existing_urls:
                print(f"    [skip] URL already exists: {url[:80]}")
                continue
            if url:
                item_id = hashlib.sha1(url.encode()).hexdigest()[:16]
            else:
                key = f"{a['validated_ticker']}|{normalize_title(a['title'])}"
                item_id = 'c_' + hashlib.sha1(key.encode()).hexdigest()[:14]
            rows.append({
                'id':           item_id,
                'published_at': a.get('published_at') or now_iso,
                'tickers':      [a['validated_ticker']],
                'source':       a.get('source', 'unknown'),
                'source_type':  'per_holding',
                'title':        a.get('title', ''),
                'url':          url or None,
                'image_url':    a.get('image_url'),
                'snippet':      a.get('snippet') or '',
                'sentiment':    'neutral',
            })

        if rows:
            write_news_items(rows)
            print(f"  Wrote {len(rows)} curated news_items "
                  f"({len(curated) - len(rows)} skipped as already present)")
        else:
            print(f"  All {len(curated)} curated articles already in DB — nothing to write")
    else:
        print("  Nothing curated — news_items unchanged")

    # ── Save pool for stock_assessor.py ──────────────────────────────────────
    os.makedirs('data', exist_ok=True)
    pool = {
        'run_time':            now_iso,
        'holdings':            holding_context,
        'av_mentions':         {t: items for t, items in av_mentions.items()},
        'marketaux_mentions':  {t: items for t, items in marketaux_mentions.items()},
        'yahoo_trending':      yahoo_trending,
        'selected_news':       curated,
    }
    with open(POOL_PATH, 'w') as f:
        json.dump(pool, f, indent=2, default=str)
    print(f"\nNews pool saved → {POOL_PATH}")


if __name__ == '__main__':
    main()
