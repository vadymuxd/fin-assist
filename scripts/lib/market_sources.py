"""
market_sources.py

Unified data fetchers for holdings_monitor.py and prospect_discovery.py.

Sources:
  - Reddit (public JSON, no auth)  — r/wallstreetbets, r/stocks, r/investing, r/ValueInvesting
  - Finnhub general market news     — tickers mentioned in real news
  - Yahoo Finance trending          — most-watched tickers today
  - Finnhub company-news + sentiment + analyst (per-ticker)
  - yfinance news + analyst info (LSE/EU + fallback)

Plus: a ticker extractor that mines free-form text for $TICKER mentions and
validates against a cached Finnhub symbol universe to eliminate false positives.
"""

import os
import re
import json
import time
import requests
import yfinance as yf
from datetime import datetime, timezone, timedelta
from collections import Counter

FINNHUB_KEY  = os.getenv('FINNHUB_API_KEY', '')
FINNHUB_BASE = 'https://finnhub.io/api/v1'
USER_AGENT   = 'fin-assist/1.0 (+https://github.com/vadymuxd/fin-assist)'
UNIVERSE_CACHE_PATH = 'data/ticker_universe.json'
UNIVERSE_TTL_HOURS  = 24 * 7  # refresh weekly


# ---------------------------------------------------------------------------
# Config loader
# ---------------------------------------------------------------------------

def load_filters(path='config/discovery_filters.json'):
    with open(path) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Ticker universe (for validating extracted uppercase tokens)
# ---------------------------------------------------------------------------

def _load_universe_cache():
    if not os.path.exists(UNIVERSE_CACHE_PATH):
        return None
    try:
        with open(UNIVERSE_CACHE_PATH) as f:
            cache = json.load(f)
        ts = datetime.fromisoformat(cache.get('fetched_at', ''))
        if datetime.now(timezone.utc) - ts < timedelta(hours=UNIVERSE_TTL_HOURS):
            return cache['symbols']
    except Exception:
        return None
    return None


def _save_universe_cache(symbols):
    os.makedirs('data', exist_ok=True)
    with open(UNIVERSE_CACHE_PATH, 'w') as f:
        json.dump({
            'fetched_at': datetime.now(timezone.utc).isoformat(),
            'symbols':    symbols,
        }, f)


def fetch_ticker_universe():
    """
    Return {symbol: {name, exchange, country}} for US + LSE + major EU markets.
    Uses Finnhub /stock/symbol (free tier). Falls back to cache if API fails.
    """
    cached = _load_universe_cache()
    if cached:
        return cached

    if not FINNHUB_KEY:
        return {}

    universe = {}
    # US, London, Toronto, Frankfurt, Paris
    for exchange in ('US', 'L', 'TO', 'DE', 'PA'):
        try:
            resp = requests.get(
                f'{FINNHUB_BASE}/stock/symbol',
                params={'exchange': exchange, 'token': FINNHUB_KEY},
                timeout=20,
            )
            resp.raise_for_status()
            for item in resp.json() or []:
                sym = (item.get('displaySymbol') or item.get('symbol') or '').upper()
                if not sym:
                    continue
                universe[sym] = {
                    'name':     item.get('description', ''),
                    'exchange': exchange,
                    'currency': item.get('currency', ''),
                }
            time.sleep(1)  # be kind to free tier
        except Exception as e:
            print(f"    Universe fetch error ({exchange}): {e}")

    if universe:
        _save_universe_cache(universe)
    return universe


# ---------------------------------------------------------------------------
# Ticker extraction from free-form text
# ---------------------------------------------------------------------------

_DOLLAR_RE     = re.compile(r'\$([A-Z]{1,5})(?:\.[A-Z]{1,2})?\b')
_UPPERCASE_RE  = re.compile(r'\b([A-Z]{2,5})\b')


def extract_tickers(text, universe, stopwords):
    """
    Return set of tickers found in text.
    High-confidence: $TICKER prefix (always accepted if length 1-5).
    Low-confidence: uppercase tokens — only accepted if in universe AND not in stopwords.
    """
    found = set()
    for m in _DOLLAR_RE.findall(text or ''):
        if m and m not in stopwords:
            found.add(m)
    for m in _UPPERCASE_RE.findall(text or ''):
        if m in stopwords:
            continue
        if universe and m in universe:
            found.add(m)
    return found


# ---------------------------------------------------------------------------
# Reddit fetcher (public JSON, no auth)
# ---------------------------------------------------------------------------

def fetch_reddit_mentions(subs, limit, universe, stopwords):
    """
    Scrape hot posts from each sub and count ticker mentions.
    Returns {ticker: [(sub, post_title_snippet), ...]} — mentions with context.
    """
    mentions = {}
    for sub in subs:
        try:
            resp = requests.get(
                f'https://www.reddit.com/r/{sub}/hot.json',
                headers={'User-Agent': USER_AGENT},
                params={'limit': limit},
                timeout=15,
            )
            resp.raise_for_status()
            posts = resp.json().get('data', {}).get('children', [])
            for post in posts:
                data  = post.get('data', {})
                title = data.get('title', '') or ''
                body  = data.get('selftext', '') or ''
                text  = f'{title}\n{body}'
                for ticker in extract_tickers(text, universe, stopwords):
                    mentions.setdefault(ticker, []).append((sub, title[:120]))
            time.sleep(1)  # respect Reddit rate limits
        except Exception as e:
            print(f"    Reddit error (r/{sub}): {e}")
    return mentions


# ---------------------------------------------------------------------------
# Finnhub general market news
# ---------------------------------------------------------------------------

def fetch_finnhub_market_news(stopwords):
    """
    Pull general market news. Each article has a 'related' field with
    comma-separated tickers. Returns {ticker: [(source, headline), ...]}.
    """
    if not FINNHUB_KEY:
        return {}

    mentions = {}
    try:
        resp = requests.get(
            f'{FINNHUB_BASE}/news',
            params={'category': 'general', 'token': FINNHUB_KEY},
            timeout=15,
        )
        resp.raise_for_status()
        for item in resp.json() or []:
            related = (item.get('related') or '').split(',')
            headline = item.get('headline', '') or ''
            source   = item.get('source', 'Finnhub')
            for t in related:
                t = t.strip().upper()
                if t and t not in stopwords:
                    mentions.setdefault(t, []).append((source, headline[:120]))
    except Exception as e:
        print(f"    Finnhub market-news error: {e}")
    return mentions


# ---------------------------------------------------------------------------
# Yahoo Finance trending
# ---------------------------------------------------------------------------

def fetch_yahoo_trending(region='US'):
    """
    Return list of trending tickers from Yahoo Finance (undocumented but stable).
    """
    try:
        resp = requests.get(
            f'https://query1.finance.yahoo.com/v1/finance/trending/{region}',
            headers={'User-Agent': USER_AGENT},
            params={'count': 25},
            timeout=15,
        )
        resp.raise_for_status()
        result = resp.json().get('finance', {}).get('result', [])
        if not result:
            return []
        return [q.get('symbol', '').upper() for q in result[0].get('quotes', []) if q.get('symbol')]
    except Exception as e:
        print(f"    Yahoo trending error: {e}")
        return []


# ---------------------------------------------------------------------------
# Aggregate candidate ranking
# ---------------------------------------------------------------------------

def aggregate_candidates(reddit_mentions, finnhub_mentions, yahoo_trending, filters, excluded):
    """
    Combine all three sources into a ranked list of candidate dicts.

    Each candidate: {ticker, score, sources, evidence}
      - score: total mention count across sources (Reddit posts + Finnhub articles + Yahoo trending boost)
      - sources: list of source labels (e.g. ['reddit:wallstreetbets', 'finnhub-news', 'yahoo-trending'])
      - evidence: up to 5 snippet strings for rationale context

    Candidates with score < min_source_mentions are dropped.
    Candidates in `excluded` (holdings + user excludes) are dropped.
    """
    combined = Counter()
    sources  = {}
    evidence = {}

    for ticker, items in reddit_mentions.items():
        combined[ticker] += len(items)
        for sub, snippet in items[:3]:
            sources.setdefault(ticker, set()).add(f'reddit:{sub}')
            evidence.setdefault(ticker, []).append(f'r/{sub}: {snippet}')

    for ticker, items in finnhub_mentions.items():
        combined[ticker] += len(items)
        for source, headline in items[:3]:
            sources.setdefault(ticker, set()).add(f'finnhub-news')
            evidence.setdefault(ticker, []).append(f'{source}: {headline}')

    for ticker in yahoo_trending:
        # Trending is a weaker signal than a news mention — count it as 1
        combined[ticker] += 1
        sources.setdefault(ticker, set()).add('yahoo-trending')
        evidence.setdefault(ticker, []).append('Yahoo: currently trending')

    min_mentions = filters.get('min_source_mentions', 2)
    max_candidates = filters.get('max_candidates_per_run', 8)

    candidates = []
    for ticker, count in combined.most_common():
        if ticker in excluded:
            continue
        if count < min_mentions:
            continue
        candidates.append({
            'ticker':   ticker,
            'score':    count,
            'sources':  sorted(sources.get(ticker, [])),
            'evidence': evidence.get(ticker, [])[:5],
        })
        if len(candidates) >= max_candidates:
            break
    return candidates


# ---------------------------------------------------------------------------
# Per-ticker deep data (news + sentiment + analyst)
# ---------------------------------------------------------------------------

def finnhub_get(endpoint, params):
    if not FINNHUB_KEY:
        return {}
    try:
        resp = requests.get(
            f'{FINNHUB_BASE}/{endpoint}',
            params={**params, 'token': FINNHUB_KEY},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"    Finnhub error ({endpoint}): {e}")
        return {}


def fetch_ticker_context(symbol, hours=24):
    """
    Fetch recent news + sentiment + analyst consensus + price target.
    `hours` controls the news window (24 for holdings event-check, 168 for prospect scan).
    """
    now       = datetime.now(timezone.utc)
    date_to   = now.strftime('%Y-%m-%d')
    date_from = (now - timedelta(hours=hours)).strftime('%Y-%m-%d')

    news_raw = finnhub_get('company-news', {
        'symbol': symbol,
        'from':   date_from,
        'to':     date_to,
    })
    headlines = [
        {'headline': i.get('headline', ''), 'source': i.get('source', ''), 'datetime': i.get('datetime', 0)}
        for i in (news_raw or [])[:10]
        if i.get('headline')
    ]

    sentiment    = finnhub_get('news-sentiment', {'symbol': symbol})
    rec_raw      = finnhub_get('stock/recommendation', {'symbol': symbol})
    price_target = finnhub_get('stock/price-target', {'symbol': symbol})

    return {
        'headlines':    headlines,
        'sentiment':    sentiment,
        'analyst':      rec_raw[0] if rec_raw else {},
        'price_target': price_target,
    }


def fetch_yfinance_context(symbol):
    """yfinance fallback for LSE/EU or when Finnhub is empty. Returns headlines + analyst info + price/currency."""
    try:
        t        = yf.Ticker(symbol)
        raw_news = t.news or []
        headlines = []
        for item in raw_news[:10]:
            title = (
                item.get('content', {}).get('title')
                or item.get('title')
                or ''
            )
            if title:
                headlines.append({'headline': title, 'source': 'yfinance', 'datetime': 0})

        analyst_info = {}
        price = None
        currency = 'USD'
        try:
            info = t.info
            analyst_info = {
                'targetMeanPrice':         info.get('targetMeanPrice'),
                'targetHighPrice':         info.get('targetHighPrice'),
                'targetLowPrice':          info.get('targetLowPrice'),
                'recommendationKey':       info.get('recommendationKey'),
                'numberOfAnalystOpinions': info.get('numberOfAnalystOpinions'),
                'marketCap':               info.get('marketCap'),
                'longName':                info.get('longName') or info.get('shortName', ''),
            }
            price    = info.get('currentPrice') or info.get('regularMarketPrice')
            currency = info.get('currency', 'USD')
        except Exception:
            pass

        return {
            'headlines':    headlines,
            'analyst_info': analyst_info,
            'price':        price,
            'currency':     currency,
        }
    except Exception as e:
        print(f"    yfinance error ({symbol}): {e}")
        return {'headlines': [], 'analyst_info': {}, 'price': None, 'currency': 'USD'}


# ---------------------------------------------------------------------------
# Exchange inference (used by prospect_discovery.py for new tickers)
# ---------------------------------------------------------------------------

def infer_yf_symbol(ticker, universe_entry=None):
    """
    Guess the yfinance symbol from a raw ticker + universe metadata.
    Yahoo conventions: .L (London), .TO (Toronto), .DE (XETRA), .PA (Paris).
    """
    if not universe_entry:
        return ticker
    exch = universe_entry.get('exchange', '')
    if exch == 'L':
        return f'{ticker}.L'
    if exch == 'TO':
        return f'{ticker}.TO'
    if exch == 'DE':
        return f'{ticker}.DE'
    if exch == 'PA':
        return f'{ticker}.PA'
    return ticker  # US


def infer_exchange_tag(universe_entry):
    """Map Finnhub exchange code → internal tag ('US'/'LSE'/'CA'/'EU')."""
    if not universe_entry:
        return 'US'
    exch = universe_entry.get('exchange', '')
    return {
        'US': 'US',
        'L':  'LSE',
        'TO': 'CA',
        'DE': 'EU',
        'PA': 'EU',
    }.get(exch, 'US')
