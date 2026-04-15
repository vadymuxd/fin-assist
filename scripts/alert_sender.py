#!/usr/bin/env python3
"""
alert_sender.py

Sends ONE consolidated daily brief to Telegram per run.

Reads:
  data/analysis_results.json  — held positions scored by claude_analyst.py
  data/prospect_results.json  — watchlist scored by prospect_scanner.py

Sections:
  PORTFOLIO  — sell signals only: held positions with score ≤ 3
  TOP PICKS  — buy signals only: prospects with score ≥ 8
  MARKET     — sector pulse: sectors ranked by avg score across all tickers

No individual per-ticker alerts. If nothing is actionable the brief still
sends (close run only, once per 8h dedup) so you always get a daily pulse.

Run from repo root:
    python3 scripts/alert_sender.py
"""

import os
import json
import requests
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN   = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
RESULTS_PATH     = 'data/analysis_results.json'
PROSPECT_PATH    = 'data/prospect_results.json'
DEDUP_PATH       = 'data/brief_dedup.json'
DEDUP_HOURS      = 8      # one brief per 8h max
SELL_THRESHOLD   = 3      # score ≤ this triggers a portfolio sell alert
BUY_THRESHOLD    = 8      # score ≥ this triggers a prospect buy pick

# Sector groupings — used for the Market Pulse section
SECTOR_MAP = {
    'AI & Tech':         ['NVDA', 'GOOG', 'IITU', 'PLTR', 'AMD', 'META', 'MSFT', 'ASML', 'SAP'],
    'Defence':           ['RTX', 'RHM', 'LMT', 'BA.'],
    'Mining & Metals':   ['RIO', 'TECK.B', 'GLEN'],
    'Energy':            ['INRG', 'SHEL'],
    'Gold':              ['SGLN'],
    'Aerospace':         ['AIR'],
    'Pharma':            ['AZN'],
    'Financials':        ['LGEN', 'HO', 'BRK.B'],
    'ETFs & Indices':    ['VGER', 'VUSA', 'ISP6', 'EUE'],
}


# ---------------------------------------------------------------------------
# Telegram
# ---------------------------------------------------------------------------

def send_telegram(text):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("  WARNING: Telegram credentials not set")
        print(f"  Preview:\n{text}")
        return False
    try:
        resp = requests.post(
            f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage',
            json={'chat_id': TELEGRAM_CHAT_ID, 'text': text, 'parse_mode': 'HTML'},
            timeout=10,
        )
        resp.raise_for_status()
        return True
    except Exception as e:
        print(f"  Telegram error: {e}")
        return False


# ---------------------------------------------------------------------------
# Dedup — one brief per DEDUP_HOURS
# ---------------------------------------------------------------------------

def load_dedup():
    if os.path.exists(DEDUP_PATH):
        with open(DEDUP_PATH) as f:
            return json.load(f)
    return {}


def save_dedup(dedup):
    os.makedirs('data', exist_ok=True)
    with open(DEDUP_PATH, 'w') as f:
        json.dump(dedup, f, indent=2)


def is_deduped(dedup):
    last = dedup.get('last_sent')
    if not last:
        return False
    return datetime.now(timezone.utc) - datetime.fromisoformat(last) < timedelta(hours=DEDUP_HOURS)


# ---------------------------------------------------------------------------
# Section builders
# ---------------------------------------------------------------------------

def portfolio_section(results):
    """Sell signals: held positions with score ≤ SELL_THRESHOLD."""
    sell_signals = [
        (ticker, r) for ticker, r in results.items()
        if r.get('score', 5) <= SELL_THRESHOLD
    ]
    sell_signals.sort(key=lambda x: x[1].get('score', 5))

    lines = ['<b>PORTFOLIO</b>']
    if not sell_signals:
        lines.append('✅ No sell signals')
    else:
        for ticker, r in sell_signals:
            score  = r['score']
            rec    = r.get('recommendation', 'SELL')
            conf   = r.get('confidence', '')
            reason = r.get('reason', '')
            price  = r.get('current_price', 0)
            avg    = r.get('avg_buy', 0)
            pnl    = ((price - avg) / avg * 100) if avg else 0
            sign   = '+' if pnl >= 0 else ''
            lines.append(
                f'🔴 <b>{ticker}</b>  {score}/10 {rec} | {conf}\n'
                f'   P&amp;L {sign}{pnl:.1f}% | {reason}'
            )
    return '\n'.join(lines)


def prospects_section(prospect_results):
    """Buy picks: watchlist tickers with score ≥ BUY_THRESHOLD."""
    picks = [
        (ticker, r) for ticker, r in prospect_results.items()
        if r.get('score', 0) >= BUY_THRESHOLD
    ]
    picks.sort(key=lambda x: x[1].get('score', 0), reverse=True)

    lines = ['<b>TOP PICKS</b>']
    if not picks:
        lines.append('— Nothing above buy threshold today')
    else:
        for ticker, r in picks:
            score  = r['score']
            rec    = r.get('recommendation', 'BUY')
            conf   = r.get('confidence', '')
            reason = r.get('reason', '')
            notes  = r.get('notes', '')
            header = f'🟢 <b>{ticker}</b>  {score}/10 {rec} | {conf}'
            if notes:
                header += f' — {notes}'
            lines.append(f'{header}\n   {reason}')
    return '\n'.join(lines)


def market_pulse_section(results, prospect_results):
    """Sector ranking by avg score across all scored tickers."""
    all_scores = {**{t: r.get('score', 5) for t, r in results.items()},
                  **{t: r.get('score', 5) for t, r in prospect_results.items()}}

    sector_scores = {}
    for sector, tickers in SECTOR_MAP.items():
        scores = [all_scores[t] for t in tickers if t in all_scores]
        if scores:
            sector_scores[sector] = sum(scores) / len(scores)

    if not sector_scores:
        return ''

    ranked = sorted(sector_scores.items(), key=lambda x: x[1], reverse=True)

    lines = ['<b>MARKET PULSE</b>']
    for sector, avg in ranked:
        if avg >= 7.5:
            icon = '🔥'
        elif avg >= 6.5:
            icon = '📈'
        elif avg >= 5.5:
            icon = '➡️'
        else:
            icon = '📉'
        lines.append(f'{icon} {sector:<22} {avg:.1f}/10')
    return '\n'.join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    results          = {}
    prospect_results = {}

    if os.path.exists(RESULTS_PATH):
        with open(RESULTS_PATH) as f:
            results = json.load(f)
    else:
        print(f"No results file at {RESULTS_PATH} — run claude_analyst.py first")

    if os.path.exists(PROSPECT_PATH):
        with open(PROSPECT_PATH) as f:
            prospect_results = json.load(f)

    dedup = load_dedup()
    if is_deduped(dedup):
        print(f"Brief already sent within {DEDUP_HOURS}h — skipping")
        return

    now_str = datetime.now(timezone.utc).strftime('%d %b %Y, %H:%M UTC')

    sections = [
        f'📊 <b>DAILY BRIEF</b> — {now_str}',
        '',
        portfolio_section(results),
        '',
        prospects_section(prospect_results),
        '',
        market_pulse_section(results, prospect_results),
    ]
    message = '\n'.join(sections).strip()

    print(f"Sending daily brief ({len(message)} chars)...")
    if send_telegram(message):
        dedup['last_sent'] = datetime.now(timezone.utc).isoformat()
        save_dedup(dedup)
        print("  Sent.")
    else:
        print("  Failed to send.")


if __name__ == '__main__':
    main()
