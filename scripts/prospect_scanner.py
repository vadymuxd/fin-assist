#!/usr/bin/env python3
"""
prospect_scanner.py

Scores watchlist tickers (prospects / candidates to buy) using the same
FAS (Fundamental + Analyst + Sentiment) approach as claude_analyst.py,
but adapted for tickers not currently held.

Workflow:
  1. Read watchlist from the 'Watchlist' sheet tab
     Columns: A=Ticker, B=YF Symbol, C=Exchange (US/CA/LSE/EU), D=Notes
  2. For each ticker: fetch news + analyst data (Finnhub primary for US/CA,
     yfinance for LSE/EU, yfinance fallback on empty Finnhub response)
  3. Call Claude API once per ticker for FAS score
  4. Save results to data/prospect_results.json

Alerting is handled by alert_sender.py — this script only scores and saves.

Run from repo root:
    python3 scripts/prospect_scanner.py
"""

import os
import json
import requests
import yfinance as yf
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
import gspread
from google.oauth2.service_account import Credentials
import anthropic

load_dotenv()

FINNHUB_KEY  = os.getenv('FINNHUB_API_KEY', '')
SHEET_ID     = os.getenv('PORTFOLIO_SHEET_ID')
SA_FILE      = os.getenv('GOOGLE_APPLICATION_CREDENTIALS', 'config/service_account.json')
SCOPES       = ['https://www.googleapis.com/auth/spreadsheets']
RESULTS_PATH = 'data/prospect_results.json'
FINNHUB_BASE = 'https://finnhub.io/api/v1'


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def parse_float(val):
    if val is None or val == '':
        return 0.0
    cleaned = str(val).replace('£', '').replace(',', '').replace('%', '').strip()
    try:
        return float(cleaned)
    except (ValueError, TypeError):
        return 0.0


def infer_exchange(ticker, yf_symbol):
    """
    Infer exchange from ticker/yf_symbol suffix if not explicitly provided.
    Returned values match TICKER_CONFIG convention: 'US', 'CA', 'LSE', 'EU'.
    """
    sym = (yf_symbol or ticker).upper()
    if sym.endswith('.L'):
        return 'LSE'
    if sym.endswith('.TO') or sym.endswith('.V'):
        return 'CA'
    if '.' in sym:
        # .DE, .PA, .AS, .MI, .MC, etc.
        return 'EU'
    return 'US'


# ---------------------------------------------------------------------------
# Finnhub
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


def fetch_finnhub_data(symbol):
    today     = datetime.now(timezone.utc)
    date_to   = today.strftime('%Y-%m-%d')
    date_from = (today - timedelta(days=7)).strftime('%Y-%m-%d')

    news_raw = finnhub_get('company-news', {'symbol': symbol, 'from': date_from, 'to': date_to})
    headlines = [
        item['headline'] for item in (news_raw or [])[:8]
        if item.get('headline')
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


# ---------------------------------------------------------------------------
# yfinance
# ---------------------------------------------------------------------------

def fetch_yfinance_data(symbol):
    try:
        t        = yf.Ticker(symbol)
        raw_news = t.news or []
        headlines = []
        for item in raw_news[:8]:
            title = (
                item.get('content', {}).get('title')
                or item.get('title')
                or ''
            )
            if title:
                headlines.append(title)

        analyst_info = {}
        try:
            info = t.info
            analyst_info = {
                'targetMeanPrice':         info.get('targetMeanPrice'),
                'targetHighPrice':         info.get('targetHighPrice'),
                'targetLowPrice':          info.get('targetLowPrice'),
                'recommendationKey':       info.get('recommendationKey'),
                'numberOfAnalystOpinions': info.get('numberOfAnalystOpinions'),
                'currentPrice':            info.get('currentPrice') or info.get('regularMarketPrice'),
                'currency':                info.get('currency', 'GBP'),
            }
        except Exception:
            pass

        return {'headlines': headlines, 'analyst_info': analyst_info}
    except Exception as e:
        print(f"    yfinance error ({symbol}): {e}")
        return {'headlines': [], 'analyst_info': {}}


# ---------------------------------------------------------------------------
# Prompt builder (prospect variant — no held position)
# ---------------------------------------------------------------------------

def build_prompt(ticker, notes, current_price, data):
    lines = [
        f"Evaluate {ticker} as a potential buy for a UK retail investor.",
    ]
    if notes:
        lines.append(f"Context: {notes}")
    if current_price:
        lines.append(f"Current price: £{current_price:.4f}")
    lines.append("")

    if data.get('headlines'):
        lines.append("Recent news (last 7 days):")
        for i, h in enumerate(data['headlines'], 1):
            lines.append(f"  {i}. {h}")
        lines.append("")

    s_block = data.get('sentiment', {})
    if s_block and s_block.get('sentiment'):
        s    = s_block['sentiment']
        buzz = s_block.get('buzz', {})
        lines.append(
            f"Sentiment: {s.get('bullishPercent', 0)*100:.0f}% bullish, "
            f"{s.get('bearishPercent', 0)*100:.0f}% bearish | "
            f"News score: {s_block.get('companyNewsScore', 'n/a')}"
        )
        if buzz.get('articlesInLastWeek'):
            lines.append(f"Buzz: {buzz['articlesInLastWeek']} articles this week")
        lines.append("")

    a = data.get('analyst', {})
    if a and any(a.get(k, 0) for k in ('strongBuy', 'buy', 'hold', 'sell', 'strongSell')):
        total = sum(a.get(k, 0) for k in ('strongBuy', 'buy', 'hold', 'sell', 'strongSell'))
        lines.append(
            f"Analyst consensus ({total}): "
            f"StrongBuy {a.get('strongBuy',0)} Buy {a.get('buy',0)} "
            f"Hold {a.get('hold',0)} Sell {a.get('sell',0)} StrongSell {a.get('strongSell',0)}"
        )
        lines.append("")

    pt = data.get('price_target', {})
    if pt and pt.get('targetMean') and current_price:
        upside   = (pt['targetMean'] - current_price) / current_price * 100
        up_sign  = '+' if upside >= 0 else ''
        lines.append(
            f"Price target: Mean £{pt['targetMean']:.2f} ({up_sign}{upside:.1f}% upside) | "
            f"High £{pt.get('targetHigh', 'n/a')} | Low £{pt.get('targetLow', 'n/a')}"
        )
        lines.append("")

    ai = data.get('analyst_info', {})
    if ai and ai.get('targetMeanPrice'):
        upside  = ((ai['targetMeanPrice'] - current_price) / current_price * 100) if current_price else 0
        up_sign = '+' if upside >= 0 else ''
        lines.append(
            f"Analyst target: £{ai['targetMeanPrice']:.2f} ({up_sign}{upside:.1f}%) | "
            f"Rec: {ai.get('recommendationKey', 'n/a')} | "
            f"Analysts: {ai.get('numberOfAnalystOpinions', 'n/a')}"
        )
        lines.append("")

    lines += [
        "Return ONLY a JSON object (no markdown, no extra text):",
        '{',
        '  "score": <integer 1-10>,',
        '  "recommendation": "<BUY|HOLD|SELL|WATCH>",',
        '  "confidence": "<HIGH|MEDIUM|LOW>",',
        '  "reason": "<1-2 sentence explanation>"',
        '}',
        "",
        "Score: 8-10=strong buy, 6-7=bullish/worth watching, 5=neutral, 3-4=cautious, 1-2=avoid.",
    ]
    return '\n'.join(lines)


# ---------------------------------------------------------------------------
# Claude API
# ---------------------------------------------------------------------------

def call_claude(client, prompt, ticker):
    try:
        msg = client.messages.create(
            model='claude-haiku-4-5-20251001',
            max_tokens=256,
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
        print(f"    JSON parse error for {ticker} — raw: {raw[:120]}")
        return {'score': 5, 'recommendation': 'WATCH', 'confidence': 'LOW', 'reason': 'Parse error'}
    except Exception as e:
        print(f"    Claude API error for {ticker}: {e}")
        return {'score': 5, 'recommendation': 'WATCH', 'confidence': 'LOW', 'reason': f'API error: {e}'}


# ---------------------------------------------------------------------------
# Sheet reader
# ---------------------------------------------------------------------------

def read_watchlist(sh):
    """
    Read watchlist from 'Watchlist' tab.
    Expected columns: A=Ticker, B=YF Symbol, C=Exchange, D=Notes
    Returns list of dicts. Returns [] if tab is missing or empty.
    """
    try:
        ws = sh.worksheet('Watchlist')
    except gspread.exceptions.WorksheetNotFound:
        print("  'Watchlist' tab not found — create it with columns: Ticker | YF Symbol | Exchange | Notes")
        return []

    rows = ws.get_all_values()
    if not rows:
        print("  'Watchlist' tab is empty — add tickers to scan")
        return []

    # Skip header row if present (detect by checking if col A is 'Ticker' or 'ticker')
    start = 1 if rows[0][0].strip().lower() in ('ticker', 'symbol') else 0
    watchlist = []
    for row in rows[start:]:
        if not row or not row[0].strip():
            continue
        ticker    = row[0].strip().upper()
        yf_sym    = row[1].strip() if len(row) > 1 and row[1].strip() else ticker
        exchange  = row[2].strip().upper() if len(row) > 2 and row[2].strip() else ''
        notes     = row[3].strip() if len(row) > 3 else ''

        if not exchange:
            exchange = infer_exchange(ticker, yf_sym)

        watchlist.append({
            'ticker':   ticker,
            'yf_sym':   yf_sym,
            'exchange': exchange,
            'notes':    notes,
        })

    return watchlist


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("Connecting to Google Sheets...")
    creds = Credentials.from_service_account_file(SA_FILE, scopes=SCOPES)
    gc    = gspread.authorize(creds)
    sh    = gc.open_by_key(SHEET_ID)
    print(f"  Opened: {sh.title}")

    print("\nReading watchlist...")
    watchlist = read_watchlist(sh)
    if not watchlist:
        print("Nothing to scan.")
        return {}

    print(f"  {len(watchlist)} ticker(s) on watchlist")

    if not FINNHUB_KEY:
        print("  WARNING: FINNHUB_API_KEY not set — falling back to yfinance for all tickers")

    client   = anthropic.Anthropic(api_key=os.getenv('CLAUDE_API_KEY'))
    run_time = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
    results  = {}

    for item in watchlist:
        ticker   = item['ticker']
        yf_sym   = item['yf_sym']
        exchange = item['exchange']
        notes    = item['notes']
        print(f"\n  {ticker} [{exchange}]" + (f" — {notes}" if notes else ""))

        # Fetch data
        if exchange in ('US', 'CA') and FINNHUB_KEY:
            data = fetch_finnhub_data(ticker)
            if not data.get('headlines'):
                print(f"    No Finnhub news — supplementing with yfinance")
                yf_data = fetch_yfinance_data(yf_sym)
                data['headlines']    = yf_data.get('headlines', [])
                data['analyst_info'] = yf_data.get('analyst_info', {})
        else:
            data = fetch_yfinance_data(yf_sym)

        # Try to get current price from yfinance (informational only)
        current_price = data.get('analyst_info', {}).get('currentPrice') or 0.0
        if not current_price:
            try:
                hist = yf.Ticker(yf_sym).history(period='1d')
                if not hist.empty:
                    current_price = float(hist['Close'].iloc[-1])
            except Exception:
                pass

        # Score with Claude
        prompt = build_prompt(ticker, notes, current_price, data)
        print(f"    Calling Claude API ({len(data.get('headlines', []))} headlines)...")
        scored = call_claude(client, prompt, ticker)

        results[ticker] = {
            **scored,
            'ticker':        ticker,
            'notes':         notes,
            'current_price': current_price,
            'run_time':      run_time,
        }

        score = scored.get('score', 5)
        print(f"    → Score {score}/10 | {scored.get('recommendation')} | {scored.get('confidence')}")
        print(f"      {scored.get('reason', '')}")

    os.makedirs('data', exist_ok=True)
    with open(RESULTS_PATH, 'w') as f:
        json.dump(results, f, indent=2)

    print(f"\nResults saved → {RESULTS_PATH}")
    print("Run alert_sender.py to send the daily brief.")
    return results


def send_bot_reply(results):
    """Send formatted prospect scores to Telegram when triggered via bot command."""
    token   = os.getenv('TELEGRAM_BOT_TOKEN')
    chat_id = os.getenv('TELEGRAM_CHAT_ID')
    if not token or not chat_id:
        print("  Bot reply skipped — Telegram credentials not set")
        return

    now_str = datetime.now(timezone.utc).strftime('%d %b %Y, %H:%M UTC')
    lines   = [f'🔭 <b>PROSPECT SCAN</b> — {now_str}', '']

    sorted_items = sorted(results.items(), key=lambda x: x[1].get('score', 5), reverse=True)
    for ticker, r in sorted_items:
        score  = r.get('score', 5)
        rec    = r.get('recommendation', 'WATCH')
        conf   = r.get('confidence', '')
        reason = r.get('reason', '')
        notes  = r.get('notes', '')
        if score >= 8:
            emoji = '🟢'
        elif score >= 6:
            emoji = '🟡'
        elif score <= 3:
            emoji = '🔴'
        else:
            emoji = '⚪'
        header = f'{emoji} <b>{ticker}</b>  {score}/10  {rec} ({conf})'
        if notes:
            header += f' — {notes}'
        lines.append(header)
        if reason:
            lines.append(f'   {reason}')

    if not sorted_items:
        lines.append('— Watchlist is empty')

    message = '\n'.join(lines)
    try:
        resp = requests.post(
            f'https://api.telegram.org/bot{token}/sendMessage',
            json={'chat_id': chat_id, 'text': message, 'parse_mode': 'HTML'},
            timeout=10,
        )
        resp.raise_for_status()
        print("  Bot reply sent.")
    except Exception as e:
        print(f"  Bot reply failed: {e}")


if __name__ == '__main__':
    import sys
    results = main()
    if '--bot' in sys.argv and results:
        send_bot_reply(results)
