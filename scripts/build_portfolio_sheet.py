#!/usr/bin/env python3
"""
build_portfolio_sheet.py

Reads T212 and Freetrade CSV exports from data/ folder,
normalises all buy/sell transactions, and populates:
  - InvTransactions tab: full trade history (both platforms)
  - Inv26 tab: live dashboard with GOOGLEFINANCE formulas + formatting

Run from repo root:
    python3 scripts/build_portfolio_sheet.py
"""

import os
import csv
from datetime import datetime
from dotenv import load_dotenv
import gspread
from google.oauth2.service_account import Credentials

load_dotenv()

SHEET_ID = os.getenv('PORTFOLIO_SHEET_ID')
SA_FILE = os.getenv('GOOGLE_APPLICATION_CREDENTIALS', 'config/service_account.json')
DATA_DIR = 'data'

SCOPES = ['https://www.googleapis.com/auth/spreadsheets']

# ---------------------------------------------------------------------------
# Ticker mappings
# ---------------------------------------------------------------------------
# currency: GBX = London pence (/100 for £), GBP = direct, USD/EUR/CAD = FX needed
# Note: VGER returns GBP (not GBX) despite being London-listed — confirmed from sheet

FT_TICKER_MAP = {
    'HOp':   ('HO',     'EPA:HO',       'EUR'),   # Thales
    'BA.':   ('BA.',    'LON:BA.',       'GBP'),   # BAE Systems
    'RHMd':  ('RHM',    'ETR:RHM',       'EUR'),   # Rheinmetall
    'EUE':   ('EUE',    'LON:EUE',       'GBX'),   # iShares Core Euro STOXX 50
    'VGER':  ('VGER',   'LON:VGER',      'GBP'),   # iShares Core DAX — returns GBP not GBX
    'VUSA':  ('VUSA',   'LON:VUSA',      'GBX'),   # Vanguard S&P 500
    'ISP6':  ('ISP6',   'LON:ISP6',      'GBX'),   # iShares S&P SmallCap 600
    'BRK.B': ('BRK.B',  'NYSE:BRK.B',    'USD'),   # Berkshire Hathaway Class B
}

T212_TICKER_MAP = {
    'NVDA':   ('NVDA',   'NASDAQ:NVDA',  'USD'),
    'RIO':    ('RIO',    'LON:RIO',      'GBX'),
    'SGLN':   ('SGLN',   'LON:SGLN',     'GBX'),   # iShares Physical Gold ETC
    'INRG':   ('INRG',   'LON:INRG',     'GBX'),
    'RTX':    ('RTX',    'NYSE:RTX',     'USD'),
    'TECK/B': ('TECK.B', 'TSE:TECK.B',   'CAD'),
    'IITU':   ('IITU',   'LON:IITU',     'GBX'),
    'GOOG':   ('GOOG',   'NASDAQ:GOOG',  'USD'),
    'FIG':    ('FIG',    'NYSE:FIG',     'USD'),
}

TICKER_NAMES = {
    'NVDA':   'Nvidia',
    'RIO':    'Rio Tinto',
    'SGLN':   'iShares Physical Gold',
    'INRG':   'iShares Global Clean Energy',
    'RTX':    'RTX Corp',
    'TECK.B': 'Teck Resources (Class B)',
    'IITU':   'iShares S&P 500 IT Sector',
    'GOOG':   'Alphabet (Class C)',
    'HO':     'Thales',
    'BA.':    'BAE Systems',
    'RHM':    'Rheinmetall',
    'EUE':    'iShares Core Euro STOXX 50',
    'VGER':   'iShares Core DAX UCITS ETF',
    'VUSA':   'Vanguard S&P 500 UCITS ETF',
    'ISP6':   'iShares S&P SmallCap 600',
    'BRK.B':  'Berkshire Hathaway (Class B)',
    'FIG':    'Figma',
}


# ---------------------------------------------------------------------------
# GOOGLEFINANCE formula builder
# ---------------------------------------------------------------------------

def price_formula_gbp(gf_ticker, currency):
    """
    Return a GOOGLEFINANCE formula giving current price in GBP.
    Currency conversion: divide by GBP/XXX rate (more reliable than multiply by XXX/GBP).
    All wrapped in IFERROR to show blank instead of #N/A.
    """
    if currency == 'GBX':
        # London pence — divide by 100
        inner = f'GOOGLEFINANCE("{gf_ticker}","price")/100'
    elif currency == 'GBP':
        inner = f'GOOGLEFINANCE("{gf_ticker}","price")'
    elif currency == 'USD':
        # GOOGLEFINANCE("CURRENCY:GBPUSD") = USD per 1 GBP (scalar, reliable)
        inner = f'GOOGLEFINANCE("{gf_ticker}","price")/GOOGLEFINANCE("CURRENCY:GBPUSD")'
    elif currency == 'EUR':
        inner = f'GOOGLEFINANCE("{gf_ticker}","price")/GOOGLEFINANCE("CURRENCY:GBPEUR")'
    elif currency == 'CAD':
        inner = f'GOOGLEFINANCE("{gf_ticker}","price")/GOOGLEFINANCE("CURRENCY:GBPCAD")'
    else:
        inner = f'GOOGLEFINANCE("{gf_ticker}","price")'
    return f'=IFERROR({inner},"")'


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def parse_t212(data_dir):
    transactions = []
    for fname in os.listdir(data_dir):
        if not (fname.startswith('Trading212') and fname.endswith('.csv')):
            continue
        with open(os.path.join(data_dir, fname), newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                action = row['Action']
                if action not in ('Market buy', 'Market sell'):
                    continue
                raw_ticker = row['Ticker']
                if raw_ticker not in T212_TICKER_MAP:
                    print(f"  Warning: unknown T212 ticker {raw_ticker!r} — skipping")
                    continue
                std_ticker, gf_ticker, currency = T212_TICKER_MAP[raw_ticker]
                qty = float(row['No. of shares'])
                total_gbp = float(row['Total'])
                price_gbp = round(total_gbp / qty, 4) if qty else 0
                transactions.append({
                    'date': row['Time'][:10],
                    'ticker': std_ticker,
                    'gf_ticker': gf_ticker,
                    'currency': currency,
                    'name': TICKER_NAMES.get(std_ticker, row['Name']),
                    'action': 'BUY' if action == 'Market buy' else 'SELL',
                    'qty': round(qty, 8),
                    'price_gbp': price_gbp,
                    'total_gbp': round(total_gbp, 2),
                    'platform': 'T212',
                })
    print(f"  T212: {len(transactions)} buy/sell transactions")
    return transactions


def parse_freetrade(data_dir):
    transactions = []
    for fname in os.listdir(data_dir):
        if not (fname.startswith('freetrade') and fname.endswith('.csv')):
            continue
        with open(os.path.join(data_dir, fname), newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row['Type'] != 'ORDER':
                    continue
                raw_ticker = row['Ticker']
                if raw_ticker not in FT_TICKER_MAP:
                    print(f"  Warning: unknown Freetrade ticker {raw_ticker!r} — skipping")
                    continue
                std_ticker, gf_ticker, currency = FT_TICKER_MAP[raw_ticker]
                qty = float(row['Quantity'])
                total_gbp = abs(float(row['Total Amount in Account Currency']))
                price_str = row['Price per Share in Account Currency']
                price_gbp = float(price_str) if price_str else round(total_gbp / qty, 4)
                transactions.append({
                    'date': row['Timestamp'][:10],
                    'ticker': std_ticker,
                    'gf_ticker': gf_ticker,
                    'currency': currency,
                    'name': TICKER_NAMES.get(std_ticker, row['Title']),
                    'action': row['Buy / Sell'].upper(),
                    'qty': round(qty, 8),
                    'price_gbp': round(price_gbp, 4),
                    'total_gbp': round(total_gbp, 2),
                    'platform': 'Freetrade',
                })
    print(f"  Freetrade: {len(transactions)} buy/sell transactions")
    return transactions


# ---------------------------------------------------------------------------
# Position calculation
# ---------------------------------------------------------------------------

def compute_positions(transactions):
    holdings = {}
    for tx in sorted(transactions, key=lambda x: x['date']):
        t = tx['ticker']
        if t not in holdings:
            holdings[t] = {
                'ticker': t, 'gf_ticker': tx['gf_ticker'], 'currency': tx['currency'],
                'name': tx['name'], 'platform': tx['platform'],
                'qty': 0.0, 'total_buy_cost': 0.0, 'total_buy_qty': 0.0,
            }
        h = holdings[t]
        if tx['action'] == 'BUY':
            h['qty'] += tx['qty']
            h['total_buy_cost'] += tx['total_gbp']
            h['total_buy_qty'] += tx['qty']
        else:
            h['qty'] -= tx['qty']

    open_positions = {}
    for t, h in holdings.items():
        if h['qty'] > 0.0001:
            h['avg_price_gbp'] = round(h['total_buy_cost'] / h['total_buy_qty'], 4)
            h['qty'] = round(h['qty'], 8)
            open_positions[t] = h
    return open_positions


# ---------------------------------------------------------------------------
# Sheet helpers
# ---------------------------------------------------------------------------

def get_or_create_worksheet(sh, title, rows=500, cols=20):
    try:
        ws = sh.worksheet(title)
        ws.clear()
        print(f"  Tab '{title}': cleared")
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=title, rows=rows, cols=cols)
        print(f"  Tab '{title}': created")
    return ws


def col_letter(n):
    """Convert 1-based column index to letter(s). e.g. 1→A, 26→Z, 27→AA"""
    result = ''
    while n > 0:
        n, remainder = divmod(n - 1, 26)
        result = chr(65 + remainder) + result
    return result


def apply_formatting(sh, ws, stock_start, stock_end, mf_nutmeg, mf_money):
    """Apply bold, number formats, column widths, and header colours via Sheets API."""
    sid = ws.id

    def cell_range(r1, c1, r2=None, c2=None):
        """Return a GridRange dict (0-based)."""
        gr = {'sheetId': sid, 'startRowIndex': r1 - 1, 'startColumnIndex': c1 - 1}
        if r2: gr['endRowIndex'] = r2
        if c2: gr['endColumnIndex'] = c2
        return gr

    def fmt_request(r1, c1, r2, c2, fmt):
        return {'repeatCell': {
            'range': cell_range(r1, c1, r2, c2),
            'cell': {'userEnteredFormat': fmt},
            'fields': 'userEnteredFormat(' + ','.join(fmt.keys()) + ')',
        }}

    GBP_FMT   = {'numberFormat': {'type': 'CURRENCY', 'pattern': '£#,##0.00'}}
    PCT_FMT   = {'numberFormat': {'type': 'PERCENT',  'pattern': '0.00%'}}
    QTY_FMT   = {'numberFormat': {'type': 'NUMBER',   'pattern': '#,##0.0000'}}
    BOLD      = {'textFormat': {'bold': True}}
    BOLD_WHITE= {'textFormat': {'bold': True, 'foregroundColor': {'red':1,'green':1,'blue':1}}}
    BLUE_BG   = {'backgroundColor': {'red': 0.18, 'green': 0.42, 'blue': 0.75}}
    GREY_BG   = {'backgroundColor': {'red': 0.93, 'green': 0.93, 'blue': 0.93}}

    col_count = 13  # A–M

    requests = [
        # Title row — bold, larger font
        fmt_request(1, 1, 2, 2, {'textFormat': {'bold': True, 'fontSize': 13}}),

        # Section header rows — grey background, bold
        fmt_request(4, 1, 5, col_count + 1, {**GREY_BG, **BOLD}),
        fmt_request(7, 1, 8, col_count + 1, {**GREY_BG, **BOLD}),

        # Stock column header row — blue background, white bold text
        fmt_request(8, 1, 9, col_count + 1, {**BLUE_BG, **BOLD_WHITE}),

        # Qty column (D) — 4 decimal places
        fmt_request(stock_start, 4, stock_end + 1, 5, QTY_FMT),

        # Avg Buy £ (E), Current Price £ (F), Current Value £ (G), Cost Basis £ (H), P&L £ (I)
        fmt_request(stock_start, 5, stock_end + 1, 10, GBP_FMT),

        # P&L % (J)
        fmt_request(stock_start, 10, stock_end + 1, 11, PCT_FMT),

        # Summary row values (B, E, H, K) — GBP/PCT formatting
        fmt_request(5, 2, 6, 3, GBP_FMT),
        fmt_request(5, 5, 6, 6, GBP_FMT),
        fmt_request(5, 8, 6, 9, GBP_FMT),
        fmt_request(5, 11, 6, 12, PCT_FMT),

        # Managed funds section header — grey bg, bold
        fmt_request(mf_nutmeg - 2, 1, mf_nutmeg - 1, 8, {**GREY_BG, **BOLD}),
        # MF col headers — blue bg, white bold
        fmt_request(mf_nutmeg - 1, 1, mf_nutmeg, 8, {**BLUE_BG, **BOLD_WHITE}),
        # MF £ values (C, D, E)
        fmt_request(mf_nutmeg, 3, mf_money + 1, 6, GBP_FMT),
        # MF P&L %
        fmt_request(mf_nutmeg, 6, mf_money + 1, 7, PCT_FMT),

        # Column widths (0-based column indices)
        {'updateDimensionProperties': {
            'range': {'sheetId': sid, 'dimension': 'COLUMNS', 'startIndex': 0, 'endIndex': 1},
            'properties': {'pixelSize': 80}, 'fields': 'pixelSize'}},   # A: Ticker
        {'updateDimensionProperties': {
            'range': {'sheetId': sid, 'dimension': 'COLUMNS', 'startIndex': 1, 'endIndex': 2},
            'properties': {'pixelSize': 210}, 'fields': 'pixelSize'}},  # B: Name
        {'updateDimensionProperties': {
            'range': {'sheetId': sid, 'dimension': 'COLUMNS', 'startIndex': 2, 'endIndex': 3},
            'properties': {'pixelSize': 85}, 'fields': 'pixelSize'}},   # C: Platform
        {'updateDimensionProperties': {
            'range': {'sheetId': sid, 'dimension': 'COLUMNS', 'startIndex': 3, 'endIndex': 4},
            'properties': {'pixelSize': 100}, 'fields': 'pixelSize'}},  # D: Qty
        {'updateDimensionProperties': {
            'range': {'sheetId': sid, 'dimension': 'COLUMNS', 'startIndex': 4, 'endIndex': 10},
            'properties': {'pixelSize': 120}, 'fields': 'pixelSize'}},  # E–J: £ columns
        {'updateDimensionProperties': {
            'range': {'sheetId': sid, 'dimension': 'COLUMNS', 'startIndex': 10, 'endIndex': 13},
            'properties': {'pixelSize': 110}, 'fields': 'pixelSize'}},  # K–M: Score etc
    ]

    sh.batch_update({'requests': requests})
    print("  Formatting applied")


# ---------------------------------------------------------------------------
# Sheet writers
# ---------------------------------------------------------------------------

def write_inv_transactions(ws, transactions):
    headers = ['Date', 'Ticker', 'Name', 'Action', 'Qty', 'Price per Share £', 'Total £', 'Platform']
    rows = [headers]
    for tx in sorted(transactions, key=lambda x: x['date']):
        rows.append([
            tx['date'], tx['ticker'], tx['name'], tx['action'],
            tx['qty'], tx['price_gbp'], tx['total_gbp'], tx['platform'],
        ])
    ws.update(rows, 'A1')
    print(f"  InvTransactions: {len(rows)-1} transactions")


def write_inv26(sh, ws, positions):
    """
    Layout (fixed row numbers):
      1  Title
      2  Last updated
      3  blank
      4  SUMMARY header
      5  Summary data row
      6  blank
      7  STOCKS section header
      8  Column headers
      9… Stock rows (one per open position)
      N+1 blank
      N+2 MANAGED FUNDS header
      N+3 MF column headers
      N+4 Nutmeg Alpha / JP Morgan
      N+5 Moneyfarm
    """
    today = datetime.today().strftime('%Y-%m-%d')
    stocks = sorted(positions.values(), key=lambda x: (0 if x['platform'] == 'T212' else 1, x['name']))
    n = len(stocks)

    STOCK_START = 9
    STOCK_END   = STOCK_START + n - 1   # = 19 for 11 stocks
    MF_HDR      = STOCK_END + 2         # = 21
    MF_COL_HDR  = STOCK_END + 3         # = 22
    MF_NUTMEG   = STOCK_END + 4         # = 23
    MF_MONEY    = STOCK_END + 5         # = 24
    SR          = 5                     # summary row

    rows = []

    # Rows 1–3
    rows.append(['PORTFOLIO DASHBOARD — Inv26'])
    rows.append([f'Last updated: {today}'])
    rows.append([''])

    # Row 4: section label (plain text — no leading = to avoid formula parse)
    rows.append(['SUMMARY'])

    # Row 5: summary data
    rows.append([
        'Stocks Total Value £',  f'=SUM(G{STOCK_START}:G{STOCK_END})',
        '',
        'Managed Funds Value £', f'=D{MF_NUTMEG}+D{MF_MONEY}',
        '',
        'Grand Total £',         f'=B{SR}+E{SR}',
        '',
        'Stocks P&L £',          f'=SUM(I{STOCK_START}:I{STOCK_END})',
        '',
        'Stocks P&L %',          f'=IFERROR(SUM(I{STOCK_START}:I{STOCK_END})/SUM(H{STOCK_START}:H{STOCK_END}),"")',
    ])

    # Row 6: blank
    rows.append([''])

    # Row 7: section label
    rows.append(['SELF-MANAGED STOCKS'])

    # Row 8: column headers
    rows.append([
        'Ticker', 'Name', 'Platform', 'Qty', 'Avg Buy £',
        'Current Price £', 'Current Value £', 'Cost Basis £',
        'P&L £', 'P&L %', 'Score', 'Recommendation', 'Last Updated by Script',
    ])

    # Rows 9…: stock data
    for stock in stocks:
        r = len(rows) + 1  # 1-based sheet row
        rows.append([
            stock['ticker'],
            stock['name'],
            stock['platform'],
            stock['qty'],
            stock['avg_price_gbp'],
            price_formula_gbp(stock['gf_ticker'], stock['currency']),
            f'=IFERROR(D{r}*F{r},"")',
            f'=D{r}*E{r}',
            f'=IFERROR(G{r}-H{r},"")',
            f'=IFERROR((G{r}-H{r})/H{r},"")',
            '', '', '',
        ])

    assert len(rows) == STOCK_END, f"Row mismatch: {len(rows)} vs {STOCK_END}"

    # Blank row after stocks
    rows.append([''])

    # Managed funds section
    rows.append(['MANAGED FUNDS (update current value monthly)'])
    rows.append(['Name', 'Provider', 'Invested £', 'Current Value £', 'P&L £', 'P&L %', 'Last Updated'])
    rows.append([
        'Nutmeg Alpha', 'JP Morgan', 0, 0,
        f'=D{MF_NUTMEG}-C{MF_NUTMEG}',
        f'=IFERROR((D{MF_NUTMEG}-C{MF_NUTMEG})/C{MF_NUTMEG},"")',
        '',
    ])
    rows.append([
        'Moneyfarm', 'Moneyfarm', 0, 0,
        f'=D{MF_MONEY}-C{MF_MONEY}',
        f'=IFERROR((D{MF_MONEY}-C{MF_MONEY})/C{MF_MONEY},"")',
        '',
    ])

    ws.update(rows, 'A1', value_input_option='USER_ENTERED')
    print(f"  Inv26: {n} stocks + 2 managed fund rows written")

    apply_formatting(sh, ws, STOCK_START, STOCK_END, MF_NUTMEG, MF_MONEY)

    print(f"  Fill rows {MF_NUTMEG} and {MF_MONEY}: columns C (Invested £) and D (Current Value £)")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("Connecting to Google Sheets...")
    creds = Credentials.from_service_account_file(SA_FILE, scopes=SCOPES)
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(SHEET_ID)
    print(f"  Opened: {sh.title}")

    print("\nParsing CSVs...")
    all_txs = parse_t212(DATA_DIR) + parse_freetrade(DATA_DIR)
    print(f"  Total: {len(all_txs)} transactions")

    print("\nComputing positions...")
    positions = compute_positions(all_txs)
    print(f"  Open positions: {len(positions)}")
    for ticker, p in sorted(positions.items()):
        print(f"    {ticker:8s}  qty={p['qty']:12.4f}  avg_buy=£{p['avg_price_gbp']:.2f}  ({p['platform']})")

    print("\nWriting InvTransactions...")
    ws_tx = get_or_create_worksheet(sh, 'InvTransactions')
    write_inv_transactions(ws_tx, all_txs)

    print("\nWriting Inv26 - Summary...")
    ws_inv = get_or_create_worksheet(sh, 'Inv26 - Summary')
    write_inv26(sh, ws_inv, positions)

    print("\nDone.")


if __name__ == '__main__':
    main()
