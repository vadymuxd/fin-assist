#!/usr/bin/env python3
"""
market_worker.py — Daily investment pipeline worker.

Replaces: news_fetcher.py, stock_assessor.py, alert_dispatcher.py

Modes (called separately in GHA with 5-min sleep between each):
  --mode fetch     Script A: fetch + curate news → data/news_pool.json
  --mode assess    Script B: assess holdings + prospects → data/assessments.json
  --mode dispatch  Script C: 48h dedup, log to Supabase, send Telegram

Intermediate files act as checkpoints — if dispatch fails, re-run
--mode dispatch against the existing assessments.json without re-fetching.
"""

import os
import json
import hashlib
import argparse
import requests
import yfinance as yf
import anthropic
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from dotenv import load_dotenv
import gspread
from google.oauth2.service_account import Credentials

from lib.market_sources import (
    fetch_av_market_sentiment,
    finnhub_get,
    load_filters,
)
from lib.supabase_sink import (
    write_news_items,
    get_recently_alerted_tickers,
    write_holding_alert,
    write_prospect_alert,
    write_holding_prices,
    get_holding_price_history,
)

load_dotenv()

# ── Constants ─────────────────────────────────────────────────────────────────

SHEET_ID  = os.getenv('PORTFOLIO_SHEET_ID')
SA_FILE   = os.getenv('GOOGLE_APPLICATION_CREDENTIALS', 'config/service_account.json')
SCOPES    = ['https://www.googleapis.com/auth/spreadsheets']

POOL_PATH        = 'data/news_pool.json'
ASSESSMENTS_PATH = 'data/assessments.json'
THRESHOLDS_PATH  = 'config/thresholds.json'

LONDON_TZ   = ZoneInfo('Europe/London')
DEDUP_HOURS = 48

SELL_THRESHOLD_DEFAULTS = {
    'stop_loss_pct':               15.0,
    'trailing_stop_pct':           12.0,
    'concentration_pct':           30.0,
    'trailing_high_lookback_days': 30,
    'min_gain_for_trailing_pct':   15.0,
}

FINNHUB_KEY  = os.getenv('FINNHUB_API_KEY', '')
FINNHUB_BASE = 'https://finnhub.io/api/v1'

MAX_PER_TICKER = 4
MAX_CURATED    = 5
MAX_PROSPECTS  = 10

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


# ── Shared helpers ────────────────────────────────────────────────────────────

def parse_float(val):
    if val is None or val == '':
        return 0.0
    try:
        return float(str(val).replace('£', '').replace(',', '').replace('%', '').strip())
    except (ValueError, TypeError):
        return 0.0


def normalize_title(title):
    if not title:
        return ''
    t = title.lower().strip()
    for ch in '"\'“”():.,!?-—–|':
        t = t.replace(ch, ' ')
    return ' '.join(t.split())


def escape_html(text):
    return str(text).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def load_sell_thresholds():
    """Sell-signal thresholds from config/thresholds.json, with safe defaults."""
    thr = dict(SELL_THRESHOLD_DEFAULTS)
    try:
        with open(THRESHOLDS_PATH) as f:
            thr.update((json.load(f) or {}).get('sell_signals', {}))
    except Exception as e:
        print(f"  thresholds.json load failed ({e}) — using defaults")
    return thr


def send_telegram(text):
    token   = os.getenv('TELEGRAM_BOT_TOKEN')
    chat_id = os.getenv('TELEGRAM_CHAT_ID')
    if not token or not chat_id:
        print("  Telegram not configured — printing instead:")
        print(text)
        return False
    chunks = [text[i:i+4000] for i in range(0, len(text), 4000)]
    ok = True
    for chunk in chunks:
        try:
            resp = requests.post(
                f'https://api.telegram.org/bot{token}/sendMessage',
                json={'chat_id': chat_id, 'text': chunk, 'parse_mode': 'HTML'},
                timeout=10,
            )
            resp.raise_for_status()
        except Exception as e:
            print(f"  Telegram error: {e}")
            ok = False
    return ok


def call_claude(client, prompt, ticker):
    try:
        msg = client.messages.create(
            model='claude-haiku-4-5-20251001',
            max_tokens=400,
            messages=[{'role': 'user', 'content': prompt}],
        )
        raw = msg.content[0].text.strip()
        if raw.startswith('```'):
            parts = raw.split('```')
            raw = parts[1].strip()
            if raw.startswith('json'):
                raw = raw[4:].strip()
        return json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"    JSON parse error for {ticker}: {e}")
        return None
    except Exception as e:
        print(f"    Claude API error for {ticker}: {e}")
        return None


# ── Mode: fetch ───────────────────────────────────────────────────────────────

def read_positions(sh):
    ws = sh.worksheet('Investments')
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


def fetch_finnhub_news(symbol, hours=24):
    if not FINNHUB_KEY:
        return []
    now       = datetime.now(timezone.utc)
    date_to   = now.strftime('%Y-%m-%d')
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
    for i in items[:MAX_PER_TICKER * 2]:
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
    try:
        raw = yf.Ticker(symbol).news or []
    except Exception as e:
        print(f"    yfinance news error ({symbol}): {e}")
        return []
    out     = []
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
        thumb       = content.get('thumbnail') or item.get('thumbnail') or {}
        image_url   = None
        resolutions = thumb.get('resolutions', []) or []
        if resolutions:
            image_url = resolutions[-1].get('url')
        elif thumb.get('originalUrl'):
            image_url = thumb['originalUrl']
        out.append({
            'title':        title.strip(),
            'url':          url,
            'image_url':    image_url,
            'snippet':      (content.get('summary') or content.get('description') or '')[:500],
            'published_at': published_at,
            'source':       publisher,
        })
    return out


def fetch_holding_sentiment(symbol, exchange):
    """Finnhub-only sentiment + analyst context for US/CA tickers.
    The Alpha Vantage per-ticker fallback was removed — it burned ~15 AV calls
    a day against the 25/day free cap and barely moved Claude's verdict. AV's
    daily quota is now reserved entirely for the morning prospect scan."""
    sentiment    = {}
    analyst      = {}
    price_target = {}
    if exchange in ('US', 'CA'):
        sentiment    = finnhub_get('news-sentiment', {'symbol': symbol}) or {}
        rec_raw      = finnhub_get('stock/recommendation', {'symbol': symbol}) or []
        analyst      = rec_raw[0] if rec_raw else {}
        price_target = finnhub_get('stock/price-target', {'symbol': symbol}) or {}
    return {'sentiment': sentiment, 'analyst': analyst, 'price_target': price_target}


def curate_with_validation(client, articles, holding_tickers):
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
        lines.append(f"{i}. [hint:{a.get('ticker_hint', '')}] {(a.get('title') or '').strip()[:160]}")
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
    out      = []
    seen_idx = set()
    for r in (result or [])[:MAX_CURATED]:
        if not isinstance(r, dict):
            continue
        idx    = r.get('index')
        ticker = (r.get('ticker') or '').upper()
        if not isinstance(idx, int) or idx < 0 or idx >= len(articles):
            continue
        if ticker not in holding_set:
            print(f"    [reject] index {idx} validated as {ticker!r} — not a holding")
            continue
        if idx in seen_idx:
            continue
        seen_idx.add(idx)
        out.append({**articles[idx], 'validated_ticker': ticker})
    return out


def run_fetch():
    print("=== market_worker --mode fetch ===")
    now_iso = datetime.now(timezone.utc).isoformat()

    print("\nConnecting to Google Sheets...")
    creds = Credentials.from_service_account_file(SA_FILE, scopes=SCOPES)
    sh    = gspread.authorize(creds).open_by_key(SHEET_ID)
    positions       = read_positions(sh)
    holding_tickers = [p['ticker'] for p in positions]
    print(f"  {len(positions)} holdings: {', '.join(holding_tickers)}")

    # Append today's prices for the trailing-stop signal. Upsert on (ticker,
    # date) — re-running the same day just overwrites, so the close run's
    # price is the one that sticks.
    today  = datetime.now(LONDON_TZ).strftime('%Y-%m-%d')
    prices = {p['ticker']: p['current_price'] for p in positions if p['current_price'] > 0}
    if prices:
        write_holding_prices(today, prices)
        print(f"  Price history: recorded {len(prices)} prices for {today}")

    client = anthropic.Anthropic(api_key=os.getenv('CLAUDE_API_KEY'))

    print("\nFetching per-holding news (no DB writes yet)...")
    article_pool    = []
    holding_context = {}

    for pos in positions:
        ticker                         = pos['ticker']
        finnhub_sym, yf_sym, exchange  = TICKER_CONFIG[ticker]

        if exchange in ('US', 'CA'):
            articles = fetch_finnhub_news(finnhub_sym, hours=24) or fetch_yfinance_news(yf_sym)
        else:
            articles = fetch_yfinance_news(yf_sym)

        for a in articles[:MAX_PER_TICKER]:
            article_pool.append({**a, 'ticker_hint': ticker})

        sentiment_data = fetch_holding_sentiment(finnhub_sym, exchange)
        holding_context[ticker] = {
            'headlines':    [{'headline': a['title'], 'source': a['source'], 'datetime': 0}
                             for a in articles],
            'sentiment':    sentiment_data['sentiment'],
            'analyst':      sentiment_data['analyst'],
            'price_target': sentiment_data['price_target'],
            'analyst_info': {},
            'position':     pos,
        }
        print(f"  {ticker} [{exchange}] → {len(articles)} raw articles")

    print(f"\nRaw pool size: {len(article_pool)}")
    seen_norms = set()
    deduped    = []
    for a in article_pool:
        norm = normalize_title(a.get('title', ''))
        if not norm or norm in seen_norms:
            continue
        seen_norms.add(norm)
        deduped.append(a)
    print(f"  After title dedup: {len(deduped)}")

    # Prospect discovery signal: one Alpha Vantage market scan per day.
    # AV free tier is 25 req/day — a single morning scan is rock-solid, three
    # daily scans were not. Midday/close runs skip it; prospects are assessed
    # on the morning run only (48h dedup means one scan a day is plenty).
    is_morning  = datetime.now(LONDON_TZ).hour < 11
    av_mentions = {}
    if is_morning:
        print("\nFetching AV market scan (morning run — prospect discovery)...")
        filters     = load_filters()
        stopwords   = set(filters.get('ticker_stopwords', []))
        av_mentions = fetch_av_market_sentiment(stopwords, limit=50)
    else:
        print("\nSkipping AV market scan — prospect discovery runs on the morning run only.")

    print("\nCurating with Claude (validates ticker assignment)...")
    curated = curate_with_validation(client, deduped, holding_tickers)
    print(f"  Curated: {len(curated)} article(s)")
    for a in curated:
        print(f"    - [{a['validated_ticker']}] {a['title'][:80]}")

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
                print(f"    [skip] already in DB: {url[:80]}")
                continue
            item_id = (
                hashlib.sha1(url.encode()).hexdigest()[:16]
                if url
                else 'c_' + hashlib.sha1(
                    f"{a['validated_ticker']}|{normalize_title(a['title'])}".encode()
                ).hexdigest()[:14]
            )
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
            print(f"  Wrote {len(rows)} news_items ({len(curated) - len(rows)} skipped)")
        else:
            print(f"  All {len(curated)} articles already in DB — nothing to write")
    else:
        print("  Nothing curated — news_items unchanged")

    os.makedirs('data', exist_ok=True)
    with open(POOL_PATH, 'w') as f:
        json.dump({
            'run_time':      now_iso,
            'holdings':      holding_context,
            'av_mentions':   {t: items for t, items in av_mentions.items()},
            'selected_news': curated,
        }, f, indent=2, default=str)
    print(f"\nNews pool saved → {POOL_PATH}")


# ── Mode: assess ──────────────────────────────────────────────────────────────

def build_holding_prompt(ticker, name, position, data):
    qty     = position.get('qty', 0)
    avg_buy = position.get('avg_buy', 0)
    current = position.get('current_price', 0)
    pnl_pct = ((current - avg_buy) / avg_buy * 100) if avg_buy else 0
    sign    = '+' if pnl_pct >= 0 else ''
    lines   = [
        f"Review {ticker} ({name}) for a UK retail investor who HOLDS this position.",
        f"Position: {qty:.4f} shares | Avg buy £{avg_buy:.4f} | Current £{current:.4f} | P&L {sign}{pnl_pct:.1f}%",
        "",
        "Task: is there a CONCRETE, SPECIFIC reason to act on this position based on recent news?",
        "Only flag if a real event occurred — not general market sentiment, analyst opinions, or daily price moves.",
        "",
    ]
    headlines = data.get('headlines', [])
    if headlines:
        lines.append("Recent news:")
        for i, h in enumerate(headlines[:8], 1):
            lines.append(f"  {i}. {h.get('headline') if isinstance(h, dict) else str(h)}")
    else:
        lines.append("Recent news: (none)")
    s_block = (data.get('sentiment') or {}).get('sentiment') or {}
    if s_block:
        lines.append(
            f"\nSentiment: {s_block.get('bullishPercent', 0)*100:.0f}% bullish, "
            f"{s_block.get('bearishPercent', 0)*100:.0f}% bearish"
        )
    a = data.get('analyst') or {}
    if a and any(a.get(k, 0) for k in ('strongBuy', 'buy', 'hold', 'sell', 'strongSell')):
        lines.append(
            f"Analysts: StrongBuy {a.get('strongBuy',0)} Buy {a.get('buy',0)} "
            f"Hold {a.get('hold',0)} Sell {a.get('sell',0)} StrongSell {a.get('strongSell',0)}"
        )
    lines += [
        "",
        "STEP 1 — score the position 1-10 for how it looks right now given the news:",
        "  8-10 = strong, thesis intact or improving",
        "  6-7  = comfortable hold",
        "  5    = neutral, nothing notable in the news",
        "  3-4  = concerns building (weak guidance, sector pressure, deteriorating fundamentals)",
        "  1-2  = thesis broken, exit-worthy",
        "",
        "STEP 2 — map the score to an action. The score DRIVES the action:",
        "  8-10 AND a concrete positive catalyst -> BUY_MORE",
        "  5-7                                   -> NONE",
        "  3-4                                   -> TRIM",
        "  1-2                                   -> SELL",
        "A score of 4 or below MUST produce TRIM or SELL — steady deterioration is a",
        "valid reason to act even without one dramatic headline. Never return NONE",
        "with a score of 4 or below.",
        "Pure analyst-rating noise, macro mood or daily price wiggle is a score 5 (NONE).",
        "",
        "Return ONLY a JSON object (no markdown):",
        '{',
        '  "score": <integer 1-10>,',
        '  "action": "<SELL|TRIM|BUY_MORE|NONE>",',
        '  "event": "<short phrase: what drove this, or empty string>",',
        '  "rationale": "<1-2 sentences: what is happening and why it matters for this holder>"',
        '}',
    ]
    return '\n'.join(lines)


def build_prospect_prompt(ticker, av_items):
    lines = [
        f"Evaluate {ticker} as a potential BUY for a UK retail investor.",
        "Only recommend BUY if there is a concrete, specific investment reason today.",
        "",
        "Evidence from the Alpha Vantage market news scan:",
    ]
    for _, snippet in (av_items or [])[:4]:
        lines.append(f"  - {snippet}")
    lines += [
        "",
        "Return ONLY a JSON object (no markdown):",
        '{',
        '  "recommendation": "<BUY|PASS>",',
        '  "score": <integer 1-10>,',
        '  "thesis": "<2-3 sentences: specific catalyst, why now, main risk>",',
        '  "name": "<company full name>"',
        '}',
        "",
        "recommendation rules — default to PASS:",
        "  PASS = generic buzz, no clear catalyst, or score < 7",
        "  BUY  = score ≥ 7 with a concrete thesis (specific news event, valuation trigger, catalyst)",
    ]
    return '\n'.join(lines)


def compute_price_signal(position, total_portfolio, price_history, thr):
    """
    Deterministic sell signal from price data alone — no API, fires for every
    holding (US, LSE, EU). Returns an assessment dict or None.

    Priority: trailing-stop (protect a winner) > stop-loss (cut a loser) >
    concentration (single-position risk). At most one signal per ticker.
    """
    ticker  = position.get('ticker', '')
    qty     = position.get('qty', 0) or 0
    avg_buy = position.get('avg_buy', 0) or 0
    price   = position.get('current_price', 0) or 0
    if qty <= 0 or price <= 0:
        return None

    pnl_pct  = ((price - avg_buy) / avg_buy * 100) if avg_buy else 0.0
    value    = qty * price
    conc_pct = (value / total_portfolio * 100) if total_portfolio else 0.0

    # Trailing-stop — only for positions sitting on a real gain. This protects
    # profit and is distinct from stop-loss (which cuts a losing position).
    hist = price_history.get(ticker, [])
    if hist and pnl_pct >= thr['min_gain_for_trailing_pct']:
        rolling_high = max(hist + [price])
        if rolling_high > 0:
            drop = (rolling_high - price) / rolling_high * 100
            if drop >= thr['trailing_stop_pct']:
                return {
                    'ticker': ticker, 'action': 'TRIM', 'score': 3, 'signal': 'price',
                    'event': f'Down {drop:.0f}% from {len(hist)}d high',
                    'rationale': (
                        f'Fallen {drop:.1f}% from a recent high of £{rolling_high:.2f} '
                        f'to £{price:.2f}, still {pnl_pct:+.0f}% vs cost — consider '
                        f'trimming to lock in the gain.'
                    ),
                }

    # Stop-loss — position is underwater past the threshold vs cost basis.
    if avg_buy and pnl_pct <= -thr['stop_loss_pct']:
        return {
            'ticker': ticker, 'action': 'SELL', 'score': 2, 'signal': 'price',
            'event': f'Down {abs(pnl_pct):.0f}% vs cost',
            'rationale': (
                f'{pnl_pct:.1f}% below the average buy of £{avg_buy:.2f} '
                f'(now £{price:.2f}) — review whether the thesis still holds.'
            ),
        }

    # Concentration — single position is too large a share of the portfolio.
    if conc_pct >= thr['concentration_pct']:
        return {
            'ticker': ticker, 'action': 'TRIM', 'score': 4, 'signal': 'price',
            'event': f'{conc_pct:.0f}% of portfolio',
            'rationale': (
                f'Now {conc_pct:.1f}% of the portfolio (£{value:,.0f}) — consider '
                f'trimming to reduce single-position risk.'
            ),
        }
    return None


def run_assess():
    print("=== market_worker --mode assess ===")

    if not os.path.exists(POOL_PATH):
        print(f"  {POOL_PATH} not found — run --mode fetch first")
        return

    with open(POOL_PATH) as f:
        pool = json.load(f)

    run_time    = pool.get('run_time', datetime.now(timezone.utc).isoformat())
    holdings    = pool.get('holdings', {})
    av_mentions = pool.get('av_mentions', {})

    thr           = load_sell_thresholds()
    price_history = get_holding_price_history(thr['trailing_high_lookback_days'])
    client        = anthropic.Anthropic(api_key=os.getenv('CLAUDE_API_KEY'))

    # one assessment dict per ticker, keyed by ticker
    holding_assessments = {}

    # ── Deterministic price-based sell signals (no API, every holding) ───────
    total_portfolio = sum(
        ((h.get('position') or {}).get('qty', 0) or 0)
        * ((h.get('position') or {}).get('current_price', 0) or 0)
        for h in holdings.values()
    )
    print(f"\nPrice-based sell signals (portfolio £{total_portfolio:,.0f})...")
    for ticker, data in holdings.items():
        position = data.get('position') or {}
        signal   = compute_price_signal(position, total_portfolio, price_history, thr)
        if signal:
            signal.update({
                'type':     'holding',
                'name':     position.get('name', ticker),
                'run_time': run_time,
            })
            holding_assessments[ticker] = signal
            print(f"  {ticker}: {signal['action']} — {signal['event']}")
    if not holding_assessments:
        print("  none triggered")

    # ── News-based assessment (Claude, holdings with headlines) ──────────────
    print(f"\nNews assessment of {len(holdings)} holdings...")
    for ticker, data in holdings.items():
        position  = data.get('position', {})
        name      = position.get('name', ticker)
        headlines = data.get('headlines', [])
        if not headlines:
            print(f"  {ticker}: no headlines — skip")
            continue
        result = call_claude(client, build_holding_prompt(ticker, name, position, data), ticker)
        if not result:
            continue
        action = result.get('action', 'NONE')
        score  = result.get('score', 5)
        if action == 'NONE':
            print(f"  {ticker}: NONE (score {score})")
            continue
        event     = (result.get('event') or '').strip()
        rationale = (result.get('rationale') or '').strip()
        print(f"  {ticker}: {action} (score {score}) — {event or 'no event'}")
        if ticker in holding_assessments:
            # Price signal already fired — fold the news context into it.
            if rationale:
                holding_assessments[ticker]['rationale'] += f' News: {rationale}'
            print(f"    (merged into price signal {holding_assessments[ticker]['action']})")
        else:
            holding_assessments[ticker] = {
                'type': 'holding', 'ticker': ticker, 'name': name,
                'action': action, 'score': score, 'signal': 'news',
                'event': event, 'rationale': rationale, 'run_time': run_time,
            }

    # ── Prospect discovery (AV market scan signal — morning run only) ────────
    prospect_tickers = set(av_mentions.keys()) - set(holdings.keys())

    def signal_score(t):
        return sum(s for s, _ in av_mentions.get(t, []))

    ranked = [t for t in sorted(prospect_tickers, key=signal_score, reverse=True)[:MAX_PROSPECTS]
              if signal_score(t) > 0]
    prospect_assessments = []
    if ranked:
        print(f"\nAssessing {len(ranked)} prospect(s)...")
        for ticker in ranked:
            result = call_claude(
                client, build_prospect_prompt(ticker, av_mentions.get(ticker, [])), ticker,
            )
            if not result:
                continue
            rec   = result.get('recommendation', 'PASS')
            score = result.get('score', 5)
            if rec != 'BUY' or score < 7:
                print(f"  {ticker}: {rec} (score {score}) — skip")
                continue
            print(f"  {ticker}: BUY (score {score})")
            prospect_assessments.append({
                'type': 'prospect', 'ticker': ticker, 'name': result.get('name', ticker),
                'action': 'BUY', 'score': score, 'signal': 'news', 'event': '',
                'rationale': result.get('thesis', '').strip(), 'run_time': run_time,
            })
    else:
        print("\nNo prospect candidates this run (AV scan empty or midday/close run).")

    assessments = list(holding_assessments.values()) + prospect_assessments
    os.makedirs('data', exist_ok=True)
    with open(ASSESSMENTS_PATH, 'w') as f:
        json.dump(assessments, f, indent=2)
    print(f"\n{len(assessments)} actionable assessment(s) saved → {ASSESSMENTS_PATH}")
    if not assessments:
        print("  No sell signals, no prospects — quiet run.")


# ── Mode: dispatch ────────────────────────────────────────────────────────────

def format_telegram(new_alerts):
    now_str   = datetime.now(timezone.utc).strftime('%d %b %Y, %H:%M UTC')
    lines     = []
    holdings  = [a for a in new_alerts if a['type'] == 'holding']
    prospects = [a for a in new_alerts if a['type'] == 'prospect']

    if holdings:
        lines += [f'⚠️ <b>HOLDINGS — SELL SIGNALS</b> — {now_str}', '']
        for a in holdings:
            action = a['action']
            emoji  = '🔴' if action in ('SELL', 'EXIT', 'TRIM') else '🟢'
            tag    = '📉 price' if a.get('signal') == 'price' else '📰 news'
            lines.append(
                f'{emoji} <b>{escape_html(a["ticker"])}</b> — '
                f'{escape_html(a.get("event") or "signal")}  <i>({tag})</i>'
            )
            lines.append(f'   Action: <b>{escape_html(action)}</b> | Score {a["score"]}/10')
            if a.get('rationale'):
                lines.append(f'   {escape_html(a["rationale"])}')
            lines.append('')

    if prospects:
        if lines:
            lines.append('')
        lines += [f'🔭 <b>NEW PROSPECT</b> — {now_str}', '']
        for a in prospects:
            lines.append(f'🟢 <b>{escape_html(a["ticker"])}</b> {escape_html(a.get("name", ""))} | {a["score"]}/10 BUY')
            if a.get('rationale'):
                lines.append(f'   {escape_html(a["rationale"])}')
            lines.append('')

    return '\n'.join(lines).strip()


def run_dispatch():
    print("=== market_worker --mode dispatch ===")

    if not os.path.exists(ASSESSMENTS_PATH):
        print(f"  {ASSESSMENTS_PATH} not found — nothing to dispatch")
        return

    with open(ASSESSMENTS_PATH) as f:
        assessments = json.load(f)

    if not assessments:
        print("  No actionable assessments — done")
        return

    print(f"  {len(assessments)} assessment(s) to process")

    already_alerted = get_recently_alerted_tickers(hours=DEDUP_HOURS)
    print(f"  Tickers alerted in last {DEDUP_HOURS}h: {sorted(already_alerted) or 'none'}")

    new_alerts = []
    suppressed = []
    for a in assessments:
        if a['ticker'] in already_alerted:
            suppressed.append(a)
            print(f"  [dedup] {a['ticker']} — suppressed (alerted within {DEDUP_HOURS}h)")
        else:
            new_alerts.append(a)

    if not new_alerts:
        print(f"\n  All {len(assessments)} suppressed by dedup — no messages sent")
        return

    print(f"\n  {len(new_alerts)} new signal(s), {len(suppressed)} suppressed")

    run_id   = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
    run_time = datetime.now(timezone.utc).isoformat()

    for a in new_alerts:
        if a['type'] == 'holding':
            write_holding_alert(run_id, run_time, a)
        else:
            write_prospect_alert(run_id, run_time, a)
    print(f"  Logged {len(new_alerts)} alert(s) to Supabase")

    msg = format_telegram(new_alerts)
    if msg:
        ok = send_telegram(msg)
        print(f"  Telegram: {'sent' if ok else 'FAILED'}")

    try:
        url    = os.getenv('APP_REVALIDATE_URL', '')
        secret = os.getenv('APP_REVALIDATE_SECRET', '')
        if url and secret:
            requests.post(url, headers={'x-revalidate-secret': secret}, timeout=5)
    except Exception:
        pass

    print(f"\nDone. {len(new_alerts)} alert(s) dispatched.")


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='Daily investment pipeline worker')
    parser.add_argument(
        '--mode',
        choices=['fetch', 'assess', 'dispatch'],
        required=True,
        help='fetch → news_pool.json | assess → assessments.json | dispatch → Telegram + Supabase',
    )
    args = parser.parse_args()

    {'fetch': run_fetch, 'assess': run_assess, 'dispatch': run_dispatch}[args.mode]()


if __name__ == '__main__':
    main()
