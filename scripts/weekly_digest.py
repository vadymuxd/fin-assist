#!/usr/bin/env python3
"""
weekly_digest.py

Monday 08:00 BST Telegram digest. Summarises:
  1. Portfolio total + WoW change + vs Apr-13 baseline
  2. 7-day benchmark returns with beat/miss markers
  3. Holdings grouped into 🚀 BUY MORE / ⚠️ CONSIDER SELL / 👀 WATCH
  4. Sector context: allocation % + 7-day sector-ETF return
  5. Discovery top 3 from latest prospect run
  6. LLM-generated recommendation paragraph

Depends on fresh files produced earlier in the workflow:
  data/holdings_alerts.json   (from holdings_monitor.py --auto)
  data/prospect_results.json  (from prospect_discovery.py --auto)

Run from repo root:
    python3 scripts/weekly_digest.py
"""

import os
import json
import requests
import anthropic
import yfinance as yf
from datetime import datetime, timezone
from dotenv import load_dotenv
import gspread
from google.oauth2.service_account import Credentials

load_dotenv()

SHEET_ID = os.getenv('PORTFOLIO_SHEET_ID')
SA_FILE  = os.getenv('GOOGLE_APPLICATION_CREDENTIALS', 'config/service_account.json')
SCOPES   = ['https://www.googleapis.com/auth/spreadsheets']

HOLDINGS_PATH = 'data/holdings_alerts.json'
PROSPECT_PATH = 'data/prospect_results.json'

TELEGRAM_TOKEN   = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
CLAUDE_API_KEY   = os.getenv('CLAUDE_API_KEY')

# Inv26 - Summary rows (1-based)
ROW_GRAND_TOTAL   = 7
ROW_CASH          = 9
ROW_STOCKS_TOTAL  = 11
ROW_MANAGED_TOTAL = 28
COL_VALUE_IDX     = 6   # 0-based = col G

# Inv26 - Trend baseline row (April 2026)
TREND_BASELINE_ROW = 17
TREND_TOTAL_COL    = 4   # 0-based = col E (Total)

# yfinance symbols for benchmarks
BENCHMARKS = [
    ('S&P 500',    '^GSPC'),
    ('FTSE 100',   '^FTSE'),
    ('NASDAQ 100', '^NDX'),
    ('MSCI World', 'URTH'),
    ('Gold',       'SGLN.L'),
]

# Per-ticker yfinance symbol + sector (mirrors holdings_monitor.py TICKER_CONFIG)
TICKER_META = {
    'NVDA':   ('NVDA',       'Tech'),
    'GOOG':   ('GOOG',       'Tech'),
    'IITU':   ('IITU.L',     'Tech'),
    'RTX':    ('RTX',        'Defence'),
    'RHM':    ('RHM.DE',     'Defence'),
    'HO':     ('HO.PA',      'Defence'),
    'BA.':    ('BA.L',       'Defence'),
    'BRK.B':  ('BRK-B',      'Financials'),
    'LGEN':   ('LGEN.L',     'Financials'),
    'RIO':    ('RIO.L',      'Materials'),
    'TECK.B': ('TECK-B.TO',  'Materials'),
    'INRG':   ('INRG.L',     'Energy'),
    'SGLN':   ('SGLN.L',     'Commodities'),
    'VGER':   ('VGER.L',     'Broad ETF'),
    'VUSA':   ('VUSA.L',     'Broad ETF'),
    'ISP6':   ('ISP6.L',     'Broad ETF'),
    'EUE':    ('EUE.L',      'Broad ETF'),
}

SECTOR_ETF = {
    'Tech':        ('XLK', '💻'),
    'Defence':     ('ITA', '🛡'),
    'Materials':   ('XLB', '⛏'),
    'Financials':  ('XLF', '🏦'),
    'Energy':      ('XLU', '⚡'),
    'Commodities': (None,  '🪙'),
    'Broad ETF':   (None,  '🌐'),
}

SECTOR_CONCENTRATION_WARN = 30   # percent


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


def pct_str(val, decimals=1):
    sign = '+' if val >= 0 else '−'
    return f'{sign}{abs(val):.{decimals}f}%'


def escape_html(text):
    return str(text).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def send_telegram(text):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("  Telegram credentials not set — printing instead:\n")
        print(text)
        return False
    try:
        resp = requests.post(
            f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage',
            json={'chat_id': TELEGRAM_CHAT_ID, 'text': text, 'parse_mode': 'HTML'},
            timeout=15,
        )
        resp.raise_for_status()
        return True
    except Exception as e:
        print(f"  Telegram error: {e}")
        return False


def send_telegram_chunks(message):
    """Split on section boundaries (━━━) to stay under the 4096-char limit."""
    if len(message) <= 4096:
        return send_telegram(message)

    parts   = message.split('\n━━━')
    chunks  = []
    current = parts[0]
    for part in parts[1:]:
        candidate = current + '\n━━━' + part
        if len(candidate) <= 4000:
            current = candidate
        else:
            chunks.append(current)
            current = '━━━' + part
    chunks.append(current)

    ok = True
    for c in chunks:
        ok = send_telegram(c) and ok
    return ok


# ---------------------------------------------------------------------------
# yfinance helpers
# ---------------------------------------------------------------------------

def seven_day_return_pct(symbol):
    """Return the 7-calendar-day return as a percentage. None on failure."""
    try:
        t    = yf.Ticker(symbol)
        hist = t.history(period='10d', auto_adjust=True)
        if hist is None or hist.empty or len(hist) < 2:
            return None
        closes = hist['Close'].dropna()
        if len(closes) < 2:
            return None
        first = float(closes.iloc[0])
        last  = float(closes.iloc[-1])
        if first == 0:
            return None
        return (last - first) / first * 100
    except Exception as e:
        print(f"    7d return fetch failed for {symbol}: {e}")
        return None


# ---------------------------------------------------------------------------
# Sheet readers
# ---------------------------------------------------------------------------

def read_summary(sh):
    ws = sh.worksheet('Inv26 - Summary')

    def cell(row):
        r = ws.row_values(row)
        return parse_float(r[COL_VALUE_IDX]) if len(r) > COL_VALUE_IDX else 0.0

    return {
        'grand_total':   cell(ROW_GRAND_TOTAL),
        'cash':          cell(ROW_CASH),
        'stocks_total':  cell(ROW_STOCKS_TOTAL),
        'managed_total': cell(ROW_MANAGED_TOTAL),
    }


def read_baseline_total(sh):
    """Read grand total from Inv26 - Trend row 17 (Apr 13 baseline)."""
    try:
        ws = sh.worksheet('Inv26 - Trend')
        row = ws.row_values(TREND_BASELINE_ROW)
        if len(row) > TREND_TOTAL_COL:
            return parse_float(row[TREND_TOTAL_COL])
    except Exception as e:
        print(f"  Baseline read failed: {e}")
    return 0.0


# ---------------------------------------------------------------------------
# Portfolio WoW via yfinance (weighted by market value)
# ---------------------------------------------------------------------------

def compute_portfolio_7d_return(holdings):
    """
    Weighted 7-day return across held stocks.
    holdings: list of {'ticker', 'qty', 'current_price'} from holdings_alerts.json.
    Returns percentage (float) or None if not enough data.
    """
    total_value   = 0.0
    weighted_sum  = 0.0
    for h in holdings:
        ticker = h.get('ticker')
        qty    = h.get('qty', 0)
        price  = h.get('current_price', 0)
        if ticker not in TICKER_META or qty <= 0 or price <= 0:
            continue
        yf_sym = TICKER_META[ticker][0]
        ret    = seven_day_return_pct(yf_sym)
        if ret is None:
            continue
        value         = qty * price
        total_value  += value
        weighted_sum += value * ret
    if total_value == 0:
        return None
    return weighted_sum / total_value


# ---------------------------------------------------------------------------
# Holdings classification
# ---------------------------------------------------------------------------

def sentiment_badge(h):
    """
    Build a compact sentiment/news badge from holdings_alerts.json fields.
    Prefers bullish/bearish percentage from Finnhub+AV; falls back to news count.
    """
    bull = h.get('bullish_pct')
    bear = h.get('bearish_pct')
    news = h.get('news_count', 0) or 0

    if bull is not None and bear is not None and (bull > 0 or bear > 0):
        if bull >= bear + 15:
            return f'{int(bull)}% bull'
        if bear >= bull + 10:
            return f'{int(bear)}% bear'
        return f'mixed {int(bull)}/{int(bear)}'

    if news > 0:
        return f'{news} headline{"s" if news > 1 else ""}'
    return ''


def classify_holding(h):
    """
    Map holdings_monitor output onto digest labels.
    Returns (label, icon, note) or (None, None, None) for STEADY (suppressed).
    """
    level  = h.get('alert_level', 'NONE')
    score  = h.get('score', 5)
    event  = (h.get('event') or '').strip()
    badge  = sentiment_badge(h)

    def _note(primary):
        parts = [p for p in (badge, primary) if p]
        return ' · '.join(parts)

    if level == 'ACT':
        return ('CONSIDER_SELL', '📉', _note(event or h.get('rationale', '')[:40]))

    if level == 'WATCH':
        is_earnings = 'earning' in (event or '').lower()
        icon = '📅' if is_earnings else '👀'
        return ('WATCH', icon, _note(event or 'catalyst ahead'))

    # alert_level == NONE
    if score <= 4:
        return ('CONSIDER_SELL', '📉', _note(h.get('rationale', '')[:40] or 'weak signal'))
    if score >= 8:
        return ('BUY_MORE', '📈', _note(h.get('rationale', '')[:40] or 'strong signal'))
    return (None, None, None)   # STEADY — suppressed


# ---------------------------------------------------------------------------
# Section builders
# ---------------------------------------------------------------------------

def build_portfolio_section(summary, portfolio_7d, baseline_total):
    total = summary['grand_total']
    lines = ['━━━ <b>PORTFOLIO</b> ━━━']

    if portfolio_7d is not None:
        wow_gbp = total * portfolio_7d / 100
        sign    = '+' if portfolio_7d >= 0 else '−'
        lines.append(
            f'Total: <b>£{total:,.0f}</b>  ({sign}£{abs(wow_gbp):,.0f} / {pct_str(portfolio_7d)} WoW)'
        )
    else:
        lines.append(f'Total: <b>£{total:,.0f}</b>')

    if baseline_total > 0:
        baseline_pct = (total - baseline_total) / baseline_total * 100
        lines.append(f'vs Apr 13 baseline: <b>{pct_str(baseline_pct)}</b>')

    return '\n'.join(lines)


def build_benchmarks_section(portfolio_7d, bench_returns):
    """bench_returns: list of (name, pct) tuples. portfolio_7d: user's pct."""
    lines = ['━━━ <b>BENCHMARKS (7d %)</b> ━━━', '<pre>']

    if portfolio_7d is not None:
        emoji = '🟢' if portfolio_7d >= 0 else '🔴'
        lines.append(f'{emoji} You:         {pct_str(portfolio_7d)}')

    beat_count = 0
    total      = 0
    for name, pct in bench_returns:
        if pct is None:
            lines.append(f'⚪ {name:<12} n/a')
            continue
        total += 1
        emoji = '🟢' if pct >= 0 else '🔴'
        beat  = ''
        if portfolio_7d is not None and portfolio_7d > pct:
            beat = '   ← beat'
            beat_count += 1
        # Display with SP500/FTSE/etc name padded
        name_padded = f'{name}:'.ljust(13)
        lines.append(f'{emoji} {name_padded}{pct_str(pct)}{beat}')

    lines.append('</pre>')
    if portfolio_7d is not None and total > 0:
        lines.append(f'<b>Beat {beat_count} of {total} benchmarks {"✅" if beat_count >= total/2 else "⚠"}</b>')
    return '\n'.join(lines)


def build_holdings_section(holdings):
    buckets = {'BUY_MORE': [], 'CONSIDER_SELL': [], 'WATCH': []}
    steady_count = 0

    for h in holdings:
        label, icon, note = classify_holding(h)
        if label is None:
            steady_count += 1
            continue
        buckets[label].append((h['ticker'], h.get('score', 5), icon, note))

    # Sort each bucket by score (desc for BUY_MORE, asc for CONSIDER_SELL)
    buckets['BUY_MORE'].sort(key=lambda x: -x[1])
    buckets['CONSIDER_SELL'].sort(key=lambda x: x[1])
    buckets['WATCH'].sort(key=lambda x: -x[1])

    out = ['━━━ <b>HOLDINGS</b> ━━━']

    def _fmt_bucket(title, rows):
        if not rows:
            return None
        block = [f'\n{title}', '<pre>']
        for ticker, score, icon, note in rows:
            t    = ticker.ljust(6)
            s    = f'{score:.1f}' if isinstance(score, float) else f'{score}'
            note_trunc = note[:42] if note else ''
            block.append(f'{t} {s:>3}  {icon} {note_trunc}')
        block.append('</pre>')
        return '\n'.join(block)

    for title, key in [
        ('🚀 <b>BUY MORE</b>',       'BUY_MORE'),
        ('⚠️ <b>CONSIDER SELL</b>',  'CONSIDER_SELL'),
        ('👀 <b>WATCH</b>',          'WATCH'),
    ]:
        block = _fmt_bucket(title, buckets[key])
        if block:
            out.append(block)

    if steady_count > 0:
        out.append(f'\n<i>{steady_count} other holdings steady.</i>')

    # If nothing triggered, say so explicitly
    if all(not buckets[k] for k in buckets):
        out.append('\n<i>All holdings steady — no action.</i>')

    return '\n'.join(out)


def build_sector_section(holdings):
    # Aggregate market value by sector
    sector_value = {}
    total_value  = 0.0
    for h in holdings:
        ticker = h.get('ticker')
        if ticker not in TICKER_META:
            continue
        sector = TICKER_META[ticker][1]
        if sector in ('Broad ETF', 'Commodities'):
            continue
        value = h.get('qty', 0) * h.get('current_price', 0)
        sector_value[sector] = sector_value.get(sector, 0) + value
        total_value += value

    if total_value == 0:
        return ''

    # Fetch sector ETF 7d returns once
    etf_returns = {}
    for sector, (etf, _icon) in SECTOR_ETF.items():
        if etf and sector in sector_value:
            etf_returns[sector] = seven_day_return_pct(etf)

    lines = ['━━━ <b>SECTOR CONTEXT</b> ━━━', '<pre>']
    sorted_sectors = sorted(sector_value.items(), key=lambda x: -x[1])
    warn_sectors   = []
    for sector, value in sorted_sectors:
        pct_alloc = value / total_value * 100
        icon      = SECTOR_ETF.get(sector, (None, '📊'))[1]
        etf, _    = SECTOR_ETF.get(sector, (None, None))
        warn      = '⚠' if pct_alloc >= SECTOR_CONCENTRATION_WARN else ' '
        if pct_alloc >= SECTOR_CONCENTRATION_WARN:
            warn_sectors.append(sector)
        etf_pct   = etf_returns.get(sector)
        etf_str   = f'{etf} {pct_str(etf_pct)}' if etf and etf_pct is not None else (f'{etf} n/a' if etf else '')
        name      = f'{icon} {sector}'.ljust(15)
        lines.append(f'{name} {pct_alloc:>4.0f}%{warn} {etf_str}')
    lines.append('</pre>')

    if warn_sectors:
        lines.append(f'⚠ Concentration: {", ".join(warn_sectors)} &gt; {SECTOR_CONCENTRATION_WARN}%.')

    return '\n'.join(lines)


def build_discovery_section(prospect_results):
    if not prospect_results:
        return ''
    # Sort by score, take top 3
    items = sorted(prospect_results.items(), key=lambda kv: -kv[1].get('score', 0))
    top3  = [(t, r) for t, r in items if r.get('score', 0) >= 6][:3]
    if not top3:
        return ''

    lines = ['━━━ <b>DISCOVERY (top 3)</b> ━━━', '<pre>']
    for i, (ticker, r) in enumerate(top3, 1):
        score = r.get('score', 0)
        notes = r.get('notes', '') or r.get('reason', '')[:40]
        notes_trunc = notes[:38]
        lines.append(f'{i}. {ticker:<6}{score:>3}  {notes_trunc}')
    lines.append('</pre>')
    return '\n'.join(lines)


# ---------------------------------------------------------------------------
# LLM recommendation
# ---------------------------------------------------------------------------

def build_recommendation(summary, portfolio_7d, bench_returns, holdings, prospects):
    if not CLAUDE_API_KEY:
        return ''

    holdings_summary = []
    for h in holdings:
        label, _, _ = classify_holding(h)
        if label is None:
            continue
        holdings_summary.append(
            f"{h['ticker']} (FAS {h.get('score')}, {label}): "
            f"{h.get('event') or h.get('rationale', '')[:80]}"
        )

    bench_lines = [f"{n}: {pct_str(p)}" for n, p in bench_returns if p is not None]
    prospect_lines = []
    if prospects:
        top = sorted(prospects.items(), key=lambda kv: -kv[1].get('score', 0))[:3]
        for t, r in top:
            prospect_lines.append(f"{t} (score {r.get('score')}): {r.get('notes', '')[:60]}")

    user_return_line = (
        f"Portfolio 7d: {pct_str(portfolio_7d)}" if portfolio_7d is not None else "Portfolio 7d: n/a"
    )

    prompt = f"""You are writing the closing paragraph of a weekly portfolio digest for a UK retail investor.

CONTEXT (this week):
{user_return_line}
Total value: £{summary['grand_total']:,.0f}

BENCHMARKS (7d):
{chr(10).join(bench_lines)}

HOLDINGS THAT NEED ATTENTION:
{chr(10).join(holdings_summary) if holdings_summary else '(none — all holdings steady)'}

DISCOVERY CANDIDATES:
{chr(10).join(prospect_lines) if prospect_lines else '(none)'}

Write a single paragraph, 3–5 sentences, ~80 words max. Reference the most important
holdings by ticker. Be concrete (e.g. "trim NVDA 20%", "set stop-loss on BA.",
"watch RTX earnings"). If the user beat most benchmarks, say so briefly. If there
are concentration risks or earnings-heavy weeks ahead, flag them. End with one
concrete prospect suggestion if discovery is strong. Plain prose, no bullet points,
no markdown. Do NOT start with "Here's" or "This week".
"""

    try:
        client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
        msg = client.messages.create(
            model='claude-sonnet-4-6',
            max_tokens=300,
            messages=[{'role': 'user', 'content': prompt}],
        )
        return msg.content[0].text.strip()
    except Exception as e:
        print(f"  Claude recommendation failed: {e}")
        return ''


def build_recommendation_section(text):
    if not text:
        return ''
    return f'━━━ <b>RECOMMENDATION</b> ━━━\n<i>{escape_html(text)}</i>'


# ---------------------------------------------------------------------------
# Data loaders
# ---------------------------------------------------------------------------

def load_holdings():
    if not os.path.exists(HOLDINGS_PATH):
        print(f"  {HOLDINGS_PATH} missing — holdings section will be skipped")
        return []
    with open(HOLDINGS_PATH) as f:
        return json.load(f)


def load_prospects():
    if not os.path.exists(PROSPECT_PATH):
        return {}
    with open(PROSPECT_PATH) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("Connecting to Google Sheets...")
    creds = Credentials.from_service_account_file(SA_FILE, scopes=SCOPES)
    gc    = gspread.authorize(creds)
    sh    = gc.open_by_key(SHEET_ID)
    print(f"  Opened: {sh.title}")

    print("\nReading portfolio summary...")
    summary        = read_summary(sh)
    baseline_total = read_baseline_total(sh)
    print(f"  Grand Total: £{summary['grand_total']:,.2f}  |  Baseline: £{baseline_total:,.2f}")

    print("\nLoading holdings_alerts.json...")
    holdings = load_holdings()
    print(f"  {len(holdings)} holdings loaded")

    print("\nLoading prospect_results.json...")
    prospects = load_prospects()
    print(f"  {len(prospects)} prospects loaded")

    print("\nComputing portfolio 7-day return (weighted by market value)...")
    portfolio_7d = compute_portfolio_7d_return(holdings)
    print(f"  Portfolio 7d: {portfolio_7d:.2f}%" if portfolio_7d is not None else "  Portfolio 7d: n/a")

    print("\nFetching benchmark 7-day returns...")
    bench_returns = []
    for name, sym in BENCHMARKS:
        pct = seven_day_return_pct(sym)
        bench_returns.append((name, pct))
        print(f"  {name} ({sym}): {pct:.2f}%" if pct is not None else f"  {name}: n/a")

    print("\nBuilding sections...")
    header = '📊 <b>WEEKLY DIGEST</b>\n<i>' + datetime.now(timezone.utc).strftime('%d %b %Y') + '</i>'

    sections = [
        header,
        build_portfolio_section(summary, portfolio_7d, baseline_total),
        build_benchmarks_section(portfolio_7d, bench_returns),
        build_holdings_section(holdings) if holdings else '',
        build_sector_section(holdings) if holdings else '',
        build_discovery_section(prospects),
    ]

    print("\nGenerating LLM recommendation...")
    rec_text = build_recommendation(summary, portfolio_7d, bench_returns, holdings, prospects)
    if rec_text:
        sections.append(build_recommendation_section(rec_text))

    message = '\n\n'.join(s for s in sections if s)
    print(f"\nDigest assembled ({len(message)} chars). Sending...")
    send_telegram_chunks(message)
    print("Done.")


if __name__ == '__main__':
    main()
