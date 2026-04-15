#!/usr/bin/env python3
"""
claude_analyst.py

For each open position in Inv26 - Summary:
  1. Fetch recent news + sentiment + analyst data
     - US/CA tickers: Finnhub primary (news, sentiment, recommendations, price targets)
     - LSE/EU tickers: yfinance (Finnhub free tier has limited non-US coverage)
     - Fallback to yfinance for any Finnhub call that returns empty
  2. Call Claude API once per stock for FAS score (Fundamental + Analyst + Sentiment)
  3. Write results to data/analysis_results.json (consumed by sheets_updater.py + alert_sender.py)

FAS Score 1-10:
  8-10 = Strong buy signal
  6-7  = Bullish / accumulate
  5    = Neutral / hold
  3-4  = Cautious / watch
  1-2  = Sell signal

Run from repo root:
    python3 scripts/claude_analyst.py
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

FINNHUB_KEY = os.getenv('FINNHUB_API_KEY', '')
SHEET_ID = os.getenv('PORTFOLIO_SHEET_ID')
SA_FILE = os.getenv('GOOGLE_APPLICATION_CREDENTIALS', 'config/service_account.json')
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
RESULTS_PATH = 'data/analysis_results.json'
FINNHUB_BASE = 'https://finnhub.io/api/v1'

# Per-ticker routing: (finnhub_symbol, yf_symbol, exchange)
# exchange: 'US'/'CA' → Finnhub primary; 'LSE'/'EU' → yfinance primary
TICKER_CONFIG = {
    'NVDA':   ('NVDA',    'NVDA',       'US'),
    'RTX':    ('RTX',     'RTX',        'US'),
    'GOOG':   ('GOOG',    'GOOG',       'US'),
    'BRK.B':  ('BRK.B',  'BRK-B',      'US'),
    'TECK.B': ('TECK.B', 'TECK-B.TO',  'CA'),
    'RIO':    ('RIO.L',  'RIO.L',      'LSE'),
    'SGLN':   ('SGLN.L', 'SGLN.L',    'LSE'),
    'INRG':   ('INRG.L', 'INRG.L',    'LSE'),
    'IITU':   ('IITU.L', 'IITU.L',    'LSE'),
    'VGER':   ('VGER.L', 'VGER.L',    'LSE'),
    'BA.':    ('BA.L',   'BA.L',       'LSE'),
    'VUSA':   ('VUSA.L', 'VUSA.L',    'LSE'),
    'ISP6':   ('ISP6.L', 'ISP6.L',    'LSE'),
    'LGEN':   ('LGEN.L', 'LGEN.L',    'LSE'),
    'EUE':    ('EUE.L',  'EUE.L',     'LSE'),
    'RHM':    ('RHM.DE', 'RHM.DE',    'EU'),
    'HO':     ('HO.PA',  'HO.PA',     'EU'),
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def parse_float(val):
    """Parse '£1,234.56' / '0.42' / numeric to float. Returns 0.0 on failure."""
    if val is None or val == '':
        return 0.0
    cleaned = str(val).replace('£', '').replace(',', '').replace('%', '').strip()
    try:
        return float(cleaned)
    except (ValueError, TypeError):
        return 0.0


def finnhub_get(endpoint, params):
    """GET from Finnhub. Returns parsed JSON or {} on any error."""
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


# ---------------------------------------------------------------------------
# Data fetching
# ---------------------------------------------------------------------------

def fetch_finnhub_data(symbol):
    """Fetch news, sentiment, analyst recs, and price target from Finnhub."""
    today = datetime.now(timezone.utc)
    date_to = today.strftime('%Y-%m-%d')
    date_from = (today - timedelta(days=7)).strftime('%Y-%m-%d')

    news_raw = finnhub_get('company-news', {'symbol': symbol, 'from': date_from, 'to': date_to})
    headlines = [
        item['headline'] for item in (news_raw or [])[:8]
        if item.get('headline')
    ]

    sentiment = finnhub_get('news-sentiment', {'symbol': symbol})
    rec_raw = finnhub_get('stock/recommendation', {'symbol': symbol})
    price_target = finnhub_get('stock/price-target', {'symbol': symbol})

    return {
        'headlines': headlines,
        'sentiment': sentiment,
        'analyst': rec_raw[0] if rec_raw else {},
        'price_target': price_target,
    }


def fetch_yfinance_data(symbol):
    """Fetch news and analyst info from yfinance. Used for LSE/EU + Finnhub fallback."""
    try:
        t = yf.Ticker(symbol)
        raw_news = t.news or []
        headlines = []
        for item in raw_news[:8]:
            # yfinance >=0.2 nests title under content
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
                'targetMeanPrice':          info.get('targetMeanPrice'),
                'targetHighPrice':          info.get('targetHighPrice'),
                'targetLowPrice':           info.get('targetLowPrice'),
                'recommendationKey':        info.get('recommendationKey'),
                'numberOfAnalystOpinions':  info.get('numberOfAnalystOpinions'),
            }
        except Exception:
            pass

        return {'headlines': headlines, 'analyst_info': analyst_info}
    except Exception as e:
        print(f"    yfinance error ({symbol}): {e}")
        return {'headlines': [], 'analyst_info': {}}


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------

def build_prompt(ticker, name, qty, avg_buy, current_price, data):
    pnl_pct = ((current_price - avg_buy) / avg_buy * 100) if avg_buy else 0
    sign = '+' if pnl_pct >= 0 else ''
    lines = [
        f"Analyse {ticker} ({name}) for a UK retail investor.",
        f"Position: {qty:.4f} shares | Avg buy £{avg_buy:.4f} | Current £{current_price:.4f} | P&L {sign}{pnl_pct:.1f}%",
        "",
    ]

    if data.get('headlines'):
        lines.append("Recent news (last 7 days):")
        for i, h in enumerate(data['headlines'], 1):
            lines.append(f"  {i}. {h}")
        lines.append("")

    # Finnhub sentiment
    s_block = data.get('sentiment', {})
    if s_block and s_block.get('sentiment'):
        s = s_block['sentiment']
        buzz = s_block.get('buzz', {})
        lines.append(
            f"Sentiment: {s.get('bullishPercent', 0)*100:.0f}% bullish, "
            f"{s.get('bearishPercent', 0)*100:.0f}% bearish | "
            f"News score: {s_block.get('companyNewsScore', 'n/a')}"
        )
        if buzz.get('articlesInLastWeek'):
            lines.append(f"Buzz: {buzz['articlesInLastWeek']} articles this week")
        lines.append("")

    # Finnhub analyst consensus
    a = data.get('analyst', {})
    if a and any(a.get(k, 0) for k in ('strongBuy', 'buy', 'hold', 'sell', 'strongSell')):
        total = sum(a.get(k, 0) for k in ('strongBuy', 'buy', 'hold', 'sell', 'strongSell'))
        lines.append(
            f"Analyst consensus ({total}): "
            f"StrongBuy {a.get('strongBuy',0)} Buy {a.get('buy',0)} "
            f"Hold {a.get('hold',0)} Sell {a.get('sell',0)} StrongSell {a.get('strongSell',0)}"
        )
        lines.append("")

    # Finnhub price target
    pt = data.get('price_target', {})
    if pt and pt.get('targetMean'):
        upside = ((pt['targetMean'] - current_price) / current_price * 100) if current_price else 0
        up_sign = '+' if upside >= 0 else ''
        lines.append(
            f"Price target: Mean £{pt['targetMean']:.2f} ({up_sign}{upside:.1f}% upside) | "
            f"High £{pt.get('targetHigh', 'n/a')} | Low £{pt.get('targetLow', 'n/a')}"
        )
        lines.append("")

    # yfinance analyst info (LSE/EU or Finnhub fallback)
    ai = data.get('analyst_info', {})
    if ai and ai.get('targetMeanPrice'):
        upside = ((ai['targetMeanPrice'] - current_price) / current_price * 100) if current_price else 0
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
        "Score: 8-10=strong buy, 6-7=bullish, 5=neutral, 3-4=cautious, 1-2=sell.",
    ]
    return '\n'.join(lines)


# ---------------------------------------------------------------------------
# Claude API
# ---------------------------------------------------------------------------

def call_claude(client, prompt, ticker):
    """Call Claude and parse the JSON FAS score response."""
    try:
        msg = client.messages.create(
            model='claude-haiku-4-5-20251001',
            max_tokens=256,
            messages=[{'role': 'user', 'content': prompt}],
        )
        raw = msg.content[0].text.strip()
        # Strip markdown code fences if Claude wraps response
        if raw.startswith('```'):
            parts = raw.split('```')
            raw = parts[1] if len(parts) > 1 else raw
            if raw.startswith('json'):
                raw = raw[4:].strip()
        return json.loads(raw)
    except json.JSONDecodeError:
        print(f"    JSON parse error for {ticker} — raw: {raw[:120]}")
        return {'score': 5, 'recommendation': 'HOLD', 'confidence': 'LOW', 'reason': 'Parse error'}
    except Exception as e:
        print(f"    Claude API error for {ticker}: {e}")
        return {'score': 5, 'recommendation': 'HOLD', 'confidence': 'LOW', 'reason': f'API error: {e}'}


# ---------------------------------------------------------------------------
# Sheet reader
# ---------------------------------------------------------------------------

def read_positions(sh):
    """Read open positions from Inv26 - Summary. Returns list of position dicts."""
    ws = sh.worksheet('Inv26 - Summary')
    all_rows = ws.get_all_values()
    positions = []
    for row in all_rows:
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
            'platform':      row[2].strip(),
            'qty':           qty,
            'avg_buy':       parse_float(row[4]),
            'current_price': parse_float(row[5]),
        })
    return positions


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("Connecting to Google Sheets...")
    creds = Credentials.from_service_account_file(SA_FILE, scopes=SCOPES)
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(SHEET_ID)
    print(f"  Opened: {sh.title}")

    print("\nReading positions from Inv26 - Summary...")
    positions = read_positions(sh)
    print(f"  {len(positions)} open positions found")
    if not positions:
        print("  Nothing to analyse.")
        return {}

    if not FINNHUB_KEY:
        print("  WARNING: FINNHUB_API_KEY not set — falling back to yfinance for all tickers")

    client = anthropic.Anthropic(api_key=os.getenv('CLAUDE_API_KEY'))
    run_time = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
    results = {}

    for pos in positions:
        ticker = pos['ticker']
        finnhub_sym, yf_sym, exchange = TICKER_CONFIG[ticker]
        print(f"\n  {ticker} ({pos['name']}) [{exchange}]")

        if exchange in ('US', 'CA') and FINNHUB_KEY:
            data = fetch_finnhub_data(finnhub_sym)
            if not data.get('headlines'):
                print(f"    No Finnhub news — supplementing with yfinance")
                yf_data = fetch_yfinance_data(yf_sym)
                data['headlines'] = yf_data.get('headlines', [])
        else:
            data = fetch_yfinance_data(yf_sym)

        prompt = build_prompt(
            ticker, pos['name'], pos['qty'],
            pos['avg_buy'], pos['current_price'], data,
        )

        print(f"    Calling Claude API ({len(data.get('headlines', []))} headlines)...")
        scored = call_claude(client, prompt, ticker)

        results[ticker] = {
            **scored,
            'name':          pos['name'],
            'current_price': pos['current_price'],
            'avg_buy':       pos['avg_buy'],
            'qty':           pos['qty'],
            'run_time':      run_time,
        }
        print(f"    → Score {scored.get('score')}/10 | {scored.get('recommendation')} | {scored.get('confidence')}")
        print(f"      {scored.get('reason', '')}")

    os.makedirs('data', exist_ok=True)
    with open(RESULTS_PATH, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"\nResults saved → {RESULTS_PATH}")
    print("Run sheets_updater.py to write scores to the sheet.")

    return results


def send_bot_reply(results):
    """Send formatted FAS scores to Telegram when triggered via bot command."""
    token   = os.getenv('TELEGRAM_BOT_TOKEN')
    chat_id = os.getenv('TELEGRAM_CHAT_ID')
    if not token or not chat_id:
        print("  Bot reply skipped — Telegram credentials not set")
        return

    now_str = datetime.now(timezone.utc).strftime('%d %b %Y, %H:%M UTC')
    lines   = [f'🔍 <b>ANALYSIS</b> — {now_str}', '']

    sorted_items = sorted(results.items(), key=lambda x: x[1].get('score', 5), reverse=True)
    for ticker, r in sorted_items:
        score = r.get('score', 5)
        rec   = r.get('recommendation', 'HOLD')
        conf  = r.get('confidence', '')
        reason = r.get('reason', '')
        if score >= 8:
            emoji = '🟢'
        elif score >= 6:
            emoji = '📈'
        elif score <= 3:
            emoji = '🔴'
        else:
            emoji = '⚪'
        lines.append(f'{emoji} <b>{ticker}</b>  {score}/10  {rec} ({conf})')
        if reason:
            lines.append(f'   {reason}')

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
