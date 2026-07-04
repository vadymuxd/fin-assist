#!/usr/bin/env python3
"""
notify_telegram.py

Sends a one-off message to the Fin Assist Telegram bot. Used by Claude Code
to ping Vadym when he's asked to be notified once a task finishes.

Run:
  python3 scripts/notify_telegram.py "Done: synced Monzo transactions."
"""

import os
import sys

import requests
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN   = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')


def send_telegram(text: str) -> None:
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print('Missing TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID in .env', file=sys.stderr)
        sys.exit(1)
    resp = requests.post(
        f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage',
        json={'chat_id': TELEGRAM_CHAT_ID, 'text': text, 'parse_mode': 'HTML'},
        timeout=15,
    )
    resp.raise_for_status()


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('Usage: python3 scripts/notify_telegram.py "<message>"', file=sys.stderr)
        sys.exit(1)
    send_telegram(sys.argv[1])
    print('Sent.')
