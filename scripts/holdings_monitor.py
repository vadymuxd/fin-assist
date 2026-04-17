#!/usr/bin/env python3
"""
holdings_monitor.py

Event-driven monitor for held positions. Scans last 24h news per holding and
asks Claude whether a concrete event warrants action (earnings miss, regulatory
issue, leadership change, sector-wide risk, macro impact).

Modes:
  --auto  (cron)    silent unless ≥1 holding has an ALERT-level event
  --bot   (Telegram) always replies with full holdings status table

Data sources:
  US/CA tickers: Finnhub company-news + sentiment + analyst
  LSE/EU tickers: yfinance news + analyst info (Finnhub free tier is thin outside US)

Outputs:
  data/holdings_alerts.json   — structured results for this run
  Telegram message (if --auto and alerts present, or if --bot)

Run:
  python3 scripts/holdings_monitor.py --auto
  python3 scripts/holdings_monitor.py --bot
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

from lib.market_sources import fetch_ticker_context, fetch_yfinance_context

load_dotenv()

SHEET_ID = os.getenv('PORTFOLIO_SHEET_ID')
SA_FILE  = os.getenv('GOOGLE_APPLICATION_CREDENTIALS', 'config/service_account.json')
SCOPES   = ['https://www.googleapis.com/auth/spreadsheets']
RESULTS_PATH = 'data/holdings_alerts.json'

TELEGRAM_TOKEN   = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

# Per-ticker routing mirrors claude_analyst.py
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
            'platform':      row[2].strip(),
            'qty':           qty,
            'avg_buy':       parse_float(row[4]),
            'current_price': parse_float(row[5]),
        })
    return positions


# ---------------------------------------------------------------------------
# Claude event analysis
# ---------------------------------------------------------------------------

def build_prompt(ticker, name, qty, avg_buy, current_price, data):
    pnl_pct = ((current_price - avg_buy) / avg_buy * 100) if avg_buy else 0
    sign    = '+' if pnl_pct >= 0 else ''

    lines = [
        f"You are reviewing {ticker} ({name}) for a UK retail investor who currently HOLDS this position.",
        f"Position: {qty:.4f} shares | Avg buy £{avg_buy:.4f} | Current £{current_price:.4f} | P&L {sign}{pnl_pct:.1f}%",
        "",
        "Task: identify if any CONCRETE EVENT in the last 24h should make the holder act.",
        "Examples of concrete events: earnings miss/beat, guidance cut, regulatory action, lawsuit, ",
        "management change, M&A, credit rating change, major contract win/loss, sector shock.",
        "NOT concrete: general bearishness, daily price wiggle, analyst rating change alone, macro mood.",
        "",
    ]

    headlines = data.get('headlines') or []
    if headlines:
        lines.append("Last 24h news:")
        for i, h in enumerate(headlines, 1):
            title = h.get('headline') if isinstance(h, dict) else h
            lines.append(f"  {i}. {title}")
        lines.append("")
    else:
        lines.append("Last 24h news: (none found)")
        lines.append("")

    s_block = data.get('sentiment', {})
    if s_block and s_block.get('sentiment'):
        s = s_block['sentiment']
        lines.append(
            f"Sentiment: {s.get('bullishPercent', 0)*100:.0f}% bullish, "
            f"{s.get('bearishPercent', 0)*100:.0f}% bearish"
        )

    a = data.get('analyst') or {}
    if a and any(a.get(k, 0) for k in ('strongBuy', 'buy', 'hold', 'sell', 'strongSell')):
        lines.append(
            f"Analysts: StrongBuy {a.get('strongBuy',0)} Buy {a.get('buy',0)} "
            f"Hold {a.get('hold',0)} Sell {a.get('sell',0)} StrongSell {a.get('strongSell',0)}"
        )

    ai = data.get('analyst_info') or {}
    if ai and ai.get('targetMeanPrice'):
        lines.append(
            f"Analyst target: £{ai['targetMeanPrice']:.2f} | Rec: {ai.get('recommendationKey', 'n/a')}"
        )

    lines += [
        "",
        "Return ONLY a JSON object (no markdown, no prose):",
        '{',
        '  "alert_level": "<NONE|WATCH|ACT>",',
        '  "score": <integer 1-10>,',
        '  "event": "<short phrase describing the specific event, or empty string if none>",',
        '  "rationale": "<1-2 sentences: what happened and why it matters for this holder>",',
        '  "suggested_action": "<HOLD|REVIEW|TRIM|EXIT>"',
        '}',
        "",
        "alert_level rules:",
        "  NONE  = nothing concrete, business as usual — keep holding",
        "  WATCH = something worth noting, not urgent (mild guidance shift, sector chop, soft data)",
        "  ACT   = concrete bad event OR concrete good event reversing prior thesis — user should read this",
        "",
        "Be strict with ACT. Only escalate if a real, specific event happened. Score 1-10 is context:",
        "  8-10=strong keep/add, 6-7=comfortable hold, 5=neutral, 3-4=concerns building, 1-2=exit-worthy.",
    ]
    return '\n'.join(lines)


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
            raw = parts[1] if len(parts) > 1 else raw
            if raw.startswith('json'):
                raw = raw[4:].strip()
        return json.loads(raw)
    except json.JSONDecodeError:
        return {'alert_level': 'NONE', 'score': 5, 'event': '', 'rationale': 'Parse error', 'suggested_action': 'HOLD'}
    except Exception as e:
        print(f"    Claude API error for {ticker}: {e}")
        return {'alert_level': 'NONE', 'score': 5, 'event': '', 'rationale': f'API error: {e}', 'suggested_action': 'HOLD'}


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


def format_alert_message(alerts):
    """Concise alert message — only the holdings with ACT-level events."""
    now_str = datetime.now(timezone.utc).strftime('%d %b %Y, %H:%M UTC')
    lines = [f'⚠️ <b>HOLDINGS ALERT</b> — {now_str}', '']
    for r in alerts:
        emoji = '🔴' if r['suggested_action'] in ('TRIM', 'EXIT') else '🟡'
        lines.append(f'{emoji} <b>{escape_html(r["ticker"])}</b> — {escape_html(r["event"] or "event detected")}')
        lines.append(f'   Action: <b>{escape_html(r["suggested_action"])}</b> | Score {r["score"]}/10')
        lines.append(f'   {escape_html(r["rationale"])}')
        lines.append('')
    return '\n'.join(lines).strip()


def format_full_status(results):
    """Full reply for /holdings bot command — every position with a 1-line verdict."""
    now_str = datetime.now(timezone.utc).strftime('%d %b %Y, %H:%M UTC')
    lines = [f'📊 <b>HOLDINGS STATUS</b> — {now_str}', '']

    order = {'ACT': 0, 'WATCH': 1, 'NONE': 2}
    sorted_items = sorted(results, key=lambda r: (order.get(r.get('alert_level', 'NONE'), 2), -r.get('score', 5)))

    any_act = False
    for r in sorted_items:
        level = r.get('alert_level', 'NONE')
        emoji = {'ACT': '🔴', 'WATCH': '🟡', 'NONE': '⚪'}.get(level, '⚪')
        head = f'{emoji} <b>{escape_html(r["ticker"])}</b> {r["score"]}/10 — {escape_html(r["suggested_action"])}'
        if r.get('event'):
            head += f' | {escape_html(r["event"])}'
        lines.append(head)
        if level in ('ACT', 'WATCH') and r.get('rationale'):
            lines.append(f'   {escape_html(r["rationale"])}')
            any_act = True

    if not any_act:
        lines.append('')
        lines.append('✅ No concerning events in the last 24h — all holdings quiet.')
    return '\n'.join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(mode):
    is_bot = (mode == 'bot')

    print("Connecting to Google Sheets...")
    creds = Credentials.from_service_account_file(SA_FILE, scopes=SCOPES)
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(SHEET_ID)
    print(f"  Opened: {sh.title}")

    print("\nReading holdings from Inv26 - Summary...")
    positions = read_positions(sh)
    print(f"  {len(positions)} open positions")
    if not positions:
        if is_bot:
            send_telegram('📊 <b>HOLDINGS STATUS</b>\n\nNo open positions found.')
        return

    client = anthropic.Anthropic(api_key=os.getenv('CLAUDE_API_KEY'))
    run_time = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
    results = []

    for pos in positions:
        ticker = pos['ticker']
        finnhub_sym, yf_sym, exchange = TICKER_CONFIG[ticker]
        print(f"\n  {ticker} [{exchange}]")

        if exchange in ('US', 'CA'):
            data = fetch_ticker_context(finnhub_sym, hours=24)
            if not data.get('headlines'):
                print(f"    No Finnhub news — checking yfinance")
                yf_data = fetch_yfinance_context(yf_sym)
                data['headlines']    = yf_data.get('headlines', [])
                data['analyst_info'] = yf_data.get('analyst_info', {})
        else:
            yf_data = fetch_yfinance_context(yf_sym)
            data = {
                'headlines':    yf_data.get('headlines', []),
                'sentiment':    {},
                'analyst':      {},
                'analyst_info': yf_data.get('analyst_info', {}),
            }

        prompt = build_prompt(ticker, pos['name'], pos['qty'], pos['avg_buy'], pos['current_price'], data)
        print(f"    Claude ({len(data.get('headlines', []))} headlines)...")
        scored = call_claude(client, prompt, ticker)

        results.append({
            'ticker':           ticker,
            'name':             pos['name'],
            'current_price':    pos['current_price'],
            'avg_buy':          pos['avg_buy'],
            'qty':              pos['qty'],
            'alert_level':      scored.get('alert_level', 'NONE'),
            'score':            scored.get('score', 5),
            'event':            scored.get('event', ''),
            'rationale':        scored.get('rationale', ''),
            'suggested_action': scored.get('suggested_action', 'HOLD'),
            'run_time':         run_time,
        })
        print(f"    → {scored.get('alert_level')} | {scored.get('suggested_action')} | {scored.get('event') or '(no event)'}")

    os.makedirs('data', exist_ok=True)
    with open(RESULTS_PATH, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"\nResults saved → {RESULTS_PATH}")

    # Compatibility: sheets_updater.py reads data/analysis_results.json to write
    # Score/Recommendation/Last Updated columns. Map alert_level → recommendation.
    legacy = {}
    for r in results:
        level = r['alert_level']
        rec_map = {
            ('ACT', 'EXIT'):   'SELL',
            ('ACT', 'TRIM'):   'SELL',
            ('ACT', 'REVIEW'): 'WATCH',
            ('WATCH', 'REVIEW'): 'WATCH',
        }
        rec = rec_map.get((level, r['suggested_action']), 'HOLD')
        conf = 'HIGH' if level == 'ACT' else 'MEDIUM' if level == 'WATCH' else 'LOW'
        legacy[r['ticker']] = {
            'score':          r['score'],
            'recommendation': rec,
            'confidence':     conf,
            'reason':         r['rationale'] or r['event'] or 'No event',
            'name':           r['name'],
            'current_price':  r['current_price'],
            'avg_buy':        r['avg_buy'],
            'qty':            r['qty'],
            'run_time':       r['run_time'],
        }
    with open('data/analysis_results.json', 'w') as f:
        json.dump(legacy, f, indent=2)

    alerts = [r for r in results if r['alert_level'] == 'ACT']

    if is_bot:
        send_telegram(format_full_status(results))
        print(f"\n[bot] Full status sent. {len(alerts)} ACT-level event(s).")
    else:
        if alerts:
            send_telegram(format_alert_message(alerts))
            print(f"\n[auto] {len(alerts)} alert(s) sent.")
        else:
            print("\n[auto] No ACT-level events — staying silent.")


if __name__ == '__main__':
    mode = 'auto'
    if '--bot' in sys.argv:
        mode = 'bot'
    elif '--auto' in sys.argv:
        mode = 'auto'
    main(mode)
