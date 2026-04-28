#!/usr/bin/env python3
"""
alert_dispatcher.py  —  Script C of the daily 3-step pipeline.

Reads data/assessments.json (written by stock_assessor.py).
Deduplicates by ticker: if this ticker had any alert/discovery logged
in the last 48 hours it is suppressed — regardless of content.
Logs new signals to Supabase (holdings_alerts / discoveries).
Sends a Telegram message for all newly logged signals.
Appends to the Google Sheets Alerts Log tab.

Run:
  python3 scripts/alert_dispatcher.py
"""

import os
import json
import requests
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from dotenv import load_dotenv
import gspread
from google.oauth2.service_account import Credentials

from lib.supabase_sink import (
    get_recently_alerted_tickers,
    write_holding_alert,
    write_prospect_alert,
)

load_dotenv()

ASSESSMENTS_PATH = 'data/assessments.json'
SHEET_ID   = os.getenv('PORTFOLIO_SHEET_ID')
SA_FILE    = os.getenv('GOOGLE_APPLICATION_CREDENTIALS', 'config/service_account.json')
SCOPES     = ['https://www.googleapis.com/auth/spreadsheets']
LONDON_TZ  = ZoneInfo('Europe/London')
DEDUP_HOURS = 48

ALERTS_LOG_TAB     = 'Alerts Log'
ALERTS_LOG_HEADERS = [
    'Date (Europe/London)', 'Ticker', 'Type', 'Action', 'Score', 'Event', 'Run Time (UTC)',
]


def escape_html(text):
    return str(text).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


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


def format_telegram(new_alerts):
    now_str = datetime.now(timezone.utc).strftime('%d %b %Y, %H:%M UTC')
    lines   = []

    holdings = [a for a in new_alerts if a['type'] == 'holding']
    prospects = [a for a in new_alerts if a['type'] == 'prospect']

    if holdings:
        lines += [f'⚠️ <b>HOLDINGS ALERT</b> — {now_str}', '']
        for a in holdings:
            action = a['action']
            emoji  = '🔴' if action in ('SELL', 'EXIT', 'TRIM') else '🟢'
            lines.append(f'{emoji} <b>{escape_html(a["ticker"])}</b> — {escape_html(a.get("event") or "event detected")}')
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


def get_or_create_alerts_log(sh):
    try:
        ws = sh.worksheet(ALERTS_LOG_TAB)
    except gspread.exceptions.WorksheetNotFound:
        ws = sh.add_worksheet(title=ALERTS_LOG_TAB, rows=1000, cols=len(ALERTS_LOG_HEADERS))
        ws.update(values=[ALERTS_LOG_HEADERS], range_name='A1')
        return ws
    first_row = ws.row_values(1)
    if first_row[:len(ALERTS_LOG_HEADERS)] != ALERTS_LOG_HEADERS:
        ws.clear()
        ws.update(values=[ALERTS_LOG_HEADERS], range_name='A1')
    return ws


def main():
    print("=== Script C: Alert Dispatcher ===")

    if not os.path.exists(ASSESSMENTS_PATH):
        print(f"  {ASSESSMENTS_PATH} not found — nothing to dispatch")
        return

    with open(ASSESSMENTS_PATH) as f:
        assessments = json.load(f)

    if not assessments:
        print("  No actionable assessments this run — done")
        return

    print(f"  {len(assessments)} assessment(s) to process")

    # ── Dedup: skip tickers alerted in last 48h ───────────────────────────────
    already_alerted = get_recently_alerted_tickers(hours=DEDUP_HOURS)
    print(f"  Tickers alerted in last {DEDUP_HOURS}h: {sorted(already_alerted) or 'none'}")

    new_alerts  = []
    suppressed  = []
    for a in assessments:
        if a['ticker'] in already_alerted:
            suppressed.append(a)
            print(f"  [dedup] {a['ticker']} ({a['type']}) — suppressed (alerted within {DEDUP_HOURS}h)")
        else:
            new_alerts.append(a)

    if not new_alerts:
        print(f"\n  All {len(assessments)} assessment(s) suppressed by dedup — no Telegram messages sent")
        return

    print(f"\n  {len(new_alerts)} new signal(s), {len(suppressed)} suppressed")

    # ── Log to Supabase ───────────────────────────────────────────────────────
    run_id   = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
    run_time = datetime.now(timezone.utc).isoformat()

    for a in new_alerts:
        if a['type'] == 'holding':
            write_holding_alert(run_id, run_time, a)
        else:
            write_prospect_alert(run_id, run_time, a)

    print(f"  Logged {len(new_alerts)} alert(s) to Supabase")

    # ── Send Telegram ─────────────────────────────────────────────────────────
    msg = format_telegram(new_alerts)
    if msg:
        ok = send_telegram(msg)
        print(f"  Telegram: {'sent' if ok else 'FAILED'}")

    # ── Append to Google Sheets Alerts Log ────────────────────────────────────
    try:
        creds    = Credentials.from_service_account_file(SA_FILE, scopes=SCOPES)
        gc       = gspread.authorize(creds)
        sh       = gc.open_by_key(SHEET_ID)
        log_ws   = get_or_create_alerts_log(sh)
        day      = datetime.now(LONDON_TZ).strftime('%Y-%m-%d')
        run_str  = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
        rows = [
            [day, a['ticker'], a['type'], a['action'], a['score'], a.get('event', ''), run_str]
            for a in new_alerts
        ]
        log_ws.append_rows(rows, value_input_option='USER_ENTERED')
        print(f"  Appended {len(rows)} row(s) to Alerts Log")
    except Exception as e:
        print(f"  Sheets log failed (non-critical): {e}")

    # ── Revalidate frontend ───────────────────────────────────────────────────
    try:
        url    = os.getenv('APP_REVALIDATE_URL', '')
        secret = os.getenv('APP_REVALIDATE_SECRET', '')
        if url and secret:
            requests.post(url, headers={'x-revalidate-secret': secret}, timeout=5)
    except Exception:
        pass

    print(f"\nDone. {len(new_alerts)} alert(s) dispatched.")


if __name__ == '__main__':
    main()
