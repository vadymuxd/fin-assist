"""
market_sources.py

Unified data fetchers for holdings_monitor.py and prospect_discovery.py.

Discovery sources (prospect_discovery.py) — weighted aggregate scoring:
  - Alpha Vantage NEWS_SENTIMENT market scan  — news articles with built-in sentiment (weight 3)
  - Marketaux news scan                       — independent sentiment + entity extraction (weight 2)
  - Yahoo Finance trending                    — volume/attention signal (weight 1)

Per-ticker scoring (both scripts):
  - Finnhub company-news             — recent headlines per ticker (free tier)
  - Alpha Vantage NEWS_SENTIMENT     — per-ticker sentiment when Finnhub 403s
  - yfinance                         — analyst info, price targets, LSE/EU news

Ticker universe: Finnhub /stock/symbol (US exchange, free tier)
"""

import os
import re
import json
import time
import requests
import yfinance as yf
from datetime import datetime, timezone, timedelta
from collections import Counter

FINNHUB_KEY      = os.getenv('FINNHUB_API_KEY', '')
FINNHUB_BASE     = 'https://finnhub.io/api/v1'
ALPHAVANTAGE_KEY = os.getenv('ALPHAVANTAGE_API_KEY', '')
ALPHAVANTAGE_BASE = 'https://www.alphavantage.co/query'
MARKETAUX_KEY    = os.getenv('MARKETAUX_API_KEY', '')
MARKETAUX_BASE   = 'https://api.marketaux.com/v1/news/all'
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
# Alpha Vantage market-wide news sentiment scan (discovery source, weight 3)
# ---------------------------------------------------------------------------

def fetch_av_market_sentiment(stopwords, limit=50):
    """
    Scan Alpha Vantage NEWS_SENTIMENT without a specific ticker — returns up to
    `limit` recent market news articles, each with per-ticker sentiment scores.

    Returns {ticker: [(score, snippet), ...]} where score is the weighted
    sentiment signal (relevance × sentiment, positive only).
    Free tier: 1 call, counts against 500/day quota.
    """
    if not ALPHAVANTAGE_KEY:
        print("    Alpha Vantage key not set — skipping market news scan")
        return {}

    mentions = {}
    try:
        resp = requests.get(
            ALPHAVANTAGE_BASE,
            params={
                'function': 'NEWS_SENTIMENT',
                'topics':   'technology,earnings,ipo,financial_markets,retail_wholesale',
                'sort':     'RELEVANCE',
                'limit':    limit,
                'apikey':   ALPHAVANTAGE_KEY,
            },
            headers={'User-Agent': USER_AGENT},
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()

        if 'Note' in data or 'Information' in data:
            print("    Alpha Vantage rate limit hit for market news scan")
            return {}

        articles = data.get('feed', [])
        for article in articles:
            title = article.get('title', '')
            for ts in article.get('ticker_sentiment', []):
                ticker = (ts.get('ticker') or '').upper()
                if not ticker or ticker in stopwords or '.' in ticker:
                    continue
                try:
                    relevance = float(ts.get('relevance_score', 0))
                    sentiment = float(ts.get('ticker_sentiment_score', 0))
                except (ValueError, TypeError):
                    continue
                # Only positive sentiment contributes to discovery
                if sentiment <= 0.1 or relevance < 0.3:
                    continue
                weighted = round(relevance * sentiment, 3)
                label = ts.get('ticker_sentiment_label', '')
                snippet = f"AV news: {label} ({weighted:.2f}) — {title[:80]}"
                mentions.setdefault(ticker, []).append((weighted, snippet))

        print(f"  AV market news scan: {len(mentions)} tickers with positive sentiment ({len(articles)} articles)")
    except Exception as e:
        print(f"    AV market news scan error: {e}")
    return mentions


# ---------------------------------------------------------------------------
# Marketaux news sentiment scan (discovery source, weight 2)
# ---------------------------------------------------------------------------

def fetch_marketaux_news(stopwords, limit=50):
    """
    Scan Marketaux for recent financial news with entity-level sentiment.
    Free tier: 100 req/day. limit=50 articles per call (one request).
    Returns {ticker: [(score, snippet), ...]} for tickers with positive sentiment.
    """
    if not MARKETAUX_KEY:
        print("    Marketaux key not set — skipping")
        return {}

    mentions = {}
    try:
        resp = requests.get(
            MARKETAUX_BASE,
            params={
                'filter_entities': 'true',
                'language':        'en',
                'limit':           limit,
                'api_token':       MARKETAUX_KEY,
            },
            headers={'User-Agent': USER_AGENT},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()

        # Graceful handling of quota errors
        if data.get('error'):
            print(f"    Marketaux error: {data['error'].get('message', 'unknown')}")
            return {}

        articles = data.get('data', [])
        for article in articles:
            title = article.get('title', '')
            for entity in article.get('entities', []):
                ticker = (entity.get('symbol') or '').upper()
                if not ticker or ticker in stopwords:
                    continue
                try:
                    score = float(entity.get('sentiment_score', 0))
                except (ValueError, TypeError):
                    continue
                if score <= 0.1:
                    continue
                snippet = f"Marketaux: positive ({score:.2f}) — {title[:80]}"
                mentions.setdefault(ticker, []).append((score, snippet))

        print(f"  Marketaux news scan: {len(mentions)} tickers with positive sentiment ({len(articles)} articles)")
    except Exception as e:
        print(f"    Marketaux news scan error: {e}")
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

def aggregate_candidates(av_mentions, marketaux_mentions, yahoo_trending, filters, excluded, universe=None):
    """
    Combine weighted discovery sources into a ranked list of candidate dicts.

    Weights: Alpha Vantage sentiment=3, Marketaux=2, Yahoo trending=1
    score = sum of (source_weight × sentiment_scores) per ticker

    Candidates must appear in ≥ min_source_mentions distinct sources.
    Candidates in `excluded` (holdings + user excludes) are dropped.
    Country filtering happens later in prospect_discovery.py via yfinance data.
    """

    scores       = {}
    sources      = {}
    evidence     = {}
    source_count = Counter()

    # Alpha Vantage market news sentiment (weight 3)
    for ticker, items in av_mentions.items():
        total = sum(s for s, _ in items)
        scores[ticker]  = scores.get(ticker, 0) + 3 * total
        sources.setdefault(ticker, set()).add('av-news-sentiment')
        source_count[ticker] += 1
        for _, snippet in items[:3]:
            evidence.setdefault(ticker, []).append(snippet)

    # Marketaux entity sentiment (weight 2)
    for ticker, items in marketaux_mentions.items():
        total = sum(s for s, _ in items)
        scores[ticker]  = scores.get(ticker, 0) + 2 * total
        sources.setdefault(ticker, set()).add('marketaux')
        source_count[ticker] += 1
        for _, snippet in items[:2]:
            evidence.setdefault(ticker, []).append(snippet)

    # Yahoo trending — attention signal (weight 1)
    for ticker in yahoo_trending:
        scores[ticker] = scores.get(ticker, 0) + 1
        sources.setdefault(ticker, set()).add('yahoo-trending')
        source_count[ticker] += 1
        evidence.setdefault(ticker, []).append('Yahoo: currently trending')

    min_mentions   = filters.get('min_source_mentions', 2)
    max_candidates = filters.get('max_candidates_per_run', 8)

    candidates = []
    for ticker, total_score in sorted(scores.items(), key=lambda x: -x[1]):
        if ticker in excluded:
            continue
        if source_count[ticker] < min_mentions:
            continue
        candidates.append({
            'ticker':   ticker,
            'score':    round(total_score, 3),
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


def fetch_alpha_vantage_sentiment(symbol):
    """
    Fetch news sentiment from Alpha Vantage (free tier: 500 calls/day).
    Returns a dict matching Finnhub's news-sentiment structure:
      {'sentiment': {'bullishPercent': 0.65, 'bearishPercent': 0.15}}
    Returns {} if key not set or request fails.
    """
    if not ALPHAVANTAGE_KEY:
        return {}
    try:
        resp = requests.get(
            ALPHAVANTAGE_BASE,
            params={
                'function': 'NEWS_SENTIMENT',
                'tickers':  symbol,
                'apikey':   ALPHAVANTAGE_KEY,
                'limit':    50,
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()

        # Gracefully handle rate-limit / info messages from Alpha Vantage
        if 'Note' in data or 'Information' in data:
            print(f"    Alpha Vantage rate limit hit for {symbol}")
            return {}

        feed = data.get('feed', [])
        if not feed:
            return {}

        # Average the ticker-specific sentiment scores across all articles
        scores = []
        for article in feed:
            for ts in article.get('ticker_sentiment', []):
                if ts.get('ticker', '').upper() == symbol.upper():
                    try:
                        scores.append(float(ts['ticker_sentiment_score']))
                    except (ValueError, KeyError):
                        pass

        if not scores:
            # Fall back to overall article sentiment
            for article in feed:
                try:
                    scores.append(float(article.get('overall_sentiment_score', 0)))
                except (ValueError, TypeError):
                    pass

        if not scores:
            return {}

        avg = sum(scores) / len(scores)
        # Map [-1, 1] → bullish/bearish percentages (neutral absorbs the middle)
        bullish = max(0.0, avg)
        bearish = max(0.0, -avg)
        neutral = 1.0 - bullish - bearish

        print(f"    Alpha Vantage sentiment ({symbol}): avg={avg:.3f} bull={bullish:.0%} bear={bearish:.0%} ({len(scores)} articles)")
        return {
            'sentiment': {
                'bullishPercent': round(bullish, 3),
                'bearishPercent': round(bearish, 3),
                'neutralPercent': round(neutral, 3),
                'articlesInLastWeek': len(feed),
            }
        }
    except Exception as e:
        print(f"    Alpha Vantage error ({symbol}): {e}")
        return {}


def fetch_ticker_context(symbol, hours=24):
    """
    Fetch recent news + sentiment + analyst consensus + price target.
    `hours` controls the news window (24 for holdings event-check, 168 for prospect scan).
    Sentiment: Finnhub first (paid tier), falls back to Alpha Vantage (free tier).
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
    # Alpha Vantage fallback when Finnhub sentiment is blocked (free tier)
    if not sentiment:
        sentiment = fetch_alpha_vantage_sentiment(symbol)

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
            country  = info.get('country', '')
        except Exception:
            pass

        return {
            'headlines':    headlines,
            'analyst_info': analyst_info,
            'price':        price,
            'currency':     currency,
            'country':      country,
        }
    except Exception as e:
        print(f"    yfinance error ({symbol}): {e}")
        return {'headlines': [], 'analyst_info': {}, 'price': None, 'currency': 'USD', 'country': ''}


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
